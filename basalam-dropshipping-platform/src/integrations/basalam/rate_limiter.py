import asyncio
from typing import Optional, Dict

import redis.asyncio as redis


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
        self._locks: dict[str, asyncio.Lock] = {}
        self.endpoint_limits = endpoint_limits or self.DEFAULT_ENDPOINT_LIMITS

    def _get_bucket_key(self, endpoint: str) -> str:
        return f"ratelimit:basalam:{endpoint}"

    def _get_lock(self, endpoint: str) -> asyncio.Lock:
        if endpoint not in self._locks:
            self._locks[endpoint] = asyncio.Lock()
        return self._locks[endpoint]

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

        current = await self.redis.get(key)
        if current is None:
            await self.redis.setex(key, period, rate)
            return True

        current_value = int(current)
        if current_value > 0:
            await self.redis.decr(key)
            return True
        return False

    async def wait_if_needed(self, endpoint: str, rate: int = None, period: int = None):
        lock = self._get_lock(endpoint)
        async with lock:
            while not await self.check_limit(endpoint, rate, period):
                await asyncio.sleep(0.1)

    async def get_remaining(self, endpoint: str) -> int:
        key = self._get_bucket_key(endpoint)
        limits = self._get_endpoint_limits(endpoint)
        current = await self.redis.get(key)
        if current is None:
            return limits.get("rate", self.default_rate)
        return max(0, int(current))

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
