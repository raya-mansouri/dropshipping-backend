"""
AuditLog Repository
==================
Database access for audit log entries
"""
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


class AuditLogRepository:
    """Repository for audit log persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_entry(
        self,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor_type: str,
        actor_id: UUID,
        old_value: dict | None = None,
        new_value: dict | None = None,
        reason: str | None = None,
    ) -> AuditLog:
        """Create a new audit log entry."""
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            old_value=old_value or {},
            new_value=new_value or {},
            reason=reason,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_by_entity(
        self, entity_type: str, entity_id: UUID, limit: int = 100
    ) -> List[AuditLog]:
        """Get audit log history for a specific entity."""
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(
        self, entity_type: str, limit: int = 20
    ) -> List[AuditLog]:
        """Get recent audit log entries for an entity type."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
