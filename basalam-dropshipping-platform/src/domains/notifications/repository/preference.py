"""
Notification Preference Repository
===================================
Repository for NotificationPreference model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import NotificationPreference, NotificationChannel


class NotificationPreferenceRepository:
    """
    Repository for managing NotificationPreference entities.

    Handles database operations for notification preference records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[NotificationPreference]:
        result = await self.session.execute(
            select(NotificationPreference).where(NotificationPreference.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: uuid.UUID) -> List[NotificationPreference]:
        result = await self.session.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
            .order_by(NotificationPreference.event_type)
        )
        return list(result.scalars().all())

    async def get_for_channel(
        self, user_id: uuid.UUID, channel: NotificationChannel
    ) -> List[NotificationPreference]:
        channel_field = f"{channel.value}_enabled"
        result = await self.session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                getattr(NotificationPreference, channel_field) == True,
            )
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> NotificationPreference:
        preference = NotificationPreference(**data)
        self.session.add(preference)
        await self.session.flush()
        await self.session.refresh(preference)
        return preference

    async def update(
        self, id: uuid.UUID, data: dict
    ) -> Optional[NotificationPreference]:
        await self.session.execute(
            update(NotificationPreference)
            .where(NotificationPreference.id == id)
            .values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def upsert(
        self, user_id: uuid.UUID, channel: NotificationChannel, enabled: bool
    ) -> NotificationPreference:
        event_type = channel.value
        channel_field = f"{event_type}_enabled"

        result = await self.session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.event_type == event_type,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            await self.session.execute(
                update(NotificationPreference)
                .where(NotificationPreference.id == existing.id)
                .values(**{channel_field: enabled})
            )
            await self.session.flush()
            return await self.get_by_id(existing.id)

        data = {"user_id": user_id, "event_type": event_type, channel_field: enabled}
        return await self.create(data)
