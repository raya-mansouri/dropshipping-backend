"""
System Logs Service
===========================
Business logic for system-wide logging and monitoring.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from .models import SystemLog
from .repository import SystemLogRepository

logger = structlog.get_logger(__name__)


class SystemLogService:
    """Service for managing system log entries."""

    def __init__(self, session: AsyncSession):
        self.repo = SystemLogRepository(session)

    async def log_entry(
        self,
        level: str,
        service: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemLog:
        """Record a system log entry."""
        entry = await self.repo.create({
            "level": level,
            "service": service,
            "message": message,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
        })
        logger.debug(
            "system_log_recorded",
            level=level,
            service=service,
        )
        return entry

    async def get_service_logs(
        self, service: str, limit: int = 50
    ) -> List[SystemLog]:
        """Get recent logs for a service."""
        return await self.repo.get_by_service(service, limit=limit)

    async def get_level_logs(
        self, level: str, limit: int = 50
    ) -> List[SystemLog]:
        """Get logs by level (e.g., ERROR, WARNING)."""
        return await self.repo.get_by_level(level, limit=limit)

    async def get_recent_logs(self, limit: int = 50) -> List[SystemLog]:
        """Get recent logs across all services."""
        return await self.repo.get_recent(limit=limit)
