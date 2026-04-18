"""
Incoming Webhook Router
=======================
HTTP endpoint for receiving webhooks from external platforms.

Endpoints:
- POST /api/v1/webhooks/{platform_code}/{integration_id}

Security middleware chain (in order):
1. IP allowlist validation
2. Rate limiting
3. Timestamp validation
4. Signature verification
5. Idempotency check
"""
import structlog
import json
import time as time_module
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException, Depends, Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.repository.unit_of_work import UnitOfWork
from src.domains.shops.repository import ShopIntegrationRepository, PlatformRepository
from src.domains.webhooks.repository.webhook_event import WebhookEventRepository
from src.integrations.webhooks.security import (
    get_ip_validator,
    get_timestamp_validator,
    get_audit_logger,
    WebhookRateLimiter,
    SecurityEvent,
)
from src.integrations.webhooks.idempotency import IdempotencyManager
from src.integrations.webhooks.retry import RetryScheduler
from src.integrations.webhooks.processors.base import WebhookProcessorRegistry
from src.integrations.webhooks.processors.product import ProductWebhookProcessor
from src.integrations.webhooks.processors.order import OrderWebhookProcessor
from src.integrations.webhooks.processors.inventory import InventoryWebhookProcessor
from src.core.redis_client import get_redis_client
from src.core.webhook_metrics import (
    record_webhook_received,
    record_webhook_processed,
    record_webhook_failed,
)


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _build_processor_registry(
    secret: str, session: AsyncSession
) -> WebhookProcessorRegistry:
    """
    Build and return a fully-wired processor registry.

    Instantiates all webhook processors with the given secret and DB session
    and registers them for their respective platform + event_type combinations.

    For Basalam, numeric event_ids are resolved to string event types via
    WebhookProcessorRegistry.BASALAM_EVENT_MAP at lookup time.
    """
    registry = WebhookProcessorRegistry()

    product_proc = ProductWebhookProcessor(secret=secret, db_session=session)
    order_proc = OrderWebhookProcessor(secret=secret, db_session=session)
    inventory_proc = InventoryWebhookProcessor(secret=secret, db_session=session)

    # Basalam event_id → resolved event_type at lookup time
    #   8 → "product.changes"
    #   5 → "order.created"
    #   7 → "order.parcel_changed"
    registry.register("basalam", "product.changes", product_proc)
    registry.register("basalam", "order.created", order_proc)
    registry.register("basalam", "order.parcel_changed", order_proc)
    registry.register("basalam", "inventory.changed", inventory_proc)

    return registry


class WebhookResponse(BaseModel):
    """Standard webhook response"""
    status: str
    message: Optional[str] = None
    event_id: Optional[str] = None


async def get_platform_and_integration(
    platform_code: str,
    integration_id: UUID,
    session: AsyncSession,
) -> tuple[Any, Any]:
    """Fetch platform and integration, raise 404 if not found."""
    platform_repo = PlatformRepository(session)
    integration_repo = ShopIntegrationRepository(session)

    platform = await platform_repo.get_by_code(platform_code)
    if not platform:
        raise HTTPException(
            status_code=404,
            detail=f"Platform '{platform_code}' not found"
        )

    integration = await integration_repo.get_by_id(integration_id)
    if not integration:
        raise HTTPException(
            status_code=404,
            detail=f"Integration '{integration_id}' not found"
        )

    if integration.platform_id != platform.id:
        raise HTTPException(
            status_code=400,
            detail="Integration does not belong to this platform"
        )

    return platform, integration


async def validate_ip(
    request: Request,
    platform: Any,
    platform_code: str,
) -> None:
    """Validate client IP against platform allowlist."""
    validator = get_ip_validator()
    client_ip = _get_client_ip(request)

    allowed_ips = platform.webhook_allowed_ips or []

    if not validator.is_ip_allowed(client_ip, allowed_ips, platform_code):
        get_audit_logger().log_security_event(
            event_type=SecurityEvent.IP_REJECTED,
            platform_code=platform_code,
            integration_id=None,
            client_ip=client_ip,
            details={"allowed_ips": allowed_ips},
        )
        raise HTTPException(
            status_code=403,
            detail="IP not allowlisted"
        )


