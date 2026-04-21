"""
Webhook Security Module
=======================
Security middleware for incoming webhooks: IP allowlisting, rate limiting, timestamp validation.
"""
import ipaddress
import structlog
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Callable
from functools import wraps

from fastapi import Request, HTTPException
from pydantic import BaseModel

from src.core.config import get_settings
from src.core.webhook_metrics import record_security_event as metrics_security_event


logger = structlog.get_logger(__name__)


class SecurityEvent:
    """Security event types for logging"""
    IP_REJECTED = "ip_rejected"
    RATE_LIMITED = "rate_limited"
    TIMESTAMP_INVALID = "timestamp_invalid"
    SIGNATURE_INVALID = "signature_invalid"
    DUPLICATE_EVENT = "duplicate_event"


class IPAllowlistValidator:
    """
    Validates webhook source IPs against platform allowlist.

    Supports CIDR notation for IP ranges (e.g., "192.168.1.0/24").
    """

    def __init__(self):
        self._cache: Dict[str, List[ipaddress.IPv4Network | ipaddress.IPv6Network]] = {}

    def is_ip_allowed(
        self,
        client_ip: str,
        allowed_cidrs: List[str],
        platform_code: str,
    ) -> bool:
        """
        Check if client IP is in allowed CIDR ranges.

        Args:
            client_ip: The client's IP address
            allowed_cidrs: List of CIDR strings (e.g., ["192.168.1.0/24", "10.0.0.1"])
            platform_code: Platform code for caching

        Returns:
            True if IP is allowed (or no allowlist configured)
        """
        if not allowed_cidrs:
            # No allowlist = allow all
            return True

        try:
            client_addr = ipaddress.ip_address(client_ip)
        except ValueError:
            logger.warning(
                "Invalid client IP address",
                extra={
                    "event_type": SecurityEvent.IP_REJECTED,
                    "client_ip": client_ip,
                    "platform_code": platform_code,
                    "reason": "invalid_ip_format",
                }
            )
            return False

        # Parse CIDR ranges
        networks = self._parse_cidrs(allowed_cidrs, platform_code)

        for network in networks:
            try:
                if client_addr in network:
                    return True
            except TypeError:
                # IPv4 vs IPv6 mismatch, continue checking
                continue

        logger.warning(
            "IP not in allowlist",
            extra={
                "event_type": SecurityEvent.IP_REJECTED,
                "client_ip": client_ip,
                "platform_code": platform_code,
                "allowed_cidrs": allowed_cidrs,
            }
        )
        return False

    def _parse_cidrs(
        self, cidrs: List[str], platform_code: str
    ) -> List[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse and cache CIDR ranges."""
        cache_key = f"{platform_code}:{':'.join(sorted(cidrs))}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        networks = []
        for cidr in cidrs:
            try:
                # Handle single IP (no /prefix)
                if "/" not in cidr:
                    cidr = f"{cidr}/32" if ":" not in cidr else f"{cidr}/128"
                networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError as e:
                logger.warning(
                    "invalid_cidr_in_allowlist",
                    cidr=cidr,
                    platform_code=platform_code,
                    error=str(e),
                )

        self._cache[cache_key] = networks
        return networks


class WebhookRateLimiter:
    """
    Redis-based rate limiter for incoming webhooks.

    Uses sliding window algorithm for accurate rate limiting.
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    async def is_allowed(
        self,
        platform_code: str,
        integration_id: str,
        rate_limit_config: Optional[Dict[str, int]],
    ) -> tuple[bool, Optional[int]]:
        """
        Check if request is within rate limit.

        Args:
            platform_code: Platform identifier
            integration_id: Integration UUID
            rate_limit_config: Dict with 'rate' and 'period' keys

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        if not rate_limit_config:
            rate_limit_config = {"rate": 100, "period": 60}

        rate = rate_limit_config.get("rate", 100)
        period = rate_limit_config.get("period", 60)

        key = f"webhook:ratelimit:{platform_code}"

        try:
            current_time = time.time()
            window_start = current_time - period

            # Use Redis pipeline for atomic operations
            async with self.redis.pipeline() as pipe:
                # Remove old entries
                pipe.zremrangebyscore(key, 0, window_start)
                # Count current entries
                pipe.zcard(key)
                # Add current request (score = timestamp)
                pipe.zadd(key, {str(current_time): current_time})
                # Set expiry
                pipe.expire(key, period + 1)

                results = await pipe.execute()
                current_count = results[1]  # zcard result

            if current_count >= rate:
                # Calculate retry-after
                oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    retry_after = int(oldest_time + period - current_time) + 1
                    retry_after = max(1, retry_after)
                else:
                    retry_after = period

                logger.warning(
                    "Webhook rate limit exceeded",
                    extra={
                        "event_type": SecurityEvent.RATE_LIMITED,
                        "platform_code": platform_code,
                        "integration_id": integration_id,
                        "current_count": current_count,
                        "limit": rate,
                        "period": period,
                    }
                )
                return False, retry_after

            return True, None

        except Exception as e:
            # Fail closed: if Redis is down, reject the request.
            # This prevents a Redis outage from silently disabling rate limiting.
            logger.error(
                "rate_limiter_error_fail_closed",
                error=str(e),
                platform_code=platform_code,
                integration_id=integration_id,
            )
            return False, 60  # Reject with a 60s retry-after


class TimestampValidator:
    """
    Validates webhook timestamps to prevent replay attacks.
    """

    def __init__(self, default_tolerance: int = 300):
        self.default_tolerance = default_tolerance

    def validate_timestamp(
        self,
        timestamp: Optional[int | str | datetime],
        tolerance: Optional[int] = None,
        platform_code: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate webhook timestamp is within acceptable range.

        Args:
            timestamp: Unix timestamp, ISO string, or datetime
            tolerance: Max age in seconds (default from config)
            platform_code: For logging context

        Returns:
            Tuple of (is_valid, error_message)
        """
        if timestamp is None:
            # No timestamp = skip validation (platform doesn't send)
            return True, None

        tolerance = tolerance or self.default_tolerance

        # Parse timestamp
        try:
            if isinstance(timestamp, str):
                if timestamp.isdigit():
                    ts_value = int(timestamp)
                else:
                    # ISO format
                    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    ts_value = int(parsed.timestamp())
            elif isinstance(timestamp, datetime):
                ts_value = int(timestamp.timestamp())
            else:
                ts_value = int(timestamp)
        except (ValueError, TypeError) as e:
            logger.warning(
                "Invalid timestamp format",
                extra={
                    "event_type": SecurityEvent.TIMESTAMP_INVALID,
                    "timestamp": str(timestamp),
                    "platform_code": platform_code,
                    "reason": "invalid_format",
                }
            )
            return False, f"Invalid timestamp format: {e}"

        current_time = int(time.time())
        time_diff = current_time - ts_value

        # Check if too old
        if time_diff > tolerance:
            logger.warning(
                "Webhook timestamp too old",
                extra={
                    "event_type": SecurityEvent.TIMESTAMP_INVALID,
                    "platform_code": platform_code,
                    "age_seconds": time_diff,
                    "tolerance": tolerance,
                    "reason": "expired",
                }
            )
            return False, f"Timestamp expired: {time_diff}s > {tolerance}s tolerance"

        # Check if in future (clock skew tolerance: use tolerance / 10, minimum 30s)
        future_tolerance = max(30, tolerance // 10)
        if time_diff < -future_tolerance:
            logger.warning(
                "Webhook timestamp in future",
                extra={
                    "event_type": SecurityEvent.TIMESTAMP_INVALID,
                    "platform_code": platform_code,
                    "future_seconds": abs(time_diff),
                    "reason": "future_timestamp",
                }
            )
            return False, f"Timestamp in future: {abs(time_diff)}s ahead"

        return True, None

    def extract_timestamp(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Optional[int]:
        """
        Extract timestamp from headers or payload.

        Checks common header names and payload fields.
        """
        # Check headers
        header_candidates = [
            "X-Webhook-Timestamp",
            "X-Timestamp",
            "X-Event-Timestamp",
            "Date",
        ]

        for header in header_candidates:
            if header in headers:
                try:
                    return int(headers[header])
                except (ValueError, TypeError):
                    continue

        # Check payload
        payload_candidates = [
            payload.get("timestamp"),
            payload.get("event_timestamp"),
            payload.get("created_at"),
            payload.get("occurred_at"),
        ]

        for ts in payload_candidates:
            if ts is not None:
                return ts

        return None


class SecurityAuditLogger:
    """
    Logs security events for audit and monitoring.
    """

    def log_security_event(
        self,
        event_type: str,
        platform_code: str,
        integration_id: Optional[str],
        client_ip: Optional[str],
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Log a security event.

        Args:
            event_type: One of SecurityEvent constants
            platform_code: Platform identifier
            integration_id: Integration UUID if available
            client_ip: Client IP address
            details: Additional event details
        """
        event_data = {
            "event_type": event_type,
            "platform_code": platform_code,
            "integration_id": str(integration_id) if integration_id else None,
            "client_ip": client_ip,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(details or {}),
        }

        # Log with appropriate level
        if event_type in [SecurityEvent.IP_REJECTED, SecurityEvent.SIGNATURE_INVALID]:
            logger.warning("Webhook security event", extra=event_data)
        else:
            logger.info("Webhook security event", extra=event_data)

        # Record Prometheus metric
        metrics_security_event(event_type=event_type, platform=platform_code)


# Singleton instances
_ip_validator: Optional[IPAllowlistValidator] = None
_timestamp_validator: Optional[TimestampValidator] = None
_audit_logger: Optional[SecurityAuditLogger] = None


def get_ip_validator() -> IPAllowlistValidator:
    """Get singleton IP validator instance."""
    global _ip_validator
    if _ip_validator is None:
        _ip_validator = IPAllowlistValidator()
    return _ip_validator


def get_timestamp_validator() -> TimestampValidator:
    """Get singleton timestamp validator instance."""
    global _timestamp_validator
    if _timestamp_validator is None:
        settings = get_settings()
        _timestamp_validator = TimestampValidator(
            default_tolerance=settings.webhook_default_timestamp_tolerance
        )
    return _timestamp_validator


def get_audit_logger() -> SecurityAuditLogger:
    """Get singleton audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = SecurityAuditLogger()
    return _audit_logger
