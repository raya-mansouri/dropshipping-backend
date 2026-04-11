"""
API Rate Limiting Middleware
============================
Fixed-window rate limiting per-user for API endpoints.

Uses in-memory counters (per-process). For multi-worker deployments,
configure a reverse proxy (e.g., nginx) or use the Redis-backed
RateLimiter in integrations/basalam/rate_limiter.py instead.
"""
import time
import uuid
import structlog
from collections import defaultdict
from typing import Dict, Tuple

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)

# In-memory rate limit state (per-process)
_local_buckets: Dict[str, Tuple[float, int]] = defaultdict(lambda: (time.time(), 0))

# Rate limits per endpoint prefix (requests per minute)
RATE_LIMITS = {
    "/api/v1/auth": 20,       # auth endpoints: 20/min
    "/api/v1/orders": 60,     # orders: 60/min
    "/api/v1/products": 60,   # products: 60/min
    "/api/v1/shops": 60,      # shops: 60/min
    "/api/v1/admin": 30,      # admin: 30/min
    "_default": 100,           # everything else: 100/min
}

WINDOW_SECONDS = 60
# Clean up keys older than this to prevent unbounded memory growth
CLEANUP_THRESHOLD = WINDOW_SECONDS * 2


class RateLimitMiddleware:
    """
    ASGI middleware that rate-limits requests per user (from X-Forwarded-For
    header) or per IP for unauthenticated requests.

    NOTE: This is a per-process fixed-window rate limiter. In multi-worker
    deployments, each worker maintains independent counters. For distributed
    rate limiting, use the Redis-backed RateLimiter instead.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Skip rate limiting for infrastructure and documentation endpoints
        if path in ("/health", "/health/", "/ping", "/", "/docs", "/redoc", "/openapi.json"):
            await self.app(scope, receive, send)
            return

        # Determine rate limit for this endpoint
        limit = RATE_LIMITS.get("_default")
        for prefix, rpm in RATE_LIMITS.items():
            if prefix != "_default" and path.startswith(prefix):
                limit = rpm
                break

        # Identify client: forwarded IP or direct connection IP
        client_id = self._get_client_id(scope)
        # Use path prefix (strip dynamic segments) for rate limit key
        key = f"ratelimit:{client_id}:{self._path_prefix(path)}"

        # Periodic cleanup of stale keys
        self._cleanup_stale_keys()

        # Check rate limit
        allowed = self._check_rate(key, limit)
        if not allowed:
            logger.warning("rate_limit_exceeded", client_id=client_id, path=path)

            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _get_client_id(self, scope: Scope) -> str:
        """Extract client identifier from scope.

        Uses X-Forwarded-For header (first IP) for reverse proxy setups,
        or falls back to the direct client IP from the ASGI scope.
        """
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if forwarded:
            return forwarded.split(",")[0].strip()

        client = scope.get("client")
        if client:
            return client[0]  # IP only, not port

        # Last resort: random per-request ID to avoid shared bucket
        logger.warning("rate_limit_no_client_id", path=scope.get("path", ""))
        return f"anon:{uuid.uuid4()}"

    def _path_prefix(self, path: str) -> str:
        """Extract a stable rate-limit key from the path.

        Strips dynamic segments (UUIDs, etc.) to avoid per-resource buckets.
        e.g. /api/v1/orders/123/items -> /api/v1/orders
        """
        parts = path.rstrip("/").split("/")
        # Keep first 4 segments for API paths: /api/v1/<resource>
        if len(parts) >= 3 and parts[1] == "api":
            return "/".join(parts[:4])
        return "/".join(parts[:3])

    def _check_rate(self, key: str, limit: int) -> bool:
        """Fixed-window rate check (in-memory)."""
        now = time.time()
        window_start, count = _local_buckets[key]

        if now - window_start > WINDOW_SECONDS:
            _local_buckets[key] = (now, 1)
            return True

        if count >= limit:
            return False

        _local_buckets[key] = (window_start, count + 1)
        return True

    def _cleanup_stale_keys(self) -> None:
        """Remove expired keys to prevent unbounded memory growth."""
        now = time.time()
        stale = [
            k for k, (ts, _) in _local_buckets.items()
            if now - ts > CLEANUP_THRESHOLD
        ]
        for k in stale:
            del _local_buckets[k]
