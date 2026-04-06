"""
Product Sync Celery Tasks
=========================
Periodic product synchronization tasks.
"""
import asyncio
import structlog

from celery import shared_task

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
    """Sync products from Basalam for all active integrations."""
    logger.info("Starting product sync task")
    try:
        from src.core.database import async_session_maker
        from src.integrations.basalam.product_sync import ProductSyncService
        from src.integrations.basalam.client import BasalamClient
        from src.core.config import get_settings

        async def _sync():
            settings = get_settings()
            async with async_session_maker() as session:
                from sqlalchemy import select
                from src.domains.shops.models import ShopIntegration

                stmt = select(ShopIntegration).where(
                    ShopIntegration.status == "connected"
                )
                result = await session.execute(stmt)
                integrations = result.scalars().all()

                for integration in integrations:
                    try:
                        client = BasalamClient(
                            client_id=settings.basalam_client_id,
                            client_secret=settings.basalam_client_secret.get_secret_value(),
                        )
                        sync_service = ProductSyncService(
                            client=client,
                            session=session,
                            integration_id=integration.id,
                        )
                        await sync_service.sync_products()
                        logger.info("product_sync_completed_for_integration", integration_id=str(integration.id))
                    except Exception as e:
                        logger.error("product_sync_failed_for_integration", integration_id=str(integration.id), error=str(e))

        asyncio.run(_sync())
        logger.info("Product sync task completed")
    except Exception as exc:
        logger.error("product_sync_task_failed", error=str(exc))
        raise self.retry(exc=exc)
