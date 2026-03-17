"""
Webhook Processing Infrastructure
==================================
Base webhook processor with signature verification and event data extraction.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
import hashlib
import hmac
import logging

from pydantic import BaseModel


logger = logging.getLogger(__name__)


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
    event data extraction, and processing workflow.
    """

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
    """Registry for managing webhook processors by platform and event type"""

    def __init__(self):
        self._processors: Dict[str, Dict[str, WebhookProcessor]] = {}

    def register(
        self, platform_id: str, event_type: str, processor: WebhookProcessor
    ) -> None:
        """Register a processor for a specific platform and event type"""
        if platform_id not in self._processors:
            self._processors[platform_id] = {}
        self._processors[platform_id][event_type] = processor

    def get(self, platform_id: str, event_type: str) -> Optional[WebhookProcessor]:
        """Get processor for a specific platform and event type"""
        return self._processors.get(platform_id, {}).get(event_type)

    def list_platforms(self) -> list[str]:
        """List all registered platforms"""
        return list(self._processors.keys())

    def list_event_types(self, platform_id: str) -> list[str]:
        """List all registered event types for a platform"""
        return list(self._processors.get(platform_id, {}).keys())
