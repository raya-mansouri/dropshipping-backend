"""
Webhook Retry Schedule Repository
==================================
Repository for WebhookRetrySchedule model operations
"""

from typing import Optional, List
import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import WebhookRetrySchedule


class WebhookRetryScheduleRepository:
    """
    Repository for managing WebhookRetrySchedule entities.

    Handles retry scheduling for failed webhook events following
    the pattern: 1m, 5m, 15m, 1h, 6h (5 attempts total).
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[WebhookRetrySchedule]:
        """
        Get retry schedule by its UUID.

        Args:
            id: WebhookRetrySchedule UUID

        Returns:
            WebhookRetrySchedule instance if found, None otherwise
        """
        result = await self.session.execute(
            select(WebhookRetrySchedule).where(WebhookRetrySchedule.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_event_id(
        self, webhook_event_id: uuid.UUID
    ) -> List[WebhookRetrySchedule]:
        """
        Get all retry schedules for a specific webhook event.

        Args:
            webhook_event_id: WebhookEvent UUID

        Returns:
            List of WebhookRetrySchedule instances for the event
        """
        result = await self.session.execute(
            select(WebhookRetrySchedule)
            .where(WebhookRetrySchedule.webhook_event_id == webhook_event_id)
            .order_by(WebhookRetrySchedule.attempt.asc())
        )
        return list(result.scalars().all())

    async def get_pending(self, limit: int = 100) -> List[WebhookRetrySchedule]:
        """
        Get pending retry schedules.

        Args:
            limit: Maximum number of results

        Returns:
            List of pending WebhookRetrySchedule instances
        """
        result = await self.session.execute(
            select(WebhookRetrySchedule)
            .where(WebhookRetrySchedule.status == "pending")
            .order_by(WebhookRetrySchedule.scheduled_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_scheduled_for(
        self, time: datetime, limit: int = 100
    ) -> List[WebhookRetrySchedule]:
        """
        Get retry schedules scheduled for a specific time.

        Args:
            time: Datetime to get schedules for
            limit: Maximum number of results

        Returns:
            List of WebhookRetrySchedule instances scheduled for the time
        """
        result = await self.session.execute(
            select(WebhookRetrySchedule)
            .where(
                WebhookRetrySchedule.status == "pending",
                WebhookRetrySchedule.scheduled_at <= time,
            )
            .order_by(WebhookRetrySchedule.scheduled_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_due_retries(
        self, current_time: datetime, limit: int = 100
    ) -> List[WebhookRetrySchedule]:
        """
        Get retries that are due (scheduled time has passed).

        Args:
            current_time: Current datetime
            limit: Maximum number of results

        Returns:
            List of due WebhookRetrySchedule instances
        """
        result = await self.session.execute(
            select(WebhookRetrySchedule)
            .where(
                WebhookRetrySchedule.status == "pending",
                WebhookRetrySchedule.scheduled_at <= current_time,
            )
            .order_by(WebhookRetrySchedule.scheduled_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> WebhookRetrySchedule:
        """
        Create a new retry schedule.

        Args:
            data: Dictionary containing retry schedule fields

        Returns:
            Newly created WebhookRetrySchedule instance
        """
        schedule = WebhookRetrySchedule(**data)
        self.session.add(schedule)
        await self.session.flush()
        await self.session.refresh(schedule)
        return schedule

    async def mark_completed(self, id: uuid.UUID) -> Optional[WebhookRetrySchedule]:
        """
        Mark retry schedule as completed (executed successfully).

        Args:
            id: WebhookRetrySchedule UUID

        Returns:
            Updated WebhookRetrySchedule instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookRetrySchedule)
            .where(WebhookRetrySchedule.id == id)
            .values(
                status="executed",
                executed_at=datetime.utcnow(),
            )
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def mark_failed(
        self, id: uuid.UUID, error: str
    ) -> Optional[WebhookRetrySchedule]:
        """
        Mark retry schedule as failed.

        Args:
            id: WebhookRetrySchedule UUID
            error: Error message describing the failure

        Returns:
            Updated WebhookRetrySchedule instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookRetrySchedule)
            .where(WebhookRetrySchedule.id == id)
            .values(
                status="failed",
                error=error,
            )
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def update(self, id: uuid.UUID, data: dict) -> Optional[WebhookRetrySchedule]:
        """
        Update retry schedule fields.

        Args:
            id: WebhookRetrySchedule UUID
            data: Dictionary containing fields to update

        Returns:
            Updated WebhookRetrySchedule instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookRetrySchedule)
            .where(WebhookRetrySchedule.id == id)
            .values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete_by_event(self, webhook_event_id: uuid.UUID) -> int:
        """
        Delete all retry schedules for a webhook event.

        Args:
            webhook_event_id: WebhookEvent UUID

        Returns:
            Number of deleted records
        """
        schedules = await self.get_by_event_id(webhook_event_id)
        count = 0
        for schedule in schedules:
            await self.session.delete(schedule)
            count += 1
        await self.session.flush()
        return count
