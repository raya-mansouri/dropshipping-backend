"""
Retry Scheduler
==============
Schedules and manages webhook retry attempts with exponential backoff.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class RetrySchedule(BaseModel):
    """Configuration for retry schedule"""

    intervals: List[int] = [
        60,  # 1 minute
        300,  # 5 minutes
        900,  # 15 minutes
        3600,  # 1 hour
        21600,  # 6 hours
    ]


class RetryScheduler:
    """
    Manages webhook retry scheduling with exponential backoff.

    Schedule: 1m, 5m, 15m, 1h, 6h (5 attempts total)
    """

    SCHEDULE = RetrySchedule()
    MAX_ATTEMPTS = 5

    def __init__(self, db_session: Optional[AsyncSession] = None):
        self.db_session = db_session

    def get_next_retry_time(self, attempt: int) -> datetime:
        """
        Calculate the next retry time for a given attempt number.

        Args:
            attempt: The current attempt number (1-indexed)

        Returns:
            The datetime when the next retry should occur
        """
        if attempt < 1 or attempt > self.MAX_ATTEMPTS:
            raise ValueError(f"Attempt must be between 1 and {self.MAX_ATTEMPTS}")

        delay_seconds = self.SCHEDULE.intervals[attempt - 1]
        return datetime.utcnow() + timedelta(seconds=delay_seconds)

    async def schedule_retry(
        self,
        event_id: str,
        attempt: int,
        platform_id: str,
        event_type: str,
        payload: dict,
    ) -> bool:
        """
        Schedule a retry for a failed webhook event.

        Args:
            event_id: The unique event identifier
            attempt: The current attempt number
            platform_id: The platform identifier
            event_type: The event type
            payload: The original webhook payload

        Returns:
            True if retry was scheduled successfully
        """
        if attempt >= self.MAX_ATTEMPTS:
            logger.warning(f"Max retry attempts reached for event {event_id}")
            await self._mark_as_failed(event_id)
            return False

        next_attempt = attempt + 1
        next_retry_time = self.get_next_retry_time(next_attempt)

        if self.db_session:
            await self._save_retry_record(
                event_id=event_id,
                attempt=next_attempt,
                platform_id=platform_id,
                event_type=event_type,
                payload=payload,
                scheduled_at=next_retry_time,
            )
            logger.info(
                f"Scheduled retry {next_attempt}/{self.MAX_ATTEMPTS} "
                f"for event {event_id} at {next_retry_time}"
            )

        return True

    async def _save_retry_record(
        self,
        event_id: str,
        attempt: int,
        platform_id: str,
        event_type: str,
        payload: dict,
        scheduled_at: datetime,
    ) -> None:
        """Save retry record to database"""
        from src.domains.webhooks.models import WebhookRetry

        retry = WebhookRetry(
            event_id=event_id,
            attempt=attempt,
            platform_id=platform_id,
            event_type=event_type,
            payload=payload,
            scheduled_at=scheduled_at,
            status="pending",
        )
        self.db_session.add(retry)
        await self.db_session.commit()

    async def _mark_as_failed(self, event_id: str) -> None:
        """Mark event as permanently failed"""
        from src.domains.webhooks.models import WebhookRetry

        stmt = (
            update(WebhookRetry)
            .where(WebhookRetry.event_id == event_id)
            .values(status="failed")
        )
        await self.db_session.execute(stmt)
        await self.db_session.commit()

    async def get_pending_retries(self) -> List[dict]:
        """
        Get all pending retry events that are due.

        Returns:
            List of retry records that should be processed
        """
        if not self.db_session:
            return []

        from src.domains.webhooks.models import WebhookRetry

        now = datetime.utcnow()
        stmt = select(WebhookRetry).where(
            WebhookRetry.status == "pending", WebhookRetry.scheduled_at <= now
        )
        result = await self.db_session.execute(stmt)
        retries = result.scalars().all()

        return [
            {
                "id": r.id,
                "event_id": r.event_id,
                "attempt": r.attempt,
                "platform_id": r.platform_id,
                "event_type": r.event_type,
                "payload": r.payload,
            }
            for r in retries
        ]

    async def mark_retry_complete(self, retry_id: int) -> None:
        """Mark a retry as completed"""
        from src.domains.webhooks.models import WebhookRetry

        stmt = (
            update(WebhookRetry)
            .where(WebhookRetry.id == retry_id)
            .values(status="completed")
        )
        await self.db_session.execute(stmt)
        await self.db_session.commit()

    async def mark_retry_failed(self, retry_id: int) -> None:
        """Mark a retry as failed (will be retried again if attempts remain)"""
        from src.domains.webhooks.models import WebhookRetry

        stmt = (
            update(WebhookRetry)
            .where(WebhookRetry.id == retry_id)
            .values(status="failed")
        )
        await self.db_session.execute(stmt)
        await self.db_session.commit()

    def get_retry_interval(self, attempt: int) -> int:
        """
        Get the retry interval in seconds for a given attempt.

        Args:
            attempt: The attempt number (1-indexed)

        Returns:
            Interval in seconds
        """
        if 1 <= attempt <= len(self.SCHEDULE.intervals):
            return self.SCHEDULE.intervals[attempt - 1]
        return self.SCHEDULE.intervals[-1]
