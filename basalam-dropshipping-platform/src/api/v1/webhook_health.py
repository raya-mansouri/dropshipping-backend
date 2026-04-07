"""
Webhook Health Monitoring Endpoints
====================================
Health check and metrics endpoints for webhook system status.
"""
import structlog
from typing import Optional, Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.domains.accounts.models import User


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhook Health"])


class WebhookHealthResponse(BaseModel):
    """Webhook health status response"""
    status: str  # healthy, degraded, unhealthy
    incoming: Dict[str, Any]
    outgoing: Dict[str, Any]
    integrations: Dict[str, Any]
    issues: Optional[List[str]] = None


class IntegrationWebhookStatus(BaseModel):
    """Webhook status for a single integration"""
    integration_id: str
    platform_code: str
    webhook_status: str
    webhook_registered_at: Optional[str]
    last_webhook_at: Optional[str]
    webhooks_processed: int
    webhooks_failed: int
    success_rate: float


class OutgoingDLQEntry(BaseModel):
    """Outgoing webhook DLQ entry"""
    id: str
    integration_id: str
    event_type: str
    url: str
    failure_reason: str
    failure_count: int
    created_at: str
    status: str


@router.get(
    "/health",
    response_model=WebhookHealthResponse,
    summary="Get webhook system health",
    description="Returns aggregated health metrics for the webhook system",
)
async def get_webhook_health(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get overall webhook system health status.

    Returns incoming/outgoing metrics and any detected issues.
    """
    # Query incoming webhook stats
    incoming_result = await session.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '5 minutes') as received_5m,
            COUNT(*) FILTER (WHERE status = 'completed' AND created_at > NOW() - INTERVAL '5 minutes') as processed_5m,
            COUNT(*) FILTER (WHERE status = 'failed' AND created_at > NOW() - INTERVAL '5 minutes') as failed_5m,
            COUNT(*) FILTER (WHERE status = 'dlq') as dlq_size,
            AVG(EXTRACT(EPOCH FROM (processed_at - created_at))) FILTER (
                WHERE status = 'completed' AND processed_at IS NOT NULL
            ) as avg_processing_seconds
        FROM webhook_events
    """))
    incoming_stats = incoming_result.fetchone()

    # Query outgoing webhook stats
    outgoing_result = await session.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'sent' AND created_at > NOW() - INTERVAL '5 minutes') as sent_5m,
            COUNT(*) FILTER (WHERE status = 'failed' AND created_at > NOW() - INTERVAL '5 minutes') as failed_5m,
            COUNT(*) FILTER (WHERE status IN ('pending', 'retrying')) as pending_count,
            COUNT(*) FILTER (WHERE status = 'dlq') as dlq_size
        FROM outgoing_webhook_logs
    """))
    outgoing_stats = outgoing_result.fetchone()

    # Query integration stats
    integration_result = await session.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE webhook_status = 'active') as webhooks_active,
            COUNT(*) FILTER (WHERE webhook_status = 'inactive') as webhooks_inactive,
            COUNT(*) FILTER (WHERE webhook_status = 'not_registered') as not_registered,
            COUNT(*) FILTER (WHERE webhook_status = 'cleanup_failed') as cleanup_failed
        FROM shop_integrations
        WHERE status = 'connected'
    """))
    integration_stats = integration_result.fetchone()

    # Calculate health status
    issues = []

    # Check incoming failure rate
    incoming_received = incoming_stats[0] or 0
    incoming_failed = incoming_stats[2] or 0
    failure_rate = (incoming_failed / incoming_received * 100) if incoming_received > 0 else 0

    if failure_rate > 10:
        issues.append(f"High incoming webhook failure rate: {failure_rate:.1f}%")

    # Check DLQ sizes
    incoming_dlq = incoming_stats[3] or 0
    outgoing_dlq = outgoing_stats[3] or 0

    if incoming_dlq > 100:
        issues.append(f"Large incoming DLQ size: {incoming_dlq}")

    if outgoing_dlq > 50:
        issues.append(f"Large outgoing DLQ size: {outgoing_dlq}")

    # Check pending outgoing
    pending_outgoing = outgoing_stats[2] or 0
    if pending_outgoing > 500:
        issues.append(f"High pending outgoing webhook count: {pending_outgoing}")

    # Check cleanup failures
    cleanup_failed = integration_stats[4] or 0
    if cleanup_failed > 0:
        issues.append(f"{cleanup_failed} integrations with webhook cleanup failures")

    # Determine status
    if not issues:
        status = "healthy"
    elif len(issues) <= 2 and failure_rate < 30:
        status = "degraded"
    else:
        status = "unhealthy"

    return WebhookHealthResponse(
        status=status,
        incoming={
            "last_5min": {
                "received": incoming_received,
                "processed": incoming_stats[1] or 0,
                "failed": incoming_failed,
            },
            "dlq_size": incoming_dlq,
            "avg_processing_seconds": round(incoming_stats[4] or 0, 3),
            "failure_rate_percent": round(failure_rate, 2),
        },
        outgoing={
            "last_5min": {
                "sent": outgoing_stats[0] or 0,
                "failed": outgoing_stats[1] or 0,
            },
            "pending_count": pending_outgoing,
            "dlq_size": outgoing_dlq,
        },
        integrations={
            "total": integration_stats[0] or 0,
            "webhooks_active": integration_stats[1] or 0,
            "webhooks_inactive": integration_stats[2] or 0,
            "not_registered": integration_stats[3] or 0,
            "cleanup_failed": cleanup_failed,
        },
        issues=issues if issues else None,
    )


