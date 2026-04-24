"""
Webhook Kafka Consumer
======================
Consumes webhook.received events and processes them directly.
Kafka DLQ is the single retry boundary — no Celery bridge needed.
"""

import structlog

from src.workers.consumers.base import DLQAwareConsumer, DLQConfig
from src.core.database import async_session_maker
from src.core.repository.unit_of_work import UnitOfWork
from src.integrations.webhooks.processors.base import WebhookProcessorRegistry
from src.integrations.webhooks.processors.product import ProductWebhookProcessor
from src.integrations.webhooks.processors.order import OrderWebhookProcessor
from src.integrations.webhooks.processors.inventory import InventoryWebhookProcessor
from src.integrations.webhooks.processors.payment import PaymentWebhookProcessor

logger = structlog.get_logger("workers.webhook_consumer")


class WebhookConsumer(DLQAwareConsumer):
    topic = "webhook.received"
    group_id = "webhook-processor"

    def __init__(self, bootstrap_servers: str):
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            dlq_config=DLQConfig(
                max_retries=3,
                retry_backoff_ms=(1000, 5000, 15000),
                processing_timeout_seconds=60,
            ),
        )

    @staticmethod
    def _build_registry(session) -> WebhookProcessorRegistry:
        """Build a processor registry wired to the given DB session."""
        registry = WebhookProcessorRegistry()
        product_proc = ProductWebhookProcessor(secret="", db_session=session)
        order_proc = OrderWebhookProcessor(secret="", db_session=session)
        inventory_proc = InventoryWebhookProcessor(secret="", db_session=session)
        payment_proc = PaymentWebhookProcessor(secret="", db_session=session)
        registry.register("basalam", "product.changes", product_proc)
        registry.register("basalam", "order.created", order_proc)
        registry.register("basalam", "order.parcel_changed", order_proc)
        registry.register("basalam", "inventory.changed", inventory_proc)
        registry.register("basalam", "payment.completed", payment_proc)
        registry.register("basalam", "payment.failed", payment_proc)
        return registry

    async def process_message(self, message) -> None:
        event = message.value
        if not isinstance(event, dict):
            raise ValueError(f"Expected dict message value, got {type(event).__name__}")

        event_type = event.get("event_type")
        webhook_id = event.get("webhook_id")
        platform_id = event.get("platform_id", "basalam")

        if not event_type:
            raise ValueError("Webhook event missing event_type — cannot route")

        logger.info(
            "Processing webhook event",
            event_type=event_type,
            webhook_id=str(webhook_id),
        )

        async with async_session_maker() as session:
            # Idempotency: skip if already successfully processed.
            if webhook_id:
                from src.integrations.webhooks.idempotency import (
                    IdempotencyManager,
                )

                idempotency = IdempotencyManager(db_session=session)
                try:
                    if await idempotency.is_processed(webhook_id):
                        logger.info("Duplicate webhook skipped", webhook_id=webhook_id)
                        return
                finally:
                    await idempotency.close()

            # Business logic runs inside its own UoW transaction.
            async with UnitOfWork(session):
                registry = self._build_registry(session)

                processor = registry.get(platform_id, event_type=event_type)

                if not processor:
                    raise ValueError(
                        f"No processor registered for platform '{platform_id}' "
                        f"and event_type '{event_type}'"
                    )

                success = await processor.process(event.get("data", {}), event.get("headers", {}))
                if not success:
                    raise ValueError(
                        f"Processor returned False for platform '{platform_id}' "
                        f"event_type '{event_type}'"
                    )

                logger.info(
                    "Webhook processed",
                    event_type=event_type,
                    webhook_id=str(webhook_id),
                )

            # Mark idempotency AFTER business logic succeeds so that
            # transient failures can be retried via the DLQ (max 3).
            if webhook_id:
                from src.integrations.webhooks.idempotency import (
                    IdempotencyManager,
                )

                idempotency = IdempotencyManager(db_session=session)
                try:
                    await idempotency.mark_processed(
                        webhook_id, result={"event_type": event_type}
                    )
                finally:
                    await idempotency.close()
