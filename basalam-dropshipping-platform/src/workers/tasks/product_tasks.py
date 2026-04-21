"""
Product Sync Celery Tasks
=========================
Celery beat task that publishes ProductSyncRequested Kafka events
for all active integrations. The actual sync is performed by
ProductSyncConsumer (Kafka consumer).
"""

import structlog
from uuid import UUID

from celery import shared_task

from src.workers.celery_config import run_async

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    name="src.workers.tasks.product_tasks.product_sync",
    max_retries=3,
    default_retry_delay=300,
    retry_jitter=True,
    acks_late=True,
)
def product_sync(self):
    """Publish ProductSyncRequested events for all active integrations."""
    logger.info("Starting scheduled product sync event dispatch")
    try:

        async def _publish():
            from src.core.database import async_session_maker
            from src.core.events import ProductSyncRequested
            from src.core.events.publisher import EventPublisher
            from src.core.config import get_settings
            from sqlalchemy import select
            from src.domains.shops.models import ShopIntegration

            settings = get_settings()
            publisher = EventPublisher(
                kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
            )

            try:
                async with async_session_maker() as session:
                    stmt = select(ShopIntegration).where(
                        ShopIntegration.status == "connected",
                    )
                    result = await session.execute(stmt)
                    integrations = result.scalars().all()

                    for integration in integrations:
                        try:
                            event = ProductSyncRequested(
                                integration_id=integration.id,
                                full_sync=False,
                                triggered_by="scheduled",
                            )
                            await publisher.publish(
                                topic="sync.requested",
                                event=event,
                                route_by_type=True,
                            )
                            logger.info(
                                "scheduled_sync_event_published",
                                integration_id=str(integration.id),
                            )
                        except Exception as pub_err:
                            logger.error(
                                "sync_event_publish_failed_stopping",
                                integration_id=str(integration.id),
                                error=str(pub_err),
                            )
                            raise

                logger.info(
                    "scheduled_sync_dispatch_complete",
                    integration_count=len(integrations),
                )
            finally:
                await publisher.close()

        run_async(_publish())
    except Exception as exc:
        logger.error("product_sync_dispatch_failed", error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="src.workers.tasks.product_tasks.publish_sync_event",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def publish_sync_event(self, integration_id: str, triggered_by: str = "oauth_callback"):
    """Publish a ProductSyncRequested event for a single integration.

    Used as a Celery fallback when direct Kafka publish fails (e.g. during
    OAuth callback). Celery's own retry mechanism handles transient broker
    outages.
    """
    try:

        async def _publish_single():
            from src.core.events import ProductSyncRequested
            from src.core.events.publisher import EventPublisher
            from src.core.config import get_settings

            settings = get_settings()
            publisher = EventPublisher(
                kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
            )
            try:
                event = ProductSyncRequested(
                    integration_id=UUID(integration_id),
                    full_sync=True,
                    triggered_by=triggered_by,
                )
                await publisher.publish(
                    topic="sync.requested",
                    event=event,
                    route_by_type=True,
                )
                logger.info(
                    "sync_event_published_via_celery",
                    integration_id=integration_id,
                    triggered_by=triggered_by,
                )
            finally:
                await publisher.close()

        run_async(_publish_single())
    except Exception as exc:
        logger.error(
            "sync_event_publish_failed",
            integration_id=integration_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)
