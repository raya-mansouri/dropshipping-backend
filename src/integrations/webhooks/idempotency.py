"""
Webhook Idempotency Manager
===========================
Ensures webhook events are processed exactly once using Redis cache with database fallback.

Idempotency DB operations use a **separate session** so that the idempotency record
commits independently from the caller's business-logic transaction.  If the business
logic rolls back, the idempotency record persists and duplicate webhooks are still
rejected.
"""
import hashlib
import json
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger(__name__)


class IdempotencyManager:
    """
    Manages webhook idempotency to prevent duplicate processing.

    Uses Redis for fast lookups with TTL-based expiration,
    falls back to database for persistent storage.

    DB reads and writes are performed through a **separate session** whose
    transaction lifecycle is independent of any UnitOfWork that the caller
    may have open.  This guarantees that an idempotency record survives a
    rollback of the business-logic transaction.
    """

    REDIS_TTL_SECONDS = 24 * 60 * 60  # 24 hours

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        db_session: Optional[AsyncSession] = None,
    ):
        self.redis = redis_client
        self.db_session = db_session
        self._own_session: Optional[AsyncSession] = None

    async def _get_isolated_session(self) -> Optional[AsyncSession]:
        """Return a dedicated session whose transaction is independent of the caller's.

        Lazily creates one from the global session factory so that every
        ``_check_duplicate_in_db`` / ``_mark_processed_in_db`` call shares
        the same isolated session within this manager instance.
        """
        if self._own_session is not None:
            return self._own_session

        if self.db_session is None:
            return None

        from src.core.database import async_session_maker

        self._own_session = async_session_maker()
        return self._own_session

    async def close(self) -> None:
        """Close the isolated session (if one was created).

        Call this when the manager is no longer needed, e.g. inside a
        ``finally`` block or ``async with`` wrapper.
        """
        if self._own_session is not None:
            await self._own_session.close()
            self._own_session = None

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
                    logger.info("duplicate_event_detected_redis", event_id=str(event_id))
                    return True
            except Exception as e:
                logger.warning("redis_check_failed_fallback_db", error=str(e))

        if self.db_session:
            return await self._check_duplicate_in_db(
                platform_id, event_id, payload_hash
            )

        return False

    async def _check_duplicate_in_db(
        self, platform_id: str, event_id: str, payload_hash: str
    ) -> bool:
        """Check for duplicate in database using an isolated session."""
        from src.domains.webhooks.models import ProcessedEvent

        session = await self._get_isolated_session()
        if session is None:
            return False

        stmt = select(ProcessedEvent).where(
            ProcessedEvent.platform_id == platform_id,
            ProcessedEvent.event_id == f"{platform_id}:{event_id}:{payload_hash[:16]}",
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            logger.info("duplicate_event_detected_db", event_id=str(event_id))
            return True

        return False

    async def is_processed(
        self,
        event_id: str,
        platform_id: str = "webhook",
        payload: Optional[dict | str] = None,
    ) -> bool:
        """Convenience wrapper around ``check_duplicate`` for simple lookups.

        Accepts the simplified call signature used by webhook consumers that
        identify events by a single ``event_id`` / ``webhook_id``.
        """
        payload_hash = self.compute_payload_hash(payload) if payload else None
        return await self.check_duplicate(
            platform_id=platform_id,
            event_id=event_id,
            payload_hash=payload_hash,
        )

    async def mark_processed(
        self,
        event_id: str,
        platform_id: str = "webhook",
        result: Optional[dict] = None,
        payload_hash: Optional[str] = None,
        payload: Optional[dict | str] = None,
    ) -> bool:
        """
        Mark an event as processed.

        Args:
            event_id: The unique event ID (or webhook_id)
            platform_id: The platform identifier
            result: Optional result payload to store alongside the record
            payload_hash: Pre-computed hash of the payload
            payload: Payload to compute hash from

        Returns:
            True if successfully marked, False otherwise
        """
        if payload_hash is None and payload is not None:
            payload_hash = self.compute_payload_hash(payload)

        if not payload_hash:
            payload_hash = self.compute_payload_hash(event_id)

        redis_key = self._build_redis_key(platform_id, event_id, payload_hash)

        if self.redis:
            try:
                await self.redis.setex(
                    redis_key, self.REDIS_TTL_SECONDS, datetime.now(timezone.utc).isoformat()
                )
                logger.debug("marked_event_processed_redis", event_id=str(event_id))
            except Exception as e:
                logger.warning("failed_to_mark_redis", error=str(e))

        if self.db_session:
            await self._mark_processed_in_db(platform_id, event_id, payload_hash)

        return True

    async def _mark_processed_in_db(
        self, platform_id: str, event_id: str, payload_hash: str
    ) -> None:
        """Mark event as processed in database using an isolated session.

        The record is committed immediately so it survives any rollback of
        the caller's business-logic transaction.
        """
        from src.domains.webhooks.models import ProcessedEvent

        session = await self._get_isolated_session()
        if session is None:
            logger.warning(
                "no_db_session_available",
                event_id=str(event_id),
            )
            return

        now = datetime.now(timezone.utc)
        record = ProcessedEvent(
            event_id=f"{platform_id}:{event_id}:{payload_hash[:16]}",
            event_hash=payload_hash,
            platform_id=platform_id,
            processed_at=now,
            processed_by="webhook_processor",
        )
        session.add(record)
        await session.commit()
        logger.debug("marked_event_processed_db", event_id=str(event_id))

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
        session = await self._get_isolated_session()
        if session is None:
            return 0

        from src.domains.webhooks.models import ProcessedEvent

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.REDIS_TTL_SECONDS)

        try:
            result = await session.execute(
                ProcessedEvent.__table__.delete().where(
                    ProcessedEvent.processed_at < cutoff
                )
            )
            await session.commit()
            deleted = result.rowcount
            logger.info("cleaned_up_expired_idempotency_records", deleted=deleted)
            return deleted
        except Exception as e:
            logger.error("failed_to_cleanup_expired_records", error=str(e))
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
        if not self.redis:
            logger.warning("Cannot warm cache: Redis not available")
            return 0

        session = await self._get_isolated_session()
        if session is None:
            logger.warning("Cannot warm cache: DB session not available")
            return 0

        from src.domains.webhooks.models import ProcessedEvent

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.REDIS_TTL_SECONDS)

        try:
            stmt = select(ProcessedEvent).where(ProcessedEvent.processed_at >= cutoff)
            if platforms:
                stmt = stmt.where(ProcessedEvent.platform_id.in_(platforms))

            stmt = stmt.order_by(ProcessedEvent.processed_at.desc())
            stmt = stmt.limit(1000)

            result = await session.execute(stmt)
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
                        logger.warning("failed_to_cache_event", redis_key=redis_key, error=str(e))

            logger.info("warmed_cache_with_events", cached_count=cached_count)
            return cached_count

        except Exception as e:
            logger.error("failed_to_warm_cache", error=str(e))
            return 0
