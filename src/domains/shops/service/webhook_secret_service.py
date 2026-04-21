"""
Webhook Secret Service
======================
Secret generation, HMAC signature verification, and rotation for webhooks.
"""

import hashlib
import hmac
import secrets
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


logger = structlog.get_logger(__name__)


class WebhookSecretService:
    """
    Manages webhook secret lifecycle: generation, rotation, and HMAC verification.
    """

    # How long both old and new secrets are valid during rotation
    ROTATION_OVERLAP_PERIOD = timedelta(hours=24)

    def generate_secret(self) -> str:
        """
        Generate a cryptographically secure webhook secret.

        Returns:
            43-character URL-safe base64 string (32 bytes)
        """
        return secrets.token_urlsafe(32)

    def rotate_secret(
        self,
        current_secret: Optional[str],
    ) -> Tuple[str, datetime]:
        """
        Generate a new secret for rotation.

        During rotation, both old and new secrets should be accepted.
        The caller is responsible for:
        1. Registering the new secret with the platform
        2. Storing both secrets during overlap period
        3. Removing old secret after overlap expires

        Args:
            current_secret: The current secret (can be None for new)

        Returns:
            Tuple of (new_secret, old_secret_expires_at)
        """
        new_secret = self.generate_secret()
        expires_at = datetime.now(timezone.utc) + self.ROTATION_OVERLAP_PERIOD

        if current_secret:
            logger.info(
                "secret_rotation_initiated",
                old_secret_expires_at=str(expires_at),
            )
        else:
            logger.info("Generating initial webhook secret")

        return new_secret, expires_at

    def compute_signature(
        self,
        secret: str,
        payload: bytes,
        timestamp: Optional[int] = None,
    ) -> str:
        """
        Compute HMAC-SHA256 signature for webhook payload.

        Args:
            secret: The plaintext webhook secret
            payload: Raw request body bytes
            timestamp: Optional timestamp for signed payload format

        Returns:
            Signature string in format "sha256=<hex>" or "t=<ts>,sha256=<hex>"
        """
        if timestamp is not None:
            # Signed payload format: "timestamp.payload"
            signed_payload = f"{timestamp}.".encode() + payload
        else:
            signed_payload = payload

        signature = hmac.HMAC(
            secret.encode(),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        if timestamp is not None:
            return f"t={timestamp},sha256={signature}"
        return f"sha256={signature}"

    def verify_signature(
        self,
        secret: str,
        payload: bytes,
        signature_header: str,
        timestamp_tolerance: int = 300,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify webhook signature with constant-time comparison.

        Supports two formats:
        - "sha256=<hex>" (simple)
        - "t=<timestamp>,sha256=<hex>" (with timestamp validation)

        Args:
            secret: The plaintext webhook secret
            payload: Raw request body bytes
            signature_header: The signature from webhook headers
            timestamp_tolerance: Max age in seconds for timestamp validation

        Returns:
            Tuple of (is_valid, error_message)
        """

        if not signature_header:
            return False, "Missing signature header"

        if not secret:
            return False, "No secret configured"

        try:
            if signature_header.startswith("t="):
                # Timestamped format: "t=1234567890,sha256=abc123..."
                return self._verify_timestamped_signature(
                    secret, payload, signature_header, timestamp_tolerance
                )
            elif signature_header.startswith("sha256="):
                # Simple format: "sha256=abc123..."
                return self._verify_simple_signature(secret, payload, signature_header)
            elif signature_header.startswith("sha1="):
                # Legacy SHA1 format (less secure, for backward compatibility)
                return self._verify_sha1_signature(secret, payload, signature_header)
            else:
                return False, f"Unknown signature format: {signature_header[:20]}..."

        except Exception as e:
            logger.error("signature_verification_error", error=str(e))
            return False, str(e)

    def _verify_simple_signature(
        self, secret: str, payload: bytes, signature_header: str
    ) -> Tuple[bool, Optional[str]]:
        """Verify simple sha256=<hex> format."""
        expected_sig = self.compute_signature(secret, payload)
        provided_sig = signature_header

        if hmac.compare_digest(expected_sig, provided_sig):
            return True, None
        return False, "Signature mismatch"

    def _verify_timestamped_signature(
        self,
        secret: str,
        payload: bytes,
        signature_header: str,
        tolerance: int,
    ) -> Tuple[bool, Optional[str]]:
        """Verify t=<ts>,sha256=<hex> format with timestamp validation."""
        import time

        parts = {}
        for part in signature_header.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                parts[key] = value

        if "t" not in parts or "sha256" not in parts:
            return False, "Missing timestamp or signature in header"

        try:
            timestamp = int(parts["t"])
        except ValueError:
            return False, "Invalid timestamp format"

        # Validate timestamp is within tolerance
        current_time = int(time.time())
        time_diff = abs(current_time - timestamp)

        if time_diff > tolerance:
            return False, f"Timestamp expired: {time_diff}s > {tolerance}s tolerance"

        # Compute expected signature
        expected_sig = self.compute_signature(secret, payload, timestamp)
        expected_hash = (
            expected_sig.split(",sha256=")[1]
            if ",sha256=" in expected_sig
            else expected_sig.replace("sha256=", "")
        )

        if hmac.compare_digest(expected_hash, parts["sha256"]):
            return True, None
        return False, "Signature mismatch"

    def _verify_sha1_signature(
        self, secret: str, payload: bytes, signature_header: str
    ) -> Tuple[bool, Optional[str]]:
        """Verify legacy sha1=<hex> format (for backward compatibility)."""

        provided_hash = signature_header.replace("sha1=", "")
        expected_hash = hmac.HMAC(
            secret.encode(),
            payload,
            hashlib.sha1,
        ).hexdigest()

        if hmac.compare_digest(expected_hash, provided_hash):
            logger.warning("Using deprecated SHA1 signature verification")
            return True, None
        return False, "SHA1 signature mismatch"


def get_webhook_secret_service() -> WebhookSecretService:
    """Factory function to get WebhookSecretService instance."""
    return WebhookSecretService()