async def validate_rate_limit(
    platform_code: str,
    integration_id: UUID,
    platform: Any,
) -> None:
    """Check rate limit for this integration."""
    redis = get_redis_client()
    limiter = WebhookRateLimiter(redis)

    rate_config = platform.webhook_rate_limit or {"rate": 100, "period": 60}

    allowed, retry_after = await limiter.is_allowed(
        platform_code=platform_code,
        integration_id=str(integration_id),
        rate_limit_config=rate_config,
    )

    if not allowed:
        get_audit_logger().log_security_event(
            event_type=SecurityEvent.RATE_LIMITED,
            platform_code=platform_code,
            integration_id=str(integration_id),
            client_ip=None,
            details={"retry_after": retry_after},
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)} if retry_after else {},
        )


async def validate_timestamp(
    request: Request,
    payload: Dict[str, Any],
    platform: Any,
    platform_code: str,
) -> None:
    """Validate webhook timestamp."""
    validator = get_timestamp_validator()

    headers = dict(request.headers)
    timestamp = validator.extract_timestamp(headers, payload)

    tolerance = platform.webhook_timestamp_tolerance or 300

    is_valid, error = validator.validate_timestamp(
        timestamp=timestamp,
        tolerance=tolerance,
        platform_code=platform_code,
    )

    if not is_valid:
        get_audit_logger().log_security_event(
            event_type=SecurityEvent.TIMESTAMP_INVALID,
            platform_code=platform_code,
            integration_id=None,
            client_ip=_get_client_ip(request),
            details={"error": error, "timestamp": timestamp},
        )
        raise HTTPException(
            status_code=401,
            detail=error or "Timestamp validation failed"
        )


async def verify_signature(
    request: Request,
    raw_body: bytes,
    integration: Any,
    platform_code: str,
) -> str:
    """
    Verify webhook signature.

    Returns the decrypted secret for potential reuse.
    Raises HTTPException if signature is invalid.
    """
    from src.domains.shops.service.webhook_secret_service import get_webhook_secret_service

    secret_service = get_webhook_secret_service()

    if not integration.webhook_secret_encrypted:
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured for this integration"
        )

    # Decrypt secret
    try:
        secret = secret_service.decrypt_for_verification(integration.webhook_secret_encrypted)
    except Exception as e:
        logger.error("failed_to_decrypt_webhook_secret", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Webhook secret decryption failed"
        )

    # Get signature from headers
    signature_header = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("X-Webhook-Signature-256")
        or request.headers.get("X-Hub-Signature-256")
        or request.headers.get("X-Hub-Signature")
        or request.headers.get("X-Basalam-Signature")
    )

    if not signature_header:
        get_audit_logger().log_security_event(
            event_type=SecurityEvent.SIGNATURE_INVALID,
            platform_code=platform_code,
            integration_id=str(integration.id),
            client_ip=_get_client_ip(request),
            details={"reason": "missing_signature"},
        )
        raise HTTPException(
            status_code=401,
            detail="Missing webhook signature"
        )

    # Verify
    is_valid, error = secret_service.verify_signature(
        secret=secret,
        payload=raw_body,
        signature_header=signature_header,
    )

    if not is_valid:
        get_audit_logger().log_security_event(
            event_type=SecurityEvent.SIGNATURE_INVALID,
            platform_code=platform_code,
            integration_id=str(integration.id),
            client_ip=_get_client_ip(request),
            details={"reason": error, "signature_format": signature_header[:30]},
        )
        raise HTTPException(
            status_code=401,
            detail=f"Signature verification failed: {error}"
        )

    return secret


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header first
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take first IP (original client)
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


