"""
AuditLog Service
================
Business logic for recording and querying admin audit entries.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from .models import AuditLog
from .repository import AuditLogRepository

logger = structlog.get_logger(__name__)


class AuditLogService:
    """Service for managing audit log entries."""

    def __init__(self, session: AsyncSession):
        self.repo = AuditLogRepository(session)

    async def log_action(
        self,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor_type: str,
        actor_id: UUID,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> AuditLog:
        """Record an admin action to the audit log."""
        entry = await self.repo.create_entry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
        logger.info(
            "audit_action_logged",
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor_type=actor_type,
            actor_id=str(actor_id),
        )
        return entry

    async def get_entity_history(
        self, entity_type: str, entity_id: UUID, limit: int = 50
    ) -> List[AuditLog]:
        """Get audit log history for an entity."""
        return await self.repo.get_by_entity(entity_type, entity_id, limit=limit)

    async def get_recent_actions(
        self, entity_type: str, limit: int = 20
    ) -> List[AuditLog]:
        """Get recent admin actions for an entity type."""
        return await self.repo.get_recent(entity_type, limit)
