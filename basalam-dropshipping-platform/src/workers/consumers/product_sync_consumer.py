"""
Product Sync Kafka Consumer
============================
Consumes ProductSyncRequested events and runs ProductSyncService
with properly loaded integration credentials.

Replaces the Celery product_sync task with a Kafka-driven approach.
"""

import uuid
import structlog
from typing import Optional
from datetime import datetime, timezone

from src.workers.consumers.base import DLQAwareConsumer, DLQConfig
from src.core.database import async_session_maker
from src.core.config import get_settings

logger = structlog.get_logger("workers.product_sync_consumer")


class ProductSyncConsumer(DLQAwareConsumer):
    """Consumes ProductSyncRequested events and syncs products from Basalam."""

    topic = "sync.requested"
    group_id = "product-sync-consumer-group"

    def __init__(self, bootstrap_servers: str):
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            dlq_config=DLQConfig(
                max_retries=3,
                retry_backoff_ms=(5000, 30000, 120000),
                processing_timeout_seconds=600,  # Sync can take a while
            ),
        )

    async def _update_job_status(
        self,
        job_id: Optional[str],
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update SyncJob lifecycle status if job_id is present.

        Returns True if update succeeded, False otherwise.
        Failures are logged but never raise — callers must check the
        return value to preserve the *original* error when both sync and
        status-update fail.
        """
        if not job_id:
            return False

        from src.domains.shops.repository.sync_job import SyncJobRepository
        from src.core.repository.unit_of_work import UnitOfWork

        try:
            async with async_session_maker() as session:
                async with UnitOfWork(session):
                    repo = SyncJobRepository(session)
                    await repo.update_job_lifecycle(
                        id=uuid.UUID(job_id),
                        status=status,
                        started_at=started_at,
                        completed_at=completed_at,
                        error_message=error_message,
                    )
                    return True
        except Exception as e:
            logger.error(
                "failed_to_update_job_status",
                job_id=job_id,
                target_status=status,
                error=str(e),
                error_class=type(e).__name__,
            )
            return False

    async def process_message(self, message) -> None:
        event = message.value
        if not isinstance(event, dict):
            raise ValueError(f"Expected dict message value, got {type(event).__name__}")

        event_type = event.get("event_type")

        if event_type != "ProductSyncRequested":
            logger.warning("unexpected_event_type", event_type=event_type)
            return

        metadata = event.get("metadata", {})
        integration_id = metadata.get("integration_id")
        full_sync = metadata.get("full_sync", False)
        triggered_by = metadata.get("triggered_by", "unknown")
        job_id = metadata.get("job_id")

        if not integration_id:
            raise ValueError("ProductSyncRequested event missing integration_id")

        logger.info(
            "processing_product_sync",
            integration_id=integration_id,
            full_sync=full_sync,
            triggered_by=triggered_by,
            job_id=job_id,
        )

        # Mark job as running
        await self._update_job_status(
            job_id, "running", started_at=datetime.now(timezone.utc)
        )

        try:
            await self._sync_integration(integration_id, full_sync)
        except Exception as e:
            # Mark job as failed
            await self._update_job_status(
                job_id,
                "failed",
                completed_at=datetime.now(timezone.utc),
                error_message=str(e)[:2000],
            )
            raise

        # Mark job as completed
        await self._update_job_status(
            job_id, "completed", completed_at=datetime.now(timezone.utc)
        )

    async def _sync_integration(self, integration_id: str, full_sync: bool) -> None:
        """Load integration, read credentials, and run product sync."""
        from sqlalchemy import select
        from src.domains.shops.models import ShopIntegration
        from src.integrations.basalam.client import BasalamClient
        from src.integrations.basalam.product_sync import ProductSyncService
        from src.core.repository.unit_of_work import UnitOfWork

        settings = get_settings()

        async with async_session_maker() as session:
            async with UnitOfWork(session):
                # Load integration
                stmt = select(ShopIntegration).where(
                    ShopIntegration.id == integration_id,
                    ShopIntegration.status == "connected",
                )
                result = await session.execute(stmt)
                integration = result.scalar_one_or_none()

                if not integration:
                    raise ValueError(
                        f"No connected integration found for id {integration_id}"
                    )

                creds = integration.credentials or {}
                access_token = creds.get("access_token", "")
                refresh_token = creds.get("refresh_token", "")

                if not access_token:
                    raise ValueError(
                        f"No access_token in credentials for integration {integration_id}"
                    )

                client = BasalamClient(
                    client_id=settings.basalam_client_id,
                    client_secret=settings.basalam_client_secret.get_secret_value(),
                    access_token=access_token,
                    refresh_token=refresh_token,
                )

                try:
                    sync_service = ProductSyncService(
                        session=session,
                        client=client,
                        integration_id=integration.id,
                    )
                    sync_result = await sync_service.sync_products(full_sync=full_sync)

                    logger.info(
                        "product_sync_completed",
                        integration_id=integration_id,
                        fetched=sync_result.total_fetched,
                        created=sync_result.created_count,
                        updated=sync_result.updated_count,
                        failed=sync_result.failed_count,
                    )
                finally:
                    await client.close()
