"""
Webhook Idempotency Manager
===========================
Ensures webhook events are processed exactly once using Redis cache with database fallback.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class IdempotencyManager:
    """
    Manages webhook idempotency to prevent duplicate processing.

    Uses Redis for fast lookups with TTL-based expiration,
    falls back to database for persistent storage.
    """

    REDIS_TTL_SECONDS = 24 * 60 * 60  # 24 hours

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        db_session: Optional[AsyncSession] = None,
    ):
        self.redis = redis_client
        self.db_session = db_session

    def compute_payload_hash(self, payload: dict | str) -> str:
        """
        Compute a deterministic hash of the payload.

        Args:
            payload: The payload dict or string

        Returns:
            SHA256 hash of the payload
        """
        if isinstance(payload, dict):
            payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def check_duplicate(
        self,
        platform_id: str,
        event_id: str,
        payload_hash: Optional[str] = None,
        payload: Optional[dict | str] = None,
    ) -> bool:
        """
        Check if this event has already been processed.

        Args:
            platform_id: The platform identifier
            event_id: The unique event ID from the webhook
            payload_hash: Pre-computed hash of the payload
            payload: Payload to compute hash from (if hash not provided)

        Returns:
            True if this is a duplicate event, False otherwise
        """
        if payload_hash is None and payload is not None:
            payload_hash = self.compute_payload_hash(payload)

        if not payload_hash:
            logger.warning("No payload hash provided for idempotency check")
            return False

        redis_key = self._build_redis_key(platform_id, event_id, payload_hash)

        if self.redis:
            try:
                exists = await self.redis.exists(redis_key)
                if exists:
                    logger.info(f"Duplicate event detected in Redis: {event_id}")
                    return True
            except Exception as e:
                logger.warning(f"Redis check failed, falling back to DB: {e}")

        if self.db_session:
            return await self._check_duplicate_in_db(
                platform_id, event_id, payload_hash
            )

        return False

    async def _check_duplicate_in_db(
        self, platform_id: str, event_id: str, payload_hash: str
    ) -> bool:
        """Check for duplicate in database"""
        from src.domains.webhooks.models import ProcessedEvent

        stmt = select(ProcessedEvent).where(
            ProcessedEvent.platform_id == platform_id,
            ProcessedEvent.event_id == f"{platform_id}:{event_id}:{payload_hash[:16]}",
        )
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            logger.info(f"Duplicate event detected in DB: {event_id}")
            return True

        return False

    async def mark_processed(
        self,
        platform_id: str,
        event_id: str,
        payload_hash: Optional[str] = None,
        payload: Optional[dict | str] = None,
    ) -> bool:
        """
        Mark an event as processed.

        Args:
            platform_id: The platform identifier
            event_id: The unique event ID
            payload_hash: Pre-computed hash of the payload
            payload: Payload to compute hash from

        Returns:
            True if successfully marked, False otherwise
        """
        if payload_hash is None and payload is not None:
            payload_hash = self.compute_payload_hash(payload)

        if not payload_hash:
            logger.warning("No payload hash provided for marking processed")
            return False

        redis_key = self._build_redis_key(platform_id, event_id, payload_hash)

        if self.redis:
            try:
                await self.redis.setex(
                    redis_key, self.REDIS_TTL_SECONDS, datetime.utcnow().isoformat()
                )
                logger.debug(f"Marked event as processed in Redis: {event_id}")
            except Exception as e:
                logger.warning(f"Failed to mark in Redis: {e}")

        if self.db_session:
            await self._mark_processed_in_db(platform_id, event_id, payload_hash)

        return True

    async def _mark_processed_in_db(
        self, platform_id: str, event_id: str, payload_hash: str
    ) -> None:
        """Mark event as processed in database"""
        from src.domains.webhooks.models import ProcessedEvent

        now = datetime.utcnow()
        record = ProcessedEvent(
            event_id=f"{platform_id}:{event_id}:{payload_hash[:16]}",
            event_hash=payload_hash,
            platform_id=platform_id,
            processed_at=now,
            processed_by="webhook_processor",
        )
        self.db_session.add(record)
        await self.db_session.commit()
        logger.debug(f"Marked event as processed in DB: {event_id}")

    def _build_redis_key(
        self, platform_id: str, event_id: str, payload_hash: str
    ) -> str:
        """Build Redis key for idempotency cache"""
        return f"webhook:idem:{platform_id}:{event_id}:{payload_hash[:16]}"

    async def cleanup_expired(self) -> int:
        """
        Clean up expired idempotency records from database.

        Returns:
            Number of records cleaned up
        """
        if not self.db_session:
            return 0

        from src.domains.webhooks.models import ProcessedEvent

        cutoff = datetime.utcnow() - timedelta(seconds=self.REDIS_TTL_SECONDS)

        try:
            result = await self.db_session.execute(
                ProcessedEvent.__table__.delete().where(
                    ProcessedEvent.processed_at < cutoff
                )
            )
            await self.db_session.commit()
            deleted = result.rowcount
            logger.info(f"Cleaned up {deleted} expired idempotency records")
            return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup expired records: {e}")
            return 0

    async def warm_cache(self, platforms: Optional[list[str]] = None) -> int:
        """
        Warm the Redis cache with recent processed events from the database.

        This improves performance by populating the fast-path Redis cache
        with events that have been processed recently.

        Args:
            platforms: Optional list of platform IDs to warm cache for.
                      If None, warms cache for all platforms.

        Returns:
            Number of events cached
        """
        if not self.redis or not self.db_session:
            logger.warning("Cannot warm cache: Redis or DB session not available")
            return 0

        from src.domains.webhooks.models import ProcessedEvent

        cutoff = datetime.utcnow() - timedelta(seconds=self.REDIS_TTL_SECONDS)

        try:
            stmt = select(ProcessedEvent).where(ProcessedEvent.processed_at >= cutoff)
            if platforms:
                stmt = stmt.where(ProcessedEvent.platform_id.in_(platforms))

            stmt = stmt.order_by(ProcessedEvent.processed_at.desc())
            stmt = stmt.limit(1000)

            result = await self.db_session.execute(stmt)
            records = result.scalars().all()

            cached_count = 0
            for record in records:
                # Parse event_id to get components
                parts = record.event_id.split(":")
                if len(parts) >= 3:
                    platform_id = parts[0]
                    event_id = parts[1]

                    redis_key = self._build_redis_key(
                        platform_id,
                        event_id,
                        record.event_hash,
                    )
                    try:
                        await self.redis.setex(
                            redis_key,
                            self.REDIS_TTL_SECONDS,
                            record.processed_at.isoformat(),
                        )
                        cached_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to cache {redis_key}: {e}")

            logger.info(f"Warmed cache with {cached_count} events")
            return cached_count

        except Exception as e:
            logger.error(f"Failed to warm cache: {e}")
            return 0
