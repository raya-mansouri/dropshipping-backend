"""
Processed Event Repository
===========================
Repository for ProcessedEvent model operations

Provides idempotency checking using both Redis (fast path) and
database (persistent storage) for webhook event deduplication.
"""

from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ProcessedEvent


class ProcessedEventRepository:
    """
    Repository for managing ProcessedEvent entities.

    Handles idempotency tracking for webhook events, ensuring each
    event is processed exactly once. Uses a hybrid approach:
    - Redis (if available) for fast duplicate checking
    - Database for persistent tracking
    """

    def __init__(self, session: AsyncSession, redis_client=None):
        """
        Initialize repository with database session and optional Redis client.

        Args:
            session: Async SQLAlchemy session
            redis_client: Optional Redis client for fast duplicate checking
        """
        self.session = session
        self.redis_client = redis_client
        self.redis_prefix = "webhook:processed:"

    def _get_redis_key(self, key: str) -> str:
        """
        Generate Redis key for idempotency check.

        Args:
            key: Event identifier (platform_id + external_event_id)

        Returns:
            Redis key string
        """
        return f"{self.redis_prefix}{key}"

    async def get_by_idem_key(self, key: str) -> Optional[ProcessedEvent]:
        """
        Check if event has already been processed by its idempotency key.

        First checks Redis (fast path), then falls back to database.

        Args:
            key: Event identifier (platform_id + external_event_id)

        Returns:
            ProcessedEvent instance if found, None otherwise
        """
        if self.redis_client:
            redis_key = self._get_redis_key(key)
            cached = await self.redis_client.get(redis_key)
            if cached:
                return ProcessedEvent(
                    event_id=key,
                    event_hash=cached.decode() if isinstance(cached, bytes) else cached,
                )

        result = await self.session.execute(
            select(ProcessedEvent).where(ProcessedEvent.event_id == key)
        )
        return result.scalar_one_or_none()

    async def is_duplicate(self, key: str) -> bool:
        """
        Check if event is a duplicate (already processed).

        Args:
            key: Event identifier (platform_id + external_event_id)

        Returns:
            True if event has already been processed, False otherwise
        """
        event = await self.get_by_idem_key(key)
        return event is not None

    async def create(self, data: dict) -> ProcessedEvent:
        """
        Mark event as processed (create idempotency record).

        Stores in both Redis (for fast lookup) and database (for persistence).

        Args:
            data: Dictionary containing processed event fields
                  Must include: event_id, platform_id
                  Optional: event_hash, processed_by

        Returns:
            Newly created ProcessedEvent instance
        """
        event = ProcessedEvent(**data)

        if not event.processed_at:
            event.processed_at = datetime.utcnow()

        if not event.processed_by:
            event.processed_by = "webhook_processor"

        if self.redis_client and data.get("event_id"):
            redis_key = self._get_redis_key(data["event_id"])
            event_hash = data.get("event_hash", "")
            await self.redis_client.setex(
                redis_key,
                86400,
                event_hash,
            )

        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def delete(self, key: str) -> bool:
        """
        Remove processed event record (for reprocessing).

        Removes from both Redis and database.

        Args:
            key: Event identifier

        Returns:
            True if record was deleted, False if not found
        """
        if self.redis_client:
            redis_key = self._get_redis_key(key)
            await self.redis_client.delete(redis_key)

        result = await self.session.execute(
            select(ProcessedEvent).where(ProcessedEvent.event_id == key)
        )
        event = result.scalar_one_or_none()
        if event:
            await self.session.delete(event)
            await self.session.flush()
            return True
        return False
