"""
Integration Logs Repository
============================
Database access for integration log entries.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import IntegrationLog


class IntegrationLogRepository:
    """Repository for integration log persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, log_id: UUID) -> Optional[IntegrationLog]:
        """Get an integration log by ID."""
        result = await self.session.execute(
            select(IntegrationLog).where(IntegrationLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_by_integration(
        self, integration_id: UUID, limit: int = 100
    ) -> List[IntegrationLog]:
        """Get log history for a specific integration."""
        stmt = (
            select(IntegrationLog)
            .where(IntegrationLog.integration_id == integration_id)
            .order_by(IntegrationLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_failures(
        self, integration_id: UUID, limit: int = 20
    ) -> List[IntegrationLog]:
        """Get recent failed actions for an integration."""
        stmt = (
            select(IntegrationLog)
            .where(
                IntegrationLog.integration_id == integration_id,
                IntegrationLog.status == "failed",
            )
            .order_by(IntegrationLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict) -> IntegrationLog:
        """Create a new integration log entry."""
        entry = IntegrationLog(**data)
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry
