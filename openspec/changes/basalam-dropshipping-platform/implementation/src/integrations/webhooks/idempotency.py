"""
Idempotency Manager
===================
Ensures webhook events are processed exactly once using Redis cache
with database fallback.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class IdempotencyRecord(BaseModel):
    """Database model for idempotency records"""

    platform_id: str
    event_id: str
    payload_hash: str
    processed_at: datetime
    created_at: datetime


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
        from src.domains.webhooks.models import WebhookEventLog

        stmt = select(WebhookEventLog).where(
            WebhookEventLog.platform_id == platform_id,
            WebhookEventLog.event_id == event_id,
            WebhookEventLog.payload_hash == payload_hash,
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
        from src.domains.webhooks.models import WebhookEventLog

        now = datetime.utcnow()
        record = WebhookEventLog(
            platform_id=platform_id,
            event_id=event_id,
            payload_hash=payload_hash,
            processed_at=now,
            created_at=now,
        )
        self.db_session.add(record)
        await self.db_session.commit()
        logger.debug(f"Marked event as processed in DB: {event_id}")

    def _build_redis_key(
        self, platform_id: str, event_id: str, payload_hash: str
    ) -> str:
        """Build Redis key for idempotency cache"""
        return f"webhook:idem:{platform_id}:{event_id}:{payload_hash}"

    async def cleanup_expired(self) -> int:
        """
        Clean up expired idempotency records from database.

        Returns:
            Number of records cleaned up
        """
        if not self.db_session:
            return 0

        from src.domains.webhooks.models import WebhookEventLog

        cutoff = datetime.utcnow() - timedelta(seconds=self.REDIS_TTL_SECONDS)

        try:
            await self.db_session.execute(
                WebhookEventLog.__table__.delete().where(
                    WebhookEventLog.processed_at < cutoff
                )
            )
            await self.db_session.commit()
            return 0
        except Exception as e:
            logger.error(f"Failed to cleanup expired records: {e}")
            return 0
