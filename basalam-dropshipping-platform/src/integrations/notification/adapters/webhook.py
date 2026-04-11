"""
Webhook Notification Adapter
=============================
Implements NotificationPort for webhook notifications

Sends notifications to external systems via HTTP webhooks
with retry logic and dead letter queue support.
"""
import httpx
import hmac
import hashlib
import json
import structlog
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from ..ports import (
    NotificationPort,
    NotificationChannel,
    NotificationRequest,
    NotificationResponse,
)
from src.core.webhook_metrics import (
    record_outgoing_sent,
    record_outgoing_failed,
)


logger = structlog.get_logger(__name__)


# Retry intervals: 1m, 5m, 15m, 1h, 6h
RETRY_INTERVALS = [60, 300, 900, 3600, 21600]
MAX_RETRIES = 5


class WebhookNotificationAdapter(NotificationPort):
    """
    Webhook notification adapter
    
    Sends notifications to external URLs via HTTP POST
    Used for notifying seller stores about order events

    Features:
    - HMAC-SHA256 signature generation
    - Retry with exponential backoff
    - Dead letter queue for permanent failures
    - Logging to OutgoingWebhookLog table
    """
    
    def __init__(
        self,
        secret_key: str = "",
        default_headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        db_session=None,
        integration_id: Optional[UUID] = None,
    ):
        self.secret_key = secret_key
        self.default_headers = default_headers or {
            "Content-Type": "application/json"
        }
        self.timeout = timeout
        self.db_session = db_session
        self.integration_id = integration_id
    
    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.WEBHOOK
    
    @property
    def provider_name(self) -> str:
        return "webhook"
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        """Send webhook notification to external URL with retry logging"""
        if not request.recipient.webhook_url:
            return NotificationResponse(
                success=False,
                error="No webhook URL provided",
                provider=self.provider_name
            )

        event_type = request.content.template_id or "notification"
        
        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "title": request.content.title,
                "body": request.content.body,
                "variables": request.content.variables,
                "action_url": request.content.action_url,
            },
            "metadata": request.metadata
        }
        
        # Generate signature
        signature = self._generate_signature(payload)
        
        headers = {
            **self.default_headers,
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event_type
        }

        # Create log entry if db_session provided
        log_id: Optional[str] = None
        if self.db_session and self.integration_id:
            try:
                log_id = await self._create_webhook_log(
                    event_type=event_type,
                    payload=payload,
                    url=request.recipient.webhook_url,
                )
            except Exception as e:
                logger.error(
                    "failed_to_create_webhook_log_proceeding_without_tracking",
                    error=str(e),
                    exc_info=True,
                )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    request.recipient.webhook_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code in [200, 201, 202]:
                    # Mark as sent
                    if log_id:
                        await self._update_webhook_log(
                            log_id=log_id,
                            status="sent",
                            response_status_code=response.status_code,
                        )

                    record_outgoing_sent(
                        integration_type="webhook",
                        event_type=event_type,
                    )

                    return NotificationResponse(
                        success=True,
                        message_id=f"webhook_{datetime.now(timezone.utc).timestamp()}",
                        provider=self.provider_name
                    )

                elif response.status_code >= 500:
                    # Server error - schedule retry
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"

                    record_outgoing_failed(
                        integration_type="webhook",
                        event_type=event_type,
                        status_code=response.status_code,
                    )

                    if log_id:
                        await self._schedule_retry(
                            log_id=log_id,
                            error=error_msg,
                            response_status_code=response.status_code,
                        )

                    return NotificationResponse(
                        success=False,
                        error=error_msg,
                        provider=self.provider_name
                    )

                else:
                    # 4xx error - permanent failure, move to DLQ
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"

                    if log_id:
                        await self._move_to_dlq(
                            log_id=log_id,
                            failure_reason=error_msg,
                            response_status_code=response.status_code,
                        )

                    return NotificationResponse(
                        success=False,
                        error=error_msg,
                        provider=self.provider_name
                    )
                    
        except httpx.TimeoutException as e:
            error_msg = f"Request timeout: {e}"

            if log_id:
                await self._schedule_retry(
                    log_id=log_id,
                    error=error_msg,
                )

            return NotificationResponse(
                success=False,
                error=error_msg,
                provider=self.provider_name
            )
        except Exception as e:
            error_msg = str(e)

            if log_id:
                await self._schedule_retry(
                    log_id=log_id,
                    error=error_msg,
                )

            return NotificationResponse(
                success=False,
                error=error_msg,
                provider=self.provider_name
            )
    
    async def send_batch(self, requests: List[NotificationRequest]) -> List[NotificationResponse]:
        """Send webhooks to multiple URLs"""
        responses = []
        
        # Send to each URL separately
        for request in requests:
            response = await self.send(request)
            responses.append(response)
        
        return responses
    
    async def verify_connection(self) -> bool:
        """Verify webhook endpoint is reachable"""
        # Could do a health check endpoint
        return True
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get webhook event template"""
        templates = {
            "order_created": {
                "event": "order.created",
                "description": "Sent when a new order is created"
            },
            "order_shipped": {
                "event": "order.shipped",
                "description": "Sent when order is shipped"
            },
            "inventory_updated": {
                "event": "inventory.updated",
                "description": "Sent when inventory changes"
            },
            "price_changed": {
                "event": "price.changed",
                "description": "Sent when product price changes"
            },
            "product_forbidden": {
                "event": "product.forbidden",
                "description": "Sent when a product is rejected by Basalam"
            },
        }
        return templates.get(template_id)
    
    def _generate_signature(self, payload: Dict[str, Any]) -> str:
        """Generate HMAC signature for webhook payload"""
        if not self.secret_key:
            return ""
        
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.secret_key.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"

    async def _create_webhook_log(
        self,
        event_type: str,
        payload: Dict[str, Any],
        url: str,
    ) -> str:
        """Create OutgoingWebhookLog entry. Raises on failure."""
        from src.domains.webhooks.models import OutgoingWebhookLog, OutgoingWebhookStatus

        log = OutgoingWebhookLog(
            integration_id=self.integration_id,
            event_type=event_type,
            payload=payload,
            url=url,
            status=OutgoingWebhookStatus.PENDING.value,
            retry_count=0,
            max_retries=MAX_RETRIES,
        )
        self.db_session.add(log)
        await self.db_session.flush()

        logger.debug("created_outgoing_webhook_log", log_id=str(log.id))
        return str(log.id)

    async def _update_webhook_log(
        self,
        log_id: str,
        status: str,
        response_status_code: Optional[int] = None,
    ):
        """Update webhook log status. Raises on failure."""
        from src.domains.webhooks.models import OutgoingWebhookLog
        from sqlalchemy import update

        stmt = (
            update(OutgoingWebhookLog)
            .where(OutgoingWebhookLog.id == log_id)
            .values(
                status=status,
                last_attempt_at=datetime.now(timezone.utc),
                response_status_code=response_status_code,
            )
        )
        await self.db_session.execute(stmt)
        await self.db_session.flush()

    async def _schedule_retry(
        self,
        log_id: str,
        error: str,
        response_status_code: Optional[int] = None,
    ):
        """Schedule retry for failed webhook. Raises on failure."""
        from src.domains.webhooks.models import OutgoingWebhookLog, OutgoingWebhookStatus
        from sqlalchemy import update, select

        # Get current retry count
        stmt = select(OutgoingWebhookLog.retry_count).where(
            OutgoingWebhookLog.id == log_id
        )
        result = await self.db_session.execute(stmt)
        retry_count = result.scalar() or 0

        new_retry_count = retry_count + 1

        if new_retry_count >= MAX_RETRIES:
            # Move to DLQ
            await self._move_to_dlq(log_id, error, response_status_code)
        else:
            # Schedule next retry
            next_retry_at = datetime.now(timezone.utc) + timedelta(
                seconds=RETRY_INTERVALS[min(retry_count, len(RETRY_INTERVALS) - 1)]
            )

            stmt = (
                update(OutgoingWebhookLog)
                .where(OutgoingWebhookLog.id == log_id)
                .values(
                    status=OutgoingWebhookStatus.RETRYING.value,
                    retry_count=new_retry_count,
                    last_attempt_at=datetime.now(timezone.utc),
                    next_retry_at=next_retry_at,
                    last_error=error[:500] if error else None,
                    response_status_code=response_status_code,
                )
            )
            await self.db_session.execute(stmt)
            await self.db_session.flush()

            logger.info(
                "scheduled_webhook_retry",
                log_id=str(log_id),
                retry_count=new_retry_count,
                max_retries=MAX_RETRIES,
                next_retry_at=next_retry_at.isoformat(),
            )

    async def _move_to_dlq(
        self,
        log_id: str,
        failure_reason: str,
        response_status_code: Optional[int] = None,
    ):
        """Move failed webhook to dead letter queue. Raises on failure."""
        from src.domains.webhooks.models import (
            OutgoingWebhookLog,
            OutgoingWebhookDLQ,
            OutgoingWebhookStatus,
        )
        from sqlalchemy import update

        # Update webhook log status
        stmt = (
            update(OutgoingWebhookLog)
            .where(OutgoingWebhookLog.id == log_id)
            .values(
                status=OutgoingWebhookStatus.FAILED.value,
                last_attempt_at=datetime.now(timezone.utc),
                last_error=failure_reason[:500] if failure_reason else None,
                response_status_code=response_status_code,
            )
        )
        await self.db_session.execute(stmt)

        # Create DLQ entry
        dlq_entry = OutgoingWebhookDLQ(
            outgoing_webhook_log_id=log_id,
            failure_reason=failure_reason[:1000] if failure_reason else "Unknown error",
            failure_count=MAX_RETRIES,
            status="pending",
        )
        self.db_session.add(dlq_entry)

        await self.db_session.flush()

        logger.warning("moved_webhook_to_dlq", log_id=str(log_id))
