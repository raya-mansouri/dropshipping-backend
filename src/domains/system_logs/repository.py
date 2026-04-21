"""
System Logs Repository
===========================
Database access for system log entries.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import SystemLog


class SystemLogRepository:
    """Repository for system log persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, log_id: UUID) -> Optional[SystemLog]:
        """Get a system log by ID."""
        result = await self.session.execute(
            select(SystemLog).where(SystemLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_by_service(
        self, service: str, limit: int = 100
    ) -> List[SystemLog]:
        """Get logs for a specific service."""
        stmt = (
            select(SystemLog)
            .where(SystemLog.service == service)
            .order_by(SystemLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_level(
        self, level: str, limit: int = 100
    ) -> List[SystemLog]:
        """Get logs by level."""
        stmt = (
            select(SystemLog)
            .where(SystemLog.level == level)
            .order_by(SystemLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 50) -> List[SystemLog]:
        """Get recent system logs across all services."""
        stmt = (
            select(SystemLog)
            .order_by(SystemLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict) -> SystemLog:
        """Create a new system log entry."""
        entry = SystemLog(**data)
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry
