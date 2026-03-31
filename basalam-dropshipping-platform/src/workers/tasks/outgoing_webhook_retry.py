"""
Outgoing Webhook Retry Task
============================
Celery task for processing outgoing webhook retries with exponential backoff.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.workers.celery_config import celery_app
from src.core.database import async_session_maker
from src.domains.webhooks.models import (
    OutgoingWebhookLog,
    OutgoingWebhookDLQ,
    OutgoingWebhookStatus,
)


logger = logging.getLogger(__name__)

# Retry intervals in seconds: 1m, 5m, 15m, 1h, 6h
RETRY_INTERVALS = [60, 300, 900, 3600, 21600]
MAX_RETRIES = 5


@shared_task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=False,  # We handle backoff ourselves
    retry_jitter=False,
)
def process_webhook_retry(self, webhook_log_id: str):
    """
    Process a single webhook retry.

    Args:
        webhook_log_id: UUID of the OutgoingWebhookLog to retry

    Returns:
        Dict with result status
    """
    import asyncio

    return asyncio.run(_process_webhook_retry_async(webhook_log_id))


async def _process_webhook_retry_async(webhook_log_id: str) -> dict:
    """Async implementation of webhook retry processing."""
    async with async_session_maker() as session:
        try:
            # Get webhook log
            stmt = select(OutgoingWebhookLog).where(
                OutgoingWebhookLog.id == webhook_log_id
            )
            result = await session.execute(stmt)
            webhook_log = result.scalar_one_or_none()

            if not webhook_log:
                logger.error(f"Webhook log {webhook_log_id} not found")
                return {"status": "error", "error": "not_found"}

            # Check if already processed
            if webhook_log.status == OutgoingWebhookStatus.SENT.value:
                logger.info(f"Webhook {webhook_log_id} already sent")
                return {"status": "already_sent"}

            # Get retry count
            retry_count = webhook_log.retry_count or 0

            logger.info(
                f"Processing webhook retry {retry_count + 1}/{MAX_RETRIES} "
                f"for log {webhook_log_id}"
            )

            # Attempt to send
            success, error, status_code = await _send_webhook(
                url=webhook_log.url,
                payload=webhook_log.payload,
            )

            if success:
                # Mark as sent
                stmt = (
                    update(OutgoingWebhookLog)
                    .where(OutgoingWebhookLog.id == webhook_log_id)
                    .values(
                        status=OutgoingWebhookStatus.SENT.value,
                        last_attempt_at=datetime.utcnow(),
                        response_status_code=status_code,
                        last_error=None,
                    )
                )
                await session.execute(stmt)
                await session.commit()

                logger.info(f"Webhook {webhook_log_id} sent successfully")
                return {"status": "sent"}

            # Failed - check if we should retry
            if status_code and 400 <= status_code < 500:
                # Client error - don't retry, move to DLQ
                await _move_to_dlq(
                    session=session,
                    webhook_log=webhook_log,
                    failure_reason=error or f"HTTP {status_code}",
                )
                return {"status": "failed", "error": error, "moved_to_dlq": True}

            if retry_count + 1 >= MAX_RETRIES:
                # Max retries exceeded - move to DLQ
                await _move_to_dlq(
                    session=session,
                    webhook_log=webhook_log,
                    failure_reason=error or "Max retries exceeded",
                )
                return {"status": "failed", "error": error, "moved_to_dlq": True}

            # Schedule next retry
            next_retry_count = retry_count + 1
            next_retry_at = datetime.utcnow() + timedelta(
                seconds=RETRY_INTERVALS[min(next_retry_count, len(RETRY_INTERVALS) - 1)]
            )

            stmt = (
                update(OutgoingWebhookLog)
                .where(OutgoingWebhookLog.id == webhook_log_id)
                .values(
                    status=OutgoingWebhookStatus.RETRYING.value,
                    retry_count=next_retry_count,
                    last_attempt_at=datetime.utcnow(),
                    next_retry_at=next_retry_at,
                    last_error=error[:500] if error else None,
                    response_status_code=status_code,
                )
            )
            await session.execute(stmt)
            await session.commit()

            logger.info(
                f"Scheduled retry {next_retry_count}/{MAX_RETRIES} "
                f"for webhook {webhook_log_id} at {next_retry_at}"
            )

            return {
                "status": "retrying",
                "next_retry_at": next_retry_at.isoformat(),
                "error": error,
            }

        except Exception as e:
            logger.error(f"Error processing webhook retry {webhook_log_id}: {e}")
            return {"status": "error", "error": str(e)}


async def _send_webhook(
    url: str,
    payload: dict,
    timeout: float = 30.0,
) -> tuple[bool, Optional[str], Optional[int]]:
    """
    Send webhook to external URL.

    Returns:
        Tuple of (success, error_message, status_code)
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)

            if response.status_code in [200, 201, 202, 204]:
                return True, None, response.status_code

            error = f"HTTP {response.status_code}: {response.text[:200]}"
            return False, error, response.status_code

    except httpx.TimeoutException:
        return False, "Request timeout", None

    except httpx.ConnectError as e:
        return False, f"Connection error: {str(e)}", None

    except Exception as e:
        return False, str(e), None


