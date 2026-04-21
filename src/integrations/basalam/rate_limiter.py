import asyncio
import structlog
import time
from typing import Optional, Dict

import redis.asyncio as redis

logger = structlog.get_logger(__name__)

# Atomic token bucket Lua script
# Returns: [remaining_tokens, limit, period_ttl] or [-1, 0, 0] on rate exceeded
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local period = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

-- Get current bucket state
local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

-- Initialize if not exists
if tokens == nil then
    tokens = rate
    last_refill = now
end

-- Calculate tokens to add based on elapsed time
local elapsed = now - last_refill
local refill = (elapsed / period) * rate
tokens = math.min(rate, tokens + refill)

-- Check if enough tokens
if tokens >= requested then
    tokens = tokens - requested
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, period * 2)
    return {math.floor(tokens), rate, period}
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, period * 2)
    return {-1, rate, period}
end
"""


class RateLimitWaitExceeded(Exception):
    """Raised when rate limit wait exceeds the configured maximum."""
    pass


class RateLimiter:
    DEFAULT_ENDPOINT_LIMITS = {
        "products": {"rate": 100, "period": 60},
        "orders": {"rate": 50, "period": 60},
        "inventory": {"rate": 200, "period": 60},
        "webhooks": {"rate": 30, "period": 60},
        "default": {"rate": 100, "period": 60},
    }

    def __init__(
        self,
        redis_client: redis.Redis,
        default_rate: int = 100,
        default_period: int = 60,
        endpoint_limits: Optional[Dict[str, Dict[str, int]]] = None,
    ):
        self.redis = redis_client
        self.default_rate = default_rate
        self.default_period = default_period
        self.endpoint_limits = endpoint_limits or self.DEFAULT_ENDPOINT_LIMITS
        self._lua_script = self.redis.register_script(TOKEN_BUCKET_LUA)

    def _get_bucket_key(self, endpoint: str) -> str:
        return f"ratelimit:basalam:{endpoint}"

    def _get_endpoint_limits(self, endpoint: str) -> Dict[str, int]:
        """Get rate limits for a specific endpoint."""
        return self.endpoint_limits.get(
            endpoint,
            self.endpoint_limits.get(
                "default",
                {
                    "rate": self.default_rate,
                    "period": self.default_period,
                },
            ),
        )

    async def check_limit(
        self, endpoint: str, rate: int = None, period: int = None
    ) -> bool:
        limits = self._get_endpoint_limits(endpoint)
        rate = rate or limits.get("rate", self.default_rate)
        period = period or limits.get("period", self.default_period)
        key = self._get_bucket_key(endpoint)
        now = time.time()
        result = await self._lua_script.execute(keys=[key], args=[rate, period, now, 1])
        remaining = result[0]
        return remaining >= 0

    async def wait_if_needed(
        self, endpoint: str, rate: int = None, period: int = None, max_wait: float = 60.0
    ):
        """Wait until rate limit allows the request, with a maximum wait time."""
        waited = 0.0
        while not await self.check_limit(endpoint, rate, period):
            if waited >= max_wait:
                raise RateLimitWaitExceeded(f"Rate limit wait exceeded {max_wait}s for {endpoint}")
            await asyncio.sleep(0.1)
            waited += 0.1

    async def get_remaining(self, endpoint: str) -> int:
        key = self._get_bucket_key(endpoint)
        tokens = await self.redis.hget(key, "tokens")
        if tokens is None:
            limits = self._get_endpoint_limits(endpoint)
            return limits.get("rate", self.default_rate)
        return max(0, int(float(tokens)))

    async def get_reset_time(self, endpoint: str) -> int:
        """Get seconds until rate limit resets."""
        key = self._get_bucket_key(endpoint)
        ttl = await self.redis.ttl(key)
        return max(0, ttl)

    async def reset(self, endpoint: str):
        key = self._get_bucket_key(endpoint)
        await self.redis.delete(key)

    async def set_endpoint_limits(self, endpoint: str, rate: int, period: int) -> None:
        """Set custom rate limits for an endpoint."""
        self.endpoint_limits[endpoint] = {"rate": rate, "period": period}

    async def update_from_headers(self, endpoint: str, headers: Dict[str, str]) -> None:
        """Parse X-RateLimit-* headers from API response and update adaptive limits."""
        from src.core.metrics import rate_limit_remaining

        remaining = headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            rate_limit_remaining.labels(endpoint=endpoint).set(int(remaining))

        limit = headers.get("X-RateLimit-Limit")
        reset = headers.get("X-RateLimit-Reset")

        if limit and reset:
            try:
                parsed_limit = int(limit)
                parsed_reset = int(reset)
                if parsed_limit > 0 and parsed_reset > 0:
                    await self.set_endpoint_limits(
                        endpoint, rate=parsed_limit, period=parsed_reset
                    )
                    logger.debug(
                        "rate_limits_updated",
                        endpoint=endpoint,
                        limit=parsed_limit,
                        reset=parsed_reset,
                    )
            except (ValueError, TypeError) as e:
                logger.debug(
                    "rate_limit_header_parse_failed",
                    endpoint=endpoint,
                    limit_header=limit,
                    reset_header=reset,
                    error=str(e),
                )
