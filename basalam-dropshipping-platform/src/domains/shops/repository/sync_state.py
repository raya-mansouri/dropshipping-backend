"""
Sync State Repository
====================
Repository for SyncState model operations, extending BaseRepository.
"""

from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository.base import BaseRepository
from ..models import SyncState


class SyncStateRepository(BaseRepository[SyncState]):
    """
    Repository for managing SyncState entities.

    Tracks sync cursor, timestamps, counts, and status per entity type per integration.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, SyncState)

    async def get_by_integration_and_type(
        self, integration_id: uuid.UUID, entity_type: str
    ) -> Optional[SyncState]:
        """Get sync state for a specific integration + entity type combination."""
        result = await self.session.execute(
            select(SyncState).where(
                SyncState.integration_id == integration_id,
                SyncState.entity_type == entity_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self, integration_id: uuid.UUID, entity_type: str
    ) -> SyncState:
        """Get existing sync state or create a new one if it doesn't exist."""
        state = await self.get_by_integration_and_type(integration_id, entity_type)
        if state is None:
            state = await self.create(
                {
                    "integration_id": integration_id,
                    "entity_type": entity_type,
                    "status": "idle",
                    "sync_mode": "full",
                }
            )
        return state
