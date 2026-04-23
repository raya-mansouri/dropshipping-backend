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

    async def process_message(self, message) -> None:
        event = message.value
        if not isinstance(event, dict):
            raise ValueError(f"Expected dict message value, got {type(event).__name__}")

        event_type = event.get("event_type")
        webhook_id = event.get("webhook_id")

        if not event_type:
            raise ValueError("Webhook event missing event_type — cannot route")

        logger.info(
            "Processing webhook event",
            event_type=event_type,
            webhook_id=str(webhook_id),
        )

        async with async_session_maker() as session:
            # Idempotency: check-then-mark *before* business logic so the
            # record survives a rollback.  The IdempotencyManager uses its
            # own isolated DB session, committing independently of the UoW.
            if webhook_id:
                from src.integrations.webhooks.idempotency import (
                    IdempotencyManager,
                )

                idempotency = IdempotencyManager(db_session=session)
                try:
                    if await idempotency.is_processed(webhook_id):
                        logger.info("Duplicate webhook skipped", webhook_id=webhook_id)
                        return
                    # Mark processed immediately so the record is committed
                    # to the isolated session *before* any business logic runs.
                    # If business logic fails the idempotency record persists
                    # and prevents infinite retries.
                    await idempotency.mark_processed(
                        webhook_id, result={"event_type": event_type}
                    )
                finally:
                    await idempotency.close()

            # Business logic runs inside its own UoW transaction.
            async with UnitOfWork(session):
                from src.integrations.webhooks.processors.base import (
                    WebhookProcessorRegistry,
                )

                registry = WebhookProcessorRegistry()
                processor = registry.get_processor(event_type)

                if not processor:
                    raise ValueError(
                        f"No processor registered for event_type '{event_type}'"
                    )

                await processor.process(event.get("data", {}))

                logger.info(
                    "Webhook processed",
                    event_type=event_type,
                    webhook_id=str(webhook_id),
                )
