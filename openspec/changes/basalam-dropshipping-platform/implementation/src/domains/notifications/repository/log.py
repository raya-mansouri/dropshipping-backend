"""
Notification Log Repository
===========================
Repository for NotificationLog model operations
"""

from typing import Optional, List
import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import NotificationLog, NotificationStatus


class NotificationLogRepository:
    """
    Repository for managing NotificationLog entities.

    Handles database operations for notification log records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[NotificationLog]:
        result = await self.session.execute(
            select(NotificationLog).where(NotificationLog.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_notification(
        self, notification_id: uuid.UUID
    ) -> List[NotificationLog]:
        result = await self.session.execute(
            select(NotificationLog)
            .where(NotificationLog.notification_id == notification_id)
            .order_by(NotificationLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_status(self, status: NotificationStatus) -> List[NotificationLog]:
        result = await self.session.execute(
            select(NotificationLog)
            .where(NotificationLog.status == status.value)
            .order_by(NotificationLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_failed(self) -> List[NotificationLog]:
        result = await self.session.execute(
            select(NotificationLog)
            .where(NotificationLog.status == NotificationStatus.FAILED.value)
            .order_by(NotificationLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> NotificationLog:
        log = NotificationLog(**data)
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log

    async def update_status(
        self, id: uuid.UUID, status: NotificationStatus
    ) -> Optional[NotificationLog]:
        await self.session.execute(
            update(NotificationLog)
            .where(NotificationLog.id == id)
            .values(status=status.value)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def mark_sent(self, id: uuid.UUID) -> Optional[NotificationLog]:
        await self.session.execute(
            update(NotificationLog)
            .where(NotificationLog.id == id)
            .values(status=NotificationStatus.SENT.value, sent_at=datetime.utcnow())
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def mark_failed(
        self, id: uuid.UUID, error: str, error_code: Optional[str] = None
    ) -> Optional[NotificationLog]:
        await self.session.execute(
            update(NotificationLog)
            .where(NotificationLog.id == id)
            .values(
                status=NotificationStatus.FAILED.value,
                error=error,
                error_code=error_code,
            )
        )
        await self.session.flush()
        return await self.get_by_id(id)
