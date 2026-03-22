"""
Webhook Notification Adapter
=============================
Implements NotificationPort for webhook notifications

Sends notifications to external systems via HTTP webhooks
"""
import httpx
import hmac
import hashlib
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from ..ports import (
    NotificationPort,
    NotificationChannel,
    NotificationRequest,
    NotificationResponse,
)


class WebhookNotificationAdapter(NotificationPort):
    """
    Webhook notification adapter
    
    Sends notifications to external URLs via HTTP POST
    Used for notifying seller stores about order events
    """
    
    def __init__(
        self,
        secret_key: str = "",
        default_headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ):
        self.secret_key = secret_key
        self.default_headers = default_headers or {
            "Content-Type": "application/json"
        }
        self.timeout = timeout
    
    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.WEBHOOK
    
    @property
    def provider_name(self) -> str:
        return "webhook"
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        """Send webhook notification to external URL"""
        if not request.recipient.webhook_url:
            return NotificationResponse(
                success=False,
                error="No webhook URL provided",
                provider=self.provider_name
            )
        
        payload = {
            "event": request.content.template_id or "notification",
            "timestamp": datetime.utcnow().isoformat(),
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
            "X-Webhook-Event": request.content.template_id or "notification"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    request.recipient.webhook_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code in [200, 201, 202]:
                    return NotificationResponse(
                        success=True,
                        message_id=f"webhook_{datetime.utcnow().timestamp()}",
                        provider=self.provider_name
                    )
                else:
                    return NotificationResponse(
                        success=False,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                        provider=self.provider_name
                    )
                    
        except httpx.TimeoutException:
            return NotificationResponse(
                success=False,
                error="Request timeout",
                provider=self.provider_name
            )
        except Exception as e:
            return NotificationResponse(
                success=False,
                error=str(e),
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
