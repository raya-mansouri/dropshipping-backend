"""
Sync Job Repository
==================
Repository for SyncJob model operations, extending BaseRepository.
"""

from typing import Optional, List
from datetime import datetime
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository.base import BaseRepository
from ..models import SyncJob


class SyncJobRepository(BaseRepository[SyncJob]):
    """
    Repository for managing SyncJob entities.

    Extends BaseRepository for CRUD, QueryBuilder, pagination, and audit trail.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, SyncJob)

    async def get_by_integration(self, integration_id: uuid.UUID) -> List[SyncJob]:
        """Get all sync jobs for a specific integration."""
        result = await self.session.execute(
            select(SyncJob).where(SyncJob.integration_id == integration_id)
        )
        return list(result.scalars().all())

    async def get_pending(self, since: Optional[datetime] = None) -> List[SyncJob]:
        """Get pending sync jobs, optionally filtered by scheduled time."""
        query = select(SyncJob).where(SyncJob.status == "pending")

        if since is not None:
            query = query.where(SyncJob.scheduled_at <= since)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(self, id: uuid.UUID, status: str) -> Optional[SyncJob]:
        """Update sync job status."""
        await self.session.execute(
            update(SyncJob).where(SyncJob.id == id).values(status=status)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def increment_retry(self, id: uuid.UUID) -> Optional[SyncJob]:
        """Increment the retry count for a sync job."""
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

    async def get_latest_by_integration(
        self, integration_id: uuid.UUID, entity_type: str
    ) -> Optional[SyncJob]:
        """Get the latest sync job for a specific integration and entity type."""
        result = await self.session.execute(
            select(SyncJob)
            .where(
                SyncJob.integration_id == integration_id,
                SyncJob.entity_type == entity_type,
            )
            .order_by(SyncJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