@router.post(
    "/{platform_code}/{integration_id}",
    response_model=WebhookResponse,
    summary="Receive webhook from external platform",
    description="Main webhook ingestion endpoint for all platforms",
)
async def receive_webhook(
    request: Request,
    platform_code: str = Path(..., description="Platform code (e.g., basalam)"),
    integration_id: UUID = Path(..., description="Shop integration UUID"),
    session: AsyncSession = Depends(get_db),
):
    """
    Receive and process incoming webhook.

    Security chain:
    1. IP allowlist check
    2. Rate limiting
    3. Timestamp validation
    4. Signature verification
    5. Idempotency check
    6. Event processing
    """
    # Get raw body first (needed for signature verification)
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload"
        )

    # Get platform and integration
    platform, integration = await get_platform_and_integration(
        platform_code, integration_id, session
    )

    # Check integration is active
    if integration.status != "connected":
        raise HTTPException(
            status_code=403,
            detail=f"Integration status is '{integration.status}', not 'connected'"
        )

    # Security chain
    await validate_ip(request, platform, platform_code)
    await validate_rate_limit(platform_code, integration_id, platform)
    await validate_timestamp(request, payload, platform, platform_code)
    await verify_signature(request, raw_body, integration, platform_code)

    # Extract event metadata
    headers = dict(request.headers)
    event_type = (
        payload.get("event_type")
        or payload.get("event")
        or headers.get("X-Webhook-Event")
        or headers.get("X-Event-Type")
        or "unknown"
    )

    external_event_id = (
        payload.get("event_id")
        or payload.get("id")
        or headers.get("X-Event-Id")
        or headers.get("X-Request-Id")
    )

    # Idempotency check
    redis = get_redis_client()
    idempotency = IdempotencyManager(redis_client=redis, db_session=session)

    if external_event_id and await idempotency.check_duplicate(
        platform_id=str(platform.id),
        event_id=external_event_id,
        payload=payload,
    ):
        get_audit_logger().log_security_event(
            event_type=SecurityEvent.DUPLICATE_EVENT,
            platform_code=platform_code,
            integration_id=str(integration.id),
            client_ip=_get_client_ip(request),
            details={"event_id": external_event_id},
        )
        # Return success for duplicate (idempotent)
        return WebhookResponse(
            status="accepted",
            message="Duplicate event already processed",
            event_id=external_event_id,
        )

    # Create webhook event record
    async with UnitOfWork(session) as uow:
        event_repo = WebhookEventRepository(session)

        webhook_event = await event_repo.create({
            "platform_id": platform.id,
            "integration_id": integration.id,
            "event_type": event_type,
            "external_event_id": external_event_id or f"gen-{datetime.now(timezone.utc).timestamp()}",
            "payload": payload,
            "signature_verified": True,
            "status": "received",
        })

        await uow.commit()

    # Mark as processed in idempotency cache
    if external_event_id:
        await idempotency.mark_processed(
            platform_id=str(platform.id),
            event_id=external_event_id,
            payload=payload,
        )

    # Dispatch to processor
    processing_start = time_module.time()
    record_webhook_received(platform_code, event_type)

    # Build registry with processors wired to this session + secret
    secret_for_processor = (
        integration.webhook_secret_encrypted
        if integration.webhook_secret_encrypted
        else ""
    )
    processor_registry = _build_processor_registry(
        secret=secret_for_processor, session=session
    )

    # For Basalam, route by numeric event_id; for others, route by string event_type
    numeric_event_id = payload.get("event_id")
    if isinstance(numeric_event_id, int):
        processor = processor_registry.get(
            platform_id=platform_code, event_id=numeric_event_id
        )
    else:
        processor = processor_registry.get(
            platform_id=platform_code, event_type=event_type
        )

    if processor:
        try:
            success = await processor.process(payload, headers)
            duration = time_module.time() - processing_start
            if success:
                await event_repo.update_status(webhook_event.id, "completed")
                record_webhook_processed(platform_code, event_type, duration)
            else:
                # Schedule retry
                record_webhook_failed(platform_code, event_type, "processor_returned_false")
                scheduler = RetryScheduler(db_session=session)
                await scheduler.schedule_retry(
                    event_id=str(webhook_event.id),
                    attempt=0,
                    platform_id=str(platform.id),
                    event_type=event_type,
                    payload=payload,
                )
        except Exception as e:
            duration = time_module.time() - processing_start
            logger.error("webhook_processing_error", error=str(e))
            await event_repo.update_status(
                webhook_event.id,
                "failed",
                error_message=str(e),
            )
            record_webhook_failed(platform_code, event_type, type(e).__name__)
            # Schedule retry
            scheduler = RetryScheduler(db_session=session)
            await scheduler.schedule_retry(
                event_id=str(webhook_event.id),
                attempt=0,
                platform_id=str(platform.id),
                event_type=event_type,
                payload=payload,
            )
    else:
        logger.warning(
            "no_processor_registered",
            platform_code=platform_code,
            event_type=event_type,
            webhook_event_id=str(webhook_event.id),
        )

    return WebhookResponse(
        status="accepted",
        message="Webhook received and queued for processing",
        event_id=str(webhook_event.id),
    )
