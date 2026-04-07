"""
Integration Logs Service
=========================
Business logic for recording and querying integration activity.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from .models import IntegrationLog
from .repository import IntegrationLogRepository

logger = structlog.get_logger(__name__)


class IntegrationLogService:
    """Service for managing integration log entries."""

    def __init__(self, session: AsyncSession):
        self.repo = IntegrationLogRepository(session)

    async def log_action(
        self,
        integration_id: UUID,
        action: str,
        status: str,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> IntegrationLog:
        """Record an integration action to the log."""
        entry = await self.repo.create({
            "integration_id": integration_id,
            "action": action,
            "status": status,
            "request_data": request_data or {},
            "response_data": response_data or {},
            "error_message": error_message,
            "created_at": datetime.now(timezone.utc),
        })
        if status == "failed":
            logger.warning(
                "integration_action_failed",
                integration_id=str(integration_id),
                action=action,
                error_message=error_message,
            )
        else:
            logger.debug(
                "integration_action_logged",
                integration_id=str(integration_id),
                action=action,
                status=status,
            )
        return entry

    async def get_integration_history(
        self, integration_id: UUID, limit: int = 50
    ) -> List[IntegrationLog]:
        """Get log history for an integration."""
        return await self.repo.get_by_integration(integration_id, limit=limit)

    async def get_recent_failures(
        self, integration_id: UUID, limit: int = 20
    ) -> List[IntegrationLog]:
        """Get recent failures for an integration."""
        return await self.repo.get_recent_failures(integration_id, limit=limit)
