"""
Idempotency Integration Tests
============================
Tests for duplicate event handling, Redis layer, and database fallback
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.webhooks.idempotency import IdempotencyManager


class TestDuplicateEventHandling:
    """Tests for duplicate event detection and handling"""

    @pytest.fixture
    def sample_event(self):
        return {
            "platform_id": "platform-123",
            "event_id": "evt-987654",
            "payload": {
                "order_id": "ord-12345",
                "total_price": 99.99,
                "currency": "USD",
                "customer": {"email": "customer@example.com", "name": "Test Customer"},
                "items": [
                    {"variant_id": str(uuid.uuid4()), "quantity": 2, "price": 49.99}
                ],
            },
        }

    @pytest.mark.asyncio
    async def test_new_event_is_not_duplicate(self, sample_event):
        """Test that a new event is not marked as duplicate"""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = False

        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        manager = IdempotencyManager(redis_client=mock_redis, db_session=mock_db)

        is_duplicate = await manager.check_duplicate(
            platform_id=sample_event["platform_id"],
            event_id=sample_event["event_id"],
            payload=sample_event["payload"],
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_duplicate_event_detected(self, sample_event):
        """Test that duplicate events are correctly detected"""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = True

        manager = IdempotencyManager(redis_client=mock_redis)

        is_duplicate = await manager.check_duplicate(
            platform_id=sample_event["platform_id"],
            event_id=sample_event["event_id"],
            payload=sample_event["payload"],
        )

        assert is_duplicate is True
        mock_redis.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_same_event_id_different_platform(self, sample_event):
        """Test that same event ID on different platforms are not duplicates"""
        mock_redis = AsyncMock()

        call_count = 0

        async def mock_exists(key):
            nonlocal call_count
            call_count += 1
            return False

        mock_redis.exists.side_effect = mock_exists

        manager = IdempotencyManager(redis_client=mock_redis)

        result1 = await manager.check_duplicate(
            platform_id="platform-a",
            event_id="evt-shared",
            payload=sample_event["payload"],
        )

        result2 = await manager.check_duplicate(
            platform_id="platform-b",
            event_id="evt-shared",
            payload=sample_event["payload"],
        )

        assert result1 is False
        assert result2 is False
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_duplicate_with_different_payload_hash(self, sample_event):
        """Test handling when same event has different payload"""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = False

        manager = IdempotencyManager(redis_client=mock_redis)

        payload1 = {"order_id": "ord-123", "status": "paid"}
        payload2 = {"order_id": "ord-123", "status": "cancelled"}

        hash1 = manager.compute_payload_hash(payload1)
        hash2 = manager.compute_payload_hash(payload2)

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_event_marked_as_processed(self, sample_event):
        """Test that processed events are properly marked"""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(return_value=True)

        mock_db = AsyncMock()

        manager = IdempotencyManager(redis_client=mock_redis, db_session=mock_db)

        result = await manager.mark_processed(
            platform_id=sample_event["platform_id"],
            event_id=sample_event["event_id"],
            payload=sample_event["payload"],
        )

        assert result is True
        mock_redis.setex.assert_called_once()


class TestRedisLayer:
    """Tests for Redis idempotency layer"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.setex = AsyncMock(return_value=True)
        redis.exists = AsyncMock(return_value=False)
        redis.delete = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        return redis

    @pytest.mark.asyncio
    async def test_redis_key_format(self, mock_redis):
        """Test that Redis keys are formatted correctly"""
        manager = IdempotencyManager(redis_client=mock_redis)

        platform_id = "platform-abc"
        event_id = "evt-xyz"
        payload_hash = "abc123def456"

        key = manager._build_redis_key(platform_id, event_id, payload_hash)

        assert key == f"webhook:idem:{platform_id}:{event_id}:{payload_hash}"

    @pytest.mark.asyncio
    async def test_redis_check_returns_true_for_duplicate(self, mock_redis):
        """Test Redis returns True when duplicate exists"""
        mock_redis.exists.return_value = True

        manager = IdempotencyManager(redis_client=mock_redis)

        is_duplicate = await manager.check_duplicate(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_redis_check_returns_false_for_new(self, mock_redis):
        """Test Redis returns False when event is new"""
        mock_redis.exists.return_value = False

        manager = IdempotencyManager(redis_client=mock_redis)

        is_duplicate = await manager.check_duplicate(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_redis_ttl_is_set(self, mock_redis):
        """Test that Redis TTL is properly set when marking processed"""
        mock_redis.setex = AsyncMock(return_value=True)

        manager = IdempotencyManager(redis_client=mock_redis)

        await manager.mark_processed(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        call_args = mock_redis.setex.call_args
        assert call_args is not None

        ttl_seconds = call_args[0][1]
        assert ttl_seconds == manager.REDIS_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_redis_failure_handling(self, mock_redis):
        """Test graceful handling when Redis fails"""
        mock_redis.exists.side_effect = Exception("Redis connection error")

        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        manager = IdempotencyManager(redis_client=mock_redis, db_session=mock_db)

        is_duplicate = await manager.check_duplicate(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_redis_not_available_uses_db_only(self):
        """Test that when Redis is not available, only DB is used"""
        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        manager = IdempotencyManager(db_session=mock_db)

        is_duplicate = await manager.check_duplicate(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        assert is_duplicate is False


class TestDatabaseFallback:
    """Tests for database fallback layer"""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_database_check_finds_duplicate(self, mock_db_session):
        """Test database check finds existing processed event"""
        mock_existing_record = MagicMock()
        mock_existing_record.event_id = "evt-123"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_existing_record
        mock_db_session.execute.return_value = mock_result

        manager = IdempotencyManager(db_session=mock_db_session)

        is_duplicate = await manager._check_duplicate_in_db(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_database_check_no_duplicate(self, mock_db_session):
        """Test database check when no duplicate exists"""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        manager = IdempotencyManager(db_session=mock_db_session)

        is_duplicate = await manager._check_duplicate_in_db(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_mark_processed_in_database(self, mock_db_session):
        """Test marking event as processed in database"""
        manager = IdempotencyManager(db_session=mock_db_session)

        await manager._mark_processed_in_db(
            platform_id="platform-123", event_id="evt-123", payload_hash="test-hash"
        )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_expired_records(self, mock_db_session):
        """Test cleanup of expired idempotency records"""
        mock_result = AsyncMock()
        mock_result.rowcount = 5
        mock_db_session.execute.return_value = mock_result

        manager = IdempotencyManager(db_session=mock_db_session)

        result = await manager.cleanup_expired()

        mock_db_session.execute.assert_called()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_without_db_session(self):
        """Test cleanup returns 0 when no DB session"""
        manager = IdempotencyManager()

        result = await manager.cleanup_expired()

        assert result == 0

    @pytest.mark.asyncio
    async def test_payload_hash_consistency(self, mock_db_session):
        """Test that payload hash is consistent regardless of key order"""
        manager = IdempotencyManager(db_session=mock_db_session)

        payload1 = {
            "order_id": "ord-123",
            "customer": {"name": "Test", "email": "test@example.com"},
            "total": 100,
        }

        payload2 = {
            "total": 100,
            "customer": {"email": "test@example.com", "name": "Test"},
            "order_id": "ord-123",
        }

        hash1 = manager.compute_payload_hash(payload1)
        hash2 = manager.compute_payload_hash(payload2)

        assert hash1 == hash2


class TestIdempotencyEdgeCases:
    """Tests for edge cases in idempotency handling"""

    @pytest.mark.asyncio
    async def test_empty_payload(self):
        """Test handling of empty payload"""
        manager = IdempotencyManager()

        is_duplicate = await manager.check_duplicate(
            platform_id="platform-123", event_id="evt-123", payload={}
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_none_payload(self):
        """Test handling of None payload"""
        manager = IdempotencyManager()

        is_duplicate = await manager.check_duplicate(
            platform_id="platform-123", event_id="evt-123", payload=None
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_string_payload(self):
        """Test handling of string payload"""
        manager = IdempotencyManager()

        hash1 = manager.compute_payload_hash('{"order_id": "ord-123"}')
        hash2 = manager.compute_payload_hash({"order_id": "ord-123"})

        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_special_characters_in_payload(self):
        """Test handling of special characters in payload"""
        manager = IdempotencyManager()

        payload = {
            "order_id": "ord-123",
            "note": "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?",
            "unicode": "日本語 emojis 🎉",
        }

        hash_result = manager.compute_payload_hash(payload)

        assert len(hash_result) == 64

    @pytest.mark.asyncio
    async def test_large_payload(self):
        """Test handling of large payload"""
        manager = IdempotencyManager()

        items = [{"id": i, "name": f"Item {i}"} for i in range(1000)]
        payload = {"order_id": "ord-123", "items": items}

        hash_result = manager.compute_payload_hash(payload)

        assert len(hash_result) == 64
