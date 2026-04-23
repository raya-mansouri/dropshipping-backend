"""
Notification Repository
=======================
Repository for Notification model operations
"""

from typing import Optional, List
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Notification, NotificationStatus


class NotificationRepository:
    """
    Repository for managing Notification entities.

    Handles database operations for notification records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Notification]:
        result = await self.session.execute(
            select(Notification).where(Notification.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Notification]:
        result = await self.session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_unread(
        self,
        user_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Notification]:
        result = await self.session.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.status != NotificationStatus.READ.value,
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Notification:
        notification = Notification(**data)
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def mark_read(self, id: uuid.UUID) -> Optional[Notification]:
        await self.session.execute(
            update(Notification)
            .where(Notification.id == id)
            .values(
                status=NotificationStatus.READ.value, read_at=datetime.now(timezone.utc)
            )
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.status != NotificationStatus.READ.value,
            )
            .values(
                status=NotificationStatus.READ.value, read_at=datetime.now(timezone.utc)
            )
        )
        await self.session.flush()
        return result.rowcount

    async def delete(self, id: uuid.UUID) -> bool:
        notification = await self.get_by_id(id)
        if notification:
            await self.session.delete(notification)
            await self.session.flush()
            return True
        return False
