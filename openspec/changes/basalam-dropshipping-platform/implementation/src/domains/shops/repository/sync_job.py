"""
Sync Job Repository
==================
Repository for SyncJob model operations
"""

from typing import Optional, List
from datetime import datetime
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import Base

from ..models import SyncJob


class SyncJobRepository:
    """
    Repository for managing SyncJob entities.

    Handles database operations for sync job records
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[SyncJob]:
        """
        Get sync job by its UUID.

        Args:
            id: Sync job UUID

        Returns:
            SyncJob instance if found, None otherwise
        """
        result = await self.session.execute(select(SyncJob).where(SyncJob.id == id))
        return result.scalar_one_or_none()

    async def get_by_integration(self, integration_id: uuid.UUID) -> List[SyncJob]:
        """
        Get all sync jobs for a specific integration.

        Args:
            integration_id: Integration UUID

        Returns:
            List of SyncJob instances for the integration
        """
        result = await self.session.execute(
            select(SyncJob).where(SyncJob.integration_id == integration_id)
        )
        return list(result.scalars().all())

    async def get_pending(self, since: Optional[datetime] = None) -> List[SyncJob]:
        """
        Get pending sync jobs, optionally filtered by scheduled time.

        Args:
            since: Optional datetime to filter jobs scheduled after this time

        Returns:
            List of pending SyncJob instances
        """
        query = select(SyncJob).where(SyncJob.status == "pending")

        if since is not None:
            query = query.where(SyncJob.scheduled_at <= since)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: dict) -> SyncJob:
        """
        Create a new sync job.

        Args:
            data: Dictionary containing sync job fields

        Returns:
            Newly created SyncJob instance
        """
        sync_job = SyncJob(**data)
        self.session.add(sync_job)
        await self.session.flush()
        await self.session.refresh(sync_job)
        return sync_job

    async def update_status(self, id: uuid.UUID, status: str) -> Optional[SyncJob]:
        """
        Update sync job status.

        Args:
            id: Sync job UUID
            status: New status ('pending', 'running', 'completed', 'failed')

        Returns:
            Updated SyncJob instance if found, None otherwise
        """
        await self.session.execute(
            update(SyncJob).where(SyncJob.id == id).values(status=status)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def increment_retry(self, id: uuid.UUID) -> Optional[SyncJob]:
        """
        Increment the retry count for a sync job.

        Args:
            id: Sync job UUID

        Returns:
            Updated SyncJob instance if found, None otherwise
        """
        result = await self.session.execute(select(SyncJob).where(SyncJob.id == id))
        job = result.scalar_one_or_none()

        if job:
            new_retry_count = int(job.retry_count) + 1
            await self.session.execute(
                update(SyncJob)
                .where(SyncJob.id == id)
                .values(retry_count=str(new_retry_count))
            )
            await self.session.flush()

        return await self.get_by_id(id)