async def _move_to_dlq(
    session: AsyncSession,
    webhook_log: OutgoingWebhookLog,
    failure_reason: str,
):
    """Move failed webhook to dead letter queue."""
    # Update webhook log status
    stmt = (
        update(OutgoingWebhookLog)
        .where(OutgoingWebhookLog.id == webhook_log.id)
        .values(
            status=OutgoingWebhookStatus.FAILED.value,
            last_attempt_at=datetime.utcnow(),
            last_error=failure_reason[:500] if failure_reason else None,
        )
    )
    await session.execute(stmt)

    # Create DLQ entry
    dlq_entry = OutgoingWebhookDLQ(
        outgoing_webhook_log_id=webhook_log.id,
        failure_reason=failure_reason[:1000] if failure_reason else "Unknown error",
        failure_count=webhook_log.retry_count or MAX_RETRIES,
        status="pending",
    )
    session.add(dlq_entry)

    await session.commit()

    logger.warning(f"Moved webhook {webhook_log.id} to dead letter queue")


@shared_task
def process_pending_retries():
    """
    Process all pending webhook retries that are due.

    This task is typically called by Celery beat every minute.
    """
    import asyncio
    return asyncio.run(_process_pending_retries_async())


async def _process_pending_retries_async() -> dict:
    """Async implementation of pending retries processing."""
    async with async_session_maker() as session:
        now = datetime.utcnow()

        # Find webhooks that need retry
        stmt = select(OutgoingWebhookLog.id).where(
            OutgoingWebhookLog.status == OutgoingWebhookStatus.RETRYING.value,
            OutgoingWebhookLog.next_retry_at <= now,
        ).limit(100)  # Process in batches

        result = await session.execute(stmt)
        webhook_ids = [str(row[0]) for row in result.fetchall()]

        if not webhook_ids:
            return {"status": "success", "processed": 0}

        # Queue each webhook for processing
        for webhook_id in webhook_ids:
            process_webhook_retry.delay(webhook_id)

        logger.info(f"Queued {len(webhook_ids)} webhooks for retry processing")

        return {"status": "success", "processed": len(webhook_ids)}


@shared_task
def cleanup_old_webhook_logs():
    """
    Clean up old webhook logs and DLQ entries.

    Removes entries older than 30 days.
    """
    import asyncio
    return asyncio.run(_cleanup_old_webhook_logs_async())


async def _cleanup_old_webhook_logs_async() -> dict:
    """Async implementation of webhook logs cleanup."""
    from sqlalchemy import delete

    async with async_session_maker() as session:
        cutoff = datetime.utcnow() - timedelta(days=30)

        # Delete old sent webhooks
        stmt = delete(OutgoingWebhookLog).where(
            OutgoingWebhookLog.status == OutgoingWebhookStatus.SENT.value,
            OutgoingWebhookLog.created_at < cutoff,
        )
        result = await session.execute(stmt)
        sent_deleted = result.rowcount

        # Delete old resolved DLQ entries
        stmt = delete(OutgoingWebhookDLQ).where(
            OutgoingWebhookDLQ.status == "resolved",
            OutgoingWebhookDLQ.created_at < cutoff,
        )
        result = await session.execute(stmt)
        dlq_deleted = result.rowcount

        await session.commit()

        logger.info(f"Cleaned up {sent_deleted} sent webhooks and {dlq_deleted} DLQ entries")

        return {
            "status": "success",
            "sent_deleted": sent_deleted,
            "dlq_deleted": dlq_deleted,
        }
