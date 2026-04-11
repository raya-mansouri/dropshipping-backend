"""
Webhook Processing Infrastructure
=================================
Base webhook processor with signature verification and event data extraction.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import hashlib
import hmac
import structlog

from pydantic import BaseModel


logger = structlog.get_logger(__name__)


class WebhookEvent(BaseModel):
    """Standard webhook event structure"""

    event_id: str
    event_type: str
    platform_id: str
    timestamp: datetime
    payload: Dict[str, Any]
    headers: Dict[str, str]


class WebhookProcessor(ABC):
    """
    Base class for all webhook processors.

    Provides common functionality for signature verification,
    event data extraction, timestamp validation, and processing workflow.
    """

    MAX_TIMESTAMP_AGE_SECONDS = 300  # 5 minutes

    def __init__(self, secret: str):
        self.secret = secret

    @abstractmethod
    async def process(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Process the webhook event.

        Args:
            payload: The webhook payload data
            headers: HTTP headers from the webhook request

        Returns:
            True if processing was successful, False otherwise
        """
        pass

    def verify_signature(
        self,
        payload: str | bytes,
        signature: Optional[str],
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verify the webhook signature using HMAC-SHA256.

        Args:
            payload: The raw payload string or bytes
            signature: The signature from the webhook header
            secret: Optional override for the default secret

        Returns:
            True if signature is valid, False otherwise
        """
        if not signature:
            logger.warning("No signature provided for webhook")
            return False

        secret_key = secret or self.secret
        if not secret_key:
            logger.warning("No secret configured for webhook verification")
            return False

        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        expected_signature = hmac.new(
            secret_key.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    def validate_timestamp(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        max_age_seconds: Optional[int] = None,
    ) -> bool:
        """
        Validate that the webhook timestamp is within acceptable range.

        Rejects webhooks that are older than 5 minutes (or configured max age)
        to prevent replay attacks.

        Args:
            payload: The webhook payload
            headers: HTTP headers
            max_age_seconds: Maximum allowed age in seconds (default: 300 = 5 min)

        Returns:
            True if timestamp is valid and within range, False otherwise
        """
        max_age = max_age_seconds or self.MAX_TIMESTAMP_AGE_SECONDS

        timestamp = self.extract_timestamp(payload, headers)

        if timestamp is None:
            logger.warning("No timestamp found in webhook payload or headers")
            return False

        now = datetime.now(timezone.utc)
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_timestamp_format", timestamp=str(timestamp))
                return False

        age_seconds = abs((now - timestamp.replace(tzinfo=None)).total_seconds())

        if age_seconds > max_age:
            logger.warning(
                "webhook_timestamp_too_old",
                age_seconds=round(age_seconds, 1),
                max_age=max_age,
            )
            return False

        return True

    def extract_timestamp(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Optional[datetime]:
        """
        Extract timestamp from payload or headers.

        Args:
            payload: The webhook payload
            headers: HTTP headers

        Returns:
            Timestamp if found, None otherwise
        """
        timestamp_str = (
            payload.get("timestamp")
            or payload.get("created_at")
            or headers.get("X-Webhook-Timestamp")
            or headers.get("X-Timestamp")
        )

        if timestamp_str:
            try:
                if isinstance(timestamp_str, datetime):
                    return timestamp_str
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                try:
                    ts = int(timestamp_str)
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                except (ValueError, OSError):
                    pass

        return None

    def extract_event_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant event data from the webhook payload.

        Args:
            payload: The webhook payload

        Returns:
            Dictionary containing extracted event data
        """
        return payload.get("data", payload)

    def get_event_type(self, payload: Dict[str, Any], headers: Dict[str, str]) -> str:
        """
        Extract event type from payload or headers.

        Args:
            payload: The webhook payload
            headers: HTTP headers

        Returns:
            The event type string
        """
        return payload.get("event_type") or headers.get("X-Webhook-Event", "unknown")

    def get_event_id(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Optional[str]:
        """
        Extract event ID for idempotency tracking.

        Args:
            payload: The webhook payload
            headers: HTTP headers

        Returns:
            The event ID if available
        """
        return (
            payload.get("event_id")
            or headers.get("X-Webhook-Id")
            or headers.get("X-Request-Id")
        )


class WebhookProcessorRegistry:
    """Registry for managing webhook processors by platform and event type.

    Supports both string event types (e.g. "product.created") and numeric
    Basalam event IDs. Numeric IDs are resolved to string event types via
    the BASALAM_EVENT_MAP before lookup.
    """

    # Basalam numeric event_id → internal event type string
    BASALAM_EVENT_MAP: Dict[int, str] = {
        8: "product.changes",      # PRODUCT_CREATE_CHANGES
        5: "order.created",        # VENDOR_NEW_ORDER
        7: "order.parcel_changed", # VENDOR_PARCEL_CHANGES
        3: "inventory.changed",    # VENDOR_ORDER_ITEM_CHANGES
    }

    def __init__(self):
        self._processors: Dict[str, Dict[str, WebhookProcessor]] = {}

    def register(
        self, platform_id: str, event_type: str, processor: WebhookProcessor
    ) -> None:
        """Register a processor for a specific platform and event type"""
        if platform_id not in self._processors:
            self._processors[platform_id] = {}
        self._processors[platform_id][event_type] = processor

    def get(
        self,
        platform_id: str,
        event_type: Optional[str] = None,
        event_id: Optional[int] = None,
    ) -> Optional[WebhookProcessor]:
        """
        Get processor for a specific platform and event type.

        For Basalam, pass ``event_id`` (numeric) which is resolved to a
        string event type via ``BASALAM_EVENT_MAP``.
        For other platforms, pass ``event_type`` directly.
        """
        resolved = event_type
        if event_id is not None and platform_id == "basalam":
            resolved = self.BASALAM_EVENT_MAP.get(event_id)
            if resolved is None:
                logger.warning(
                    "unknown_basalam_event_id",
                    event_id=event_id,
                    known_event_ids=list(self.BASALAM_EVENT_MAP.keys()),
                )
                return None

        if resolved is None:
            return None

        return self._processors.get(platform_id, {}).get(resolved)

    def list_platforms(self) -> list[str]:
        """List all registered platforms"""
        return list(self._processors.keys())

    def list_event_types(self, platform_id: str) -> list[str]:
        """List all registered event types for a platform"""
        return list(self._processors.get(platform_id, {}).keys())
