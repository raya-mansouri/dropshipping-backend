"""
Celery Tasks for Incoming Webhook Processing
=============================================
Executes webhook processing synchronously. Retry is handled by the
Kafka DLQ in WebhookConsumer — not here.

IMPORTANT: This task is designed to be called ONLY from within
WebhookConsumer as a fallback path. Do not dispatch it independently
or webhook failures will be permanently lost (max_retries=0).
"""

import structlog
from celery import shared_task

from src.workers.celery_config import run_async

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    name="src.workers.tasks.webhook_tasks.process_incoming_webhook",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_incoming_webhook(
    self,
    event_type: str,
    webhook_id: str = None,
    payload: dict = None,
    platform_id: str = "basalam",
):
    """Process an incoming webhook event.

    No Celery retries — the Kafka DLQ in WebhookConsumer handles retries.
    Any exception propagates back via result.get() to the Kafka consumer.
    """
    try:
        run_async(_process(event_type, webhook_id, payload or {}, platform_id))
    except Exception as exc:
        logger.error(
            "webhook_processing_failed",
            event_type=event_type,
            webhook_id=str(webhook_id),
            error=str(exc),
        )
        raise


async def _process(event_type: str, webhook_id: str, payload: dict, platform_id: str):
    from src.core.database import async_session_maker
    from src.core.repository.unit_of_work import UnitOfWork

    async with async_session_maker() as session:
        async with UnitOfWork(session):
            # Idempotency check — uses its own isolated DB session so the
            # idempotency record survives a business-logic rollback.
            idempotency = None
            if webhook_id:
                from src.integrations.webhooks.idempotency import IdempotencyManager

                idempotency = IdempotencyManager(db_session=session)
                try:
                    if await idempotency.is_processed(webhook_id):
                        logger.info("Duplicate webhook skipped", webhook_id=webhook_id)
                        return
                finally:
                    await idempotency.close()

            # Get processor and process
            from src.integrations.webhooks.processors.base import (
                WebhookProcessorRegistry,
            )
            from src.integrations.webhooks.processors.product import (
                ProductWebhookProcessor,
            )
            from src.integrations.webhooks.processors.order import (
                OrderWebhookProcessor,
            )
            from src.integrations.webhooks.processors.inventory import (
                InventoryWebhookProcessor,
            )

            # Build registry with processors wired to this session.
            # Signature verification was already performed by the API layer
            # before dispatching this task, so secret is not needed here.
            registry = WebhookProcessorRegistry()
            product_proc = ProductWebhookProcessor(secret="", db_session=session)
            order_proc = OrderWebhookProcessor(secret="", db_session=session)
            inventory_proc = InventoryWebhookProcessor(secret="", db_session=session)
            registry.register("basalam", "product.changes", product_proc)
            registry.register("basalam", "order.created", order_proc)
            registry.register("basalam", "order.parcel_changed", order_proc)
            registry.register("basalam", "inventory.changed", inventory_proc)

            processor = registry.get(platform_id, event_type=event_type)

            if not processor:
                raise ValueError(
                    f"No processor registered for platform '{platform_id}' "
                    f"and event_type '{event_type}'"
                )

            await processor.process(payload, {})

            # Record as processed after successful handling
            if webhook_id:
                idempotency = IdempotencyManager(db_session=session)
                try:
                    await idempotency.mark_processed(
                        webhook_id, result={"event_type": event_type}
                    )
                finally:
                    await idempotency.close()

            logger.info(
                "Webhook processed via Celery",
                event_type=event_type,
                webhook_id=str(webhook_id),
            )
