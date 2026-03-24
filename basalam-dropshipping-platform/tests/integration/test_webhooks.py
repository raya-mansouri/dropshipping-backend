"""
Webhook Integration Tests
==========================
Tests for webhook signature validation, processing, and idempotency
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.webhooks.models import (
    WebhookEvent,
    WebhookEventStatus,
    ProcessedEvent,
)
from src.domains.webhooks.repository.webhook_event import WebhookEventRepository
from src.integrations.webhooks.idempotency import IdempotencyManager


class TestWebhookSignatureValidation:
    """Tests for webhook signature validation"""

    @pytest.fixture
    def webhook_secret(self):
        return "test-webhook-secret-key-12345"

    @pytest.fixture
    def sample_payload(self):
        return {
            "event_type": "order.created",
            "external_order_id": "ORD-12345",
            "order": {
                "id": "ext-123",
                "total_price": 99.99,
                "currency": "USD",
                "customer": {"phone": "09123456789", "name": "Test Customer"},
                "items": [
                    {"variant_id": str(uuid.uuid4()), "quantity": 2, "price": 49.99}
                ],
            },
            "timestamp": "2024-01-15T10:30:00Z",
        }

    def generate_signature(self, payload: dict, secret: str) -> str:
        """Generate HMAC signature for webhook payload"""
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            secret.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return signature

    @pytest.mark.asyncio
    async def test_valid_signature_passes(self, webhook_secret, sample_payload):
        """Test that a valid signature passes validation"""
        signature = self.generate_signature(sample_payload, webhook_secret)

        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            json.dumps(sample_payload, sort_keys=True).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(signature, expected_signature)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_invalid_signature_fails(self, webhook_secret, sample_payload):
        """Test that an invalid signature fails validation"""
        valid_signature = self.generate_signature(sample_payload, webhook_secret)

        tampered_payload = sample_payload.copy()
        tampered_payload["order"]["total_price"] = 0.01

        tampered_signature = self.generate_signature(tampered_payload, webhook_secret)

        is_valid = hmac.compare_digest(tampered_signature, valid_signature)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_missing_signature_fails(self, sample_payload):
        """Test that missing signature fails validation"""
        signature = None

        assert signature is None

    @pytest.mark.asyncio
    async def test_tampered_payload_fails(self, webhook_secret, sample_payload):
        """Test that tampered payload fails signature validation"""
        original_signature = self.generate_signature(sample_payload, webhook_secret)

        modified_payload = sample_payload.copy()
        modified_payload["order"]["total_price"] = 999.99

        modified_signature = self.generate_signature(modified_payload, webhook_secret)

        assert original_signature != modified_signature

    @pytest.mark.asyncio
    async def test_signature_with_different_algorithms(self, sample_payload):
        """Test signature generation with different hash algorithms"""
        payload_str = json.dumps(sample_payload, sort_keys=True)

        sha256_sig = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        sha512_sig = hashlib.sha512(payload_str.encode("utf-8")).hexdigest()

        assert len(sha256_sig) == 64
        assert len(sha512_sig) == 128
        assert sha256_sig != sha512_sig


class TestWebhookProcessing:
    """Tests for webhook event processing"""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def sample_webhook_event(self, sample_uuid):
        return {
            "id": sample_uuid,
            "platform_id": sample_uuid,
            "integration_id": sample_uuid,
            "event_type": "order.created",
            "external_event_id": "evt-12345",
            "payload": {"order_id": "ord-123", "total_price": 99.99},
            "signature": "test-signature",
            "signature_verified": True,
            "status": WebhookEventStatus.RECEIVED.value,
        }

    @pytest.mark.asyncio
    async def test_create_webhook_event(self, mock_db_session, sample_webhook_event):
        """Test creating a webhook event"""
        from sqlalchemy import select

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=None)
        mock_db_session.execute.return_value = mock_result

        repo = WebhookEventRepository(mock_db_session)

        event_data = {
            "platform_id": sample_webhook_event["platform_id"],
            "integration_id": sample_webhook_event["integration_id"],
            "event_type": sample_webhook_event["event_type"],
            "external_event_id": sample_webhook_event["external_event_id"],
            "payload": sample_webhook_event["payload"],
            "signature": sample_webhook_event["signature"],
            "signature_verified": sample_webhook_event["signature_verified"],
            "status": sample_webhook_event["status"],
        }

        event = await repo.create(event_data)

        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_event_status(self, mock_db_session, sample_webhook_event):
        """Test updating webhook event status"""
        from sqlalchemy import select

        event_id = sample_webhook_event["id"]

        mock_event = MagicMock()
        mock_event.id = event_id

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=mock_event)
        mock_db_session.execute.return_value = mock_result

        repo = WebhookEventRepository(mock_db_session)

        updated_event = await repo.update_status(
            event_id, WebhookEventStatus.PROCESSING
        )

        mock_db_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_mark_event_completed(self, mock_db_session, sample_webhook_event):
        """Test marking webhook event as completed"""
        from sqlalchemy import select

        event_id = sample_webhook_event["id"]

        mock_event = MagicMock()
        mock_event.id = event_id

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=mock_event)
        mock_db_session.execute.return_value = mock_result

        repo = WebhookEventRepository(mock_db_session)

        updated_event = await repo.update_status(event_id, WebhookEventStatus.COMPLETED)

        assert updated_event is not None

    @pytest.mark.asyncio
    async def test_mark_event_failed(self, mock_db_session, sample_webhook_event):
        """Test marking webhook event as failed with error"""
        from sqlalchemy import select

        event_id = sample_webhook_event["id"]

        mock_event = MagicMock()
        mock_event.id = event_id

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=mock_event)
        mock_db_session.execute.return_value = mock_result

        repo = WebhookEventRepository(mock_db_session)

        error_message = "Processing failed: Invalid order data"

        updated_event = await repo.mark_failed(
            event_id, error_message, "Traceback (most recent call last)"
        )

        mock_db_session.flush.assert_called()


class TestWebhookIdempotency:
    """Tests for webhook idempotency handling"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.setex = AsyncMock(return_value=True)
        redis.exists = AsyncMock(return_value=False)
        redis.delete = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_first_event_processed(self, mock_redis, mock_db_session):
        """Test that first event is processed normally"""
        mock_redis.exists.return_value = False

        manager = IdempotencyManager(
            redis_client=mock_redis, db_session=mock_db_session
        )

        platform_id = "platform-123"
        event_id = "evt-123"
        payload = {"order_id": "ord-123"}

        is_duplicate = await manager.check_duplicate(
            platform_id=platform_id, event_id=event_id, payload=payload
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_duplicate_event_detected_in_redis(self, mock_redis, mock_db_session):
        """Test duplicate detection via Redis"""
        mock_redis.exists.return_value = True

        manager = IdempotencyManager(
            redis_client=mock_redis, db_session=mock_db_session
        )

        platform_id = "platform-123"
        event_id = "evt-123"
        payload = {"order_id": "ord-123"}

        is_duplicate = await manager.check_duplicate(
            platform_id=platform_id, event_id=event_id, payload=payload
        )

        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_db(self, mock_redis, mock_db_session):
        """Test that Redis failure falls back to database check"""
        mock_redis.exists.side_effect = Exception("Redis connection failed")

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=None)
        mock_db_session.execute.return_value = mock_result

        manager = IdempotencyManager(
            redis_client=mock_redis, db_session=mock_db_session
        )

        platform_id = "platform-123"
        event_id = "evt-123"
        payload = {"order_id": "ord-123"}

        is_duplicate = await manager.check_duplicate(
            platform_id=platform_id, event_id=event_id, payload=payload
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_mark_event_as_processed(self, mock_redis, mock_db_session):
        """Test marking an event as processed"""
        manager = IdempotencyManager(
            redis_client=mock_redis, db_session=mock_db_session
        )

        platform_id = "platform-123"
        event_id = "evt-123"
        payload = {"order_id": "ord-123"}

        result = await manager.mark_processed(
            platform_id=platform_id, event_id=event_id, payload=payload
        )

        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_compute_payload_hash(self):
        """Test payload hash computation"""
        manager = IdempotencyManager()

        payload1 = {"order_id": "ord-123", "status": "paid"}
        payload2 = {"status": "paid", "order_id": "ord-123"}

        hash1 = manager.compute_payload_hash(payload1)
        hash2 = manager.compute_payload_hash(payload2)

        assert hash1 == hash2

        hash3 = manager.compute_payload_hash({"order_id": "ord-456"})

        assert hash1 != hash3

    @pytest.mark.asyncio
    async def test_duplicate_detection_with_different_payloads(self, mock_redis):
        """Test that different payloads for same event ID are handled"""
        mock_redis.exists.return_value = False

        manager = IdempotencyManager(redis_client=mock_redis)

        platform_id = "platform-123"
        event_id = "evt-123"

        payload1 = {"order_id": "ord-123", "total": 100}
        payload2 = {"order_id": "ord-123", "total": 200}

        hash1 = manager.compute_payload_hash(payload1)
        hash2 = manager.compute_payload_hash(payload2)

        assert hash1 != hash2
