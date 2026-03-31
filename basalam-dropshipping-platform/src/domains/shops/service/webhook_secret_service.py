"""
Webhook Secret Service
======================
Secure generation, encryption, and rotation of webhook secrets.

Uses Fernet symmetric encryption for storing webhook secrets.
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken

from src.core.config import get_settings


logger = logging.getLogger(__name__)


class WebhookSecretService:
    """
    Manages webhook secret lifecycle: generation, encryption, rotation.

    Secrets are 32-byte URL-safe tokens, encrypted with Fernet before storage.
    """

    # How long both old and new secrets are valid during rotation
    ROTATION_OVERLAP_PERIOD = timedelta(hours=24)

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize the service with encryption key.

        Args:
            encryption_key: Fernet key (base64-encoded 32-byte key).
                           If not provided, reads from settings.
        """
        settings = get_settings()
        key = encryption_key or settings.webhook_secret_encryption_key.get_secret_value()

        if not key:
            raise ValueError(
                "webhook_secret_encryption_key not configured. "
                "Generate one with: from cryptography.fernet import Fernet; Fernet.generate_key()"
            )

        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def generate_secret(self) -> str:
        """
        Generate a cryptographically secure webhook secret.

        Returns:
            43-character URL-safe base64 string (32 bytes)
        """
        return secrets.token_urlsafe(32)

    def encrypt_for_storage(self, secret: str) -> str:
        """
        Encrypt a webhook secret for database storage.

        Args:
            secret: The plaintext secret to encrypt

        Returns:
            Fernet-encrypted string (base64)
        """
        if not secret:
            raise ValueError("Secret cannot be empty")

        encrypted = self._fernet.encrypt(secret.encode())
        return encrypted.decode()

    def decrypt_for_verification(self, encrypted_secret: str) -> str:
        """
        Decrypt a webhook secret for signature verification.

        Args:
            encrypted_secret: The Fernet-encrypted secret from storage

        Returns:
            The plaintext secret

        Raises:
            InvalidToken: If the secret cannot be decrypted (tampered or wrong key)
        """
        if not encrypted_secret:
            raise ValueError("Encrypted secret cannot be empty")

        try:
            decrypted = self._fernet.decrypt(encrypted_secret.encode())
            return decrypted.decode()
        except InvalidToken as e:
            logger.error("Failed to decrypt webhook secret: invalid token")
            raise

    def rotate_secret(
        self,
        current_encrypted: Optional[str],
    ) -> Tuple[str, str, datetime]:
        """
        Generate a new secret for rotation.

        During rotation, both old and new secrets should be accepted.
        The caller is responsible for:
        1. Registering the new secret with the platform
        2. Storing both secrets during overlap period
        3. Removing old secret after overlap expires

        Args:
            current_encrypted: The current encrypted secret (can be None for new)

        Returns:
            Tuple of (new_secret_plaintext, new_secret_encrypted, old_secret_expires_at)
        """
        new_secret = self.generate_secret()
        new_encrypted = self.encrypt_for_storage(new_secret)

        expires_at = datetime.utcnow() + self.ROTATION_OVERLAP_PERIOD

        if current_encrypted:
            logger.info(
                f"Initiating secret rotation. Old secret valid until {expires_at}"
            )
        else:
            logger.info("Generating initial webhook secret")

        return new_secret, new_encrypted, expires_at

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
        import hmac
        import hashlib

        if timestamp is not None:
            # Signed payload format: "timestamp.payload"
            signed_payload = f"{timestamp}.".encode() + payload
        else:
            signed_payload = payload

        signature = hmac.new(
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
        import hmac
        import time

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
            logger.error(f"Signature verification error: {e}")
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
        expected_hash = expected_sig.split(",sha256=")[1] if ",sha256=" in expected_sig else expected_sig.replace("sha256=", "")

        if hmac.compare_digest(expected_hash, parts["sha256"]):
            return True, None
        return False, "Signature mismatch"

    def _verify_sha1_signature(
        self, secret: str, payload: bytes, signature_header: str
    ) -> Tuple[bool, Optional[str]]:
        """Verify legacy sha1=<hex> format (for backward compatibility)."""
        import hmac
        import hashlib

        provided_hash = signature_header.replace("sha1=", "")
        expected_hash = hmac.new(
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
