"""
Sync Service
============
Business logic for sync job management
"""

from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository import SyncJobRepository, ShopIntegrationRepository, SyncStateRepository
from ..models import SyncJob, ShopIntegration
from src.core.repository.unit_of_work import UnitOfWork


class SyncService:
    """
    Service for managing sync jobs.

    Handles creating, running, scheduling, and managing sync operations.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize service with database session.

        Args:
            session: Async SQLAlchemy session for database operations
        """
        self.session = session
        self._sync_repository = SyncJobRepository(session)
        self._integration_repository = ShopIntegrationRepository(session)
        self._sync_state_repository = SyncStateRepository(session)

    async def _get_integration_or_fail(
        self, integration_id: uuid.UUID
    ) -> ShopIntegration:
        """
        Get integration by ID or raise ValueError if not found.

        Args:
            integration_id: UUID of the integration

        Returns:
            ShopIntegration instance

        Raises:
            ValueError: If integration not found
        """
        integration = await self._integration_repository.get_by_id(integration_id)
        if not integration:
            raise ValueError(f"Integration with id '{integration_id}' not found")
        return integration

    async def _get_job_or_fail(self, job_id: uuid.UUID) -> SyncJob:
        """
        Get sync job by ID or raise ValueError if not found.

        Args:
            job_id: UUID of the sync job

        Returns:
            SyncJob instance

        Raises:
            ValueError: If job not found
        """
        job = await self._sync_repository.get_by_id(job_id)
        if not job:
            raise ValueError(f"Sync job with id '{job_id}' not found")
        return job

    async def create_sync_job(
        self,
        integration_id: uuid.UUID,
        entity_type: str,
        entity_id: Optional[uuid.UUID] = None,
    ) -> SyncJob:
        """
        Create a new sync job.

        Args:
            integration_id: UUID of the integration
            entity_type: Type of entity to sync (product, inventory, order)
            entity_id: Optional UUID of specific entity to sync

        Returns:
            Newly created SyncJob instance

        Raises:
            ValueError: If integration not found
        """
        await self._get_integration_or_fail(integration_id)

        job_data = {
            "integration_id": integration_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": "pending",
            "retry_count": 0,
            "scheduled_at": datetime.now(timezone.utc),
        }

        async with UnitOfWork(self.session):
            return await self._sync_repository.create(job_data)

    async def run_sync(self, job_id: uuid.UUID) -> SyncJob:
        """
        Execute a sync job.

        Args:
            job_id: UUID of the sync job

        Returns:
            Updated SyncJob instance

        Raises:
            ValueError: If job not found or not in pending status
        """
        job = await self._get_job_or_fail(job_id)

        if job.status not in ("pending", "failed"):
            raise ValueError(
                f"Cannot run sync job in status '{job.status}'. "
                "Only 'pending' or 'failed' jobs can be executed."
            )

        await self._sync_repository.update_status(job_id, "running")

        job = await self._get_job_or_fail(job_id)
        job.started_at = datetime.now(timezone.utc)
        await self.session.flush()

        try:
            await self._perform_sync(job)

            await self._sync_repository.update_status(job_id, "completed")
            job = await self._get_job_or_fail(job_id)
            job.completed_at = datetime.now(timezone.utc)
            await self.session.flush()

        except Exception as e:
            await self._sync_repository.update_status(job_id, "failed")
            job = await self._get_job_or_fail(job_id)
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            await self.session.flush()
            raise

        return await self._get_job_or_fail(job_id)

    async def _perform_sync(self, job: SyncJob) -> None:
        """
        Perform the actual sync operation.

        This is a placeholder - actual sync logic would be implemented
        based on entity type and platform specifics.

        Args:
            job: SyncJob instance to execute
        """
        integration = await self._integration_repository.get_by_id(job.integration_id)

        if not integration:
            raise ValueError(
                f"Integration '{job.integration_id}' not found during sync"
            )

    async def schedule_sync(
        self,
        integration_id: uuid.UUID,
        entity_type: str,
        schedule_time: Optional[datetime] = None,
    ) -> SyncJob:
        """
        Schedule a sync job for later execution.

        Args:
            integration_id: UUID of the integration
            entity_type: Type of entity to sync
            schedule_time: Optional specific time to run sync (defaults to now)

        Returns:
            Newly created SyncJob instance

        Raises:
            ValueError: If integration not found
        """
        await self._get_integration_or_fail(integration_id)

        scheduled_at = schedule_time or datetime.now(timezone.utc)

        job_data = {
            "integration_id": integration_id,
            "entity_type": entity_type,
            "status": "pending",
            "retry_count": 0,
            "scheduled_at": scheduled_at,
        }

        async with UnitOfWork(self.session):
            return await self._sync_repository.create(job_data)

    async def get_sync_status(self, job_id: uuid.UUID) -> Dict[str, Any]:
        """
        Get sync job status and details.

        Args:
            job_id: UUID of the sync job

        Returns:
            Dictionary containing job status information

        Raises:
            ValueError: If job not found
        """
        job = await self._get_job_or_fail(job_id)

        return {
            "id": job.id,
            "integration_id": job.integration_id,
            "entity_type": job.entity_type,
            "entity_id": job.entity_id,
            "status": job.status,
            "retry_count": int(job.retry_count),
            "error_message": job.error_message,
            "scheduled_at": job.scheduled_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
        }

    async def get_sync_status_by_integration(
        self, integration_id: uuid.UUID, entity_type: str = "product"
    ) -> Dict[str, Any]:
        """
        Get sync status for an integration by fetching the latest job and state.

        Args:
            integration_id: UUID of the integration
            entity_type: Type of entity to get status for (default: product)

        Returns:
            Dictionary containing job and sync state status information

        Raises:
            ValueError: If integration not found or no sync history
        """
        await self._get_integration_or_fail(integration_id)

        # Get latest sync job for this integration and entity type
        job = await self._sync_repository.get_latest_by_integration(
            integration_id, entity_type
        )

        # Get sync state for this integration and entity type
        sync_state = await self._sync_state_repository.get_by_integration_and_type(
            integration_id, entity_type
        )

        result = {
            "id": None,
            "integration_id": integration_id,
            "entity_type": entity_type,
            "entity_id": None,
            "status": "never_run",
            "retry_count": 0,
            "error_message": None,
            "scheduled_at": None,
            "started_at": None,
            "completed_at": None,
            "created_at": None,
            # Sync state fields
            "sync_state_status": sync_state.status if sync_state else None,
            "sync_mode": sync_state.sync_mode if sync_state else None,
            "total_synced": sync_state.total_synced if sync_state else 0,
            "created_count": sync_state.created_count if sync_state else 0,
            "updated_count": sync_state.updated_count if sync_state else 0,
            "failed_count": sync_state.failed_count if sync_state else 0,
            "last_sync_timestamp": sync_state.last_sync_timestamp if sync_state else None,
        }

        if job:
            result.update({
                "id": job.id,
                "entity_id": job.entity_id,
                "status": job.status,
                "retry_count": int(job.retry_count) if job.retry_count else 0,
                "error_message": job.error_message,
                "scheduled_at": job.scheduled_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "created_at": job.created_at,
            })

        return result

    async def retry_failed_job(self, job_id: uuid.UUID) -> SyncJob:
        """
        Retry a failed sync job.

        Increments retry count and resets status to pending.

        Args:
            job_id: UUID of the sync job

        Returns:
            Updated SyncJob instance

        Raises:
            ValueError: If job not found or not in failed status
        """
        job = await self._get_job_or_fail(job_id)

        if job.status != "failed":
            raise ValueError(
                f"Cannot retry job in status '{job.status}'. "
                "Only 'failed' jobs can be retried."
            )

        async with UnitOfWork(self.session):
            await self._sync_repository.increment_retry(job_id)
            await self._sync_repository.update_status(job_id, "pending")

            job = await self._get_job_or_fail(job_id)
            job.error_message = None
            job.scheduled_at = datetime.now(timezone.utc)

        return await self._get_job_or_fail(job_id)

    async def cancel_job(self, job_id: uuid.UUID) -> SyncJob:
        """
        Cancel a pending sync job.

        Args:
            job_id: UUID of the sync job

        Returns:
            Updated SyncJob instance

        Raises:
            ValueError: If job not found or not in pending status
        """
        job = await self._get_job_or_fail(job_id)

        if job.status != "pending":
            raise ValueError(
                f"Cannot cancel job in status '{job.status}'. "
                "Only 'pending' jobs can be cancelled."
            )

        async with UnitOfWork(self.session):
            await self._sync_repository.update_status(job_id, "cancelled")

        return await self._get_job_or_fail(job_id)