@router.get(
    "/integrations/{integration_id}/status",
    response_model=IntegrationWebhookStatus,
    summary="Get webhook status for integration",
)
async def get_integration_webhook_status(
    integration_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get webhook status for a specific integration."""
    # Get integration with platform info
    result = await session.execute(text("""
        SELECT
            si.id,
            si.webhook_status,
            si.webhook_registered_at,
            p.code as platform_code,
            (
                SELECT MAX(created_at)
                FROM webhook_events
                WHERE integration_id = si.id
            ) as last_webhook_at,
            (
                SELECT COUNT(*)
                FROM webhook_events
                WHERE integration_id = si.id AND status = 'completed'
            ) as webhooks_processed,
            (
                SELECT COUNT(*)
                FROM webhook_events
                WHERE integration_id = si.id AND status IN ('failed', 'dlq')
            ) as webhooks_failed
        FROM shop_integrations si
        JOIN platforms p ON p.id = si.platform_id
        WHERE si.id = :integration_id
    """), {"integration_id": str(integration_id)})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")

    processed = row[5] or 0
    failed = row[6] or 0
    total = processed + failed
    success_rate = (processed / total * 100) if total > 0 else 100.0

    return IntegrationWebhookStatus(
        integration_id=str(row[0]),
        platform_code=row[3],
        webhook_status=row[1],
        webhook_registered_at=str(row[2]) if row[2] else None,
        last_webhook_at=str(row[4]) if row[4] else None,
        webhooks_processed=processed,
        webhooks_failed=failed,
        success_rate=round(success_rate, 2),
    )


@router.get(
    "/outgoing/dlq",
    response_model=List[OutgoingDLQEntry],
    summary="List outgoing webhook DLQ entries",
)
async def list_outgoing_dlq(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: str = Query("pending", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List entries in the outgoing webhook dead letter queue."""
    result = await session.execute(text("""
        SELECT
            id,
            integration_id,
            failure_reason,
            failure_count,
            created_at,
            status
        FROM outgoing_webhook_dlq
        WHERE status = :status
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), {"status": status, "limit": limit, "offset": offset})

    entries = []
    for row in result.fetchall():
        # Get the related webhook log for more details
        log_result = await session.execute(text("""
            SELECT event_type, url
            FROM outgoing_webhook_logs
            WHERE id = (
                SELECT outgoing_webhook_log_id
                FROM outgoing_webhook_dlq
                WHERE id = :dlq_id
            )
        """), {"dlq_id": str(row[0])})
        log_row = log_result.fetchone()

        entries.append(OutgoingDLQEntry(
            id=str(row[0]),
            integration_id=str(row[1]),
            event_type=log_row[0] if log_row else "unknown",
            url=log_row[1] if log_row else "unknown",
            failure_reason=row[2] or "Unknown error",
            failure_count=row[3] or 0,
            created_at=str(row[4]),
            status=row[5],
        ))

    return entries


@router.post(
    "/outgoing/dlq/{dlq_id}/retry",
    summary="Retry a DLQ entry",
)
async def retry_dlq_entry(
    dlq_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually retry a failed webhook from the DLQ."""
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get DLQ entry
    result = await session.execute(text("""
        SELECT id, outgoing_webhook_log_id, status
        FROM outgoing_webhook_dlq
        WHERE id = :dlq_id
    """), {"dlq_id": str(dlq_id)})

    dlq_entry = result.fetchone()
    if not dlq_entry:
        raise HTTPException(status_code=404, detail="DLQ entry not found")

    # Reset webhook log for retry
    await session.execute(text("""
        UPDATE outgoing_webhook_logs
        SET status = 'pending',
            retry_count = 0,
            next_retry_at = NOW()
        WHERE id = :log_id
    """), {"log_id": str(dlq_entry[1])})

    # Mark DLQ entry as resolved
    await session.execute(text("""
        UPDATE outgoing_webhook_dlq
        SET status = 'resolved',
            resolved_at = NOW(),
            resolution_notes = 'Manual retry initiated'
        WHERE id = :dlq_id
    """), {"dlq_id": str(dlq_id)})

    await session.commit()

    return {"status": "retry_scheduled", "dlq_id": str(dlq_id)}


@router.delete(
    "/outgoing/dlq/{dlq_id}",
    summary="Remove a DLQ entry",
)
async def remove_dlq_entry(
    dlq_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an entry from the outgoing webhook DLQ."""
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await session.execute(text("""
        DELETE FROM outgoing_webhook_dlq
        WHERE id = :dlq_id
        RETURNING id
    """), {"dlq_id": str(dlq_id)})

    deleted = result.fetchone()
    if not deleted:
        raise HTTPException(status_code=404, detail="DLQ entry not found")

    await session.commit()

    return {"status": "deleted", "dlq_id": str(dlq_id)}
