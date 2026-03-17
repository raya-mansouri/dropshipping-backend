import asyncio
from typing import Optional

import redis.asyncio as redis


class RateLimiter:
    def __init__(
        self,
        redis_client: redis.Redis,
        default_rate: int = 100,
        default_period: int = 60,
    ):
        self.redis = redis_client
        self.default_rate = default_rate
        self.default_period = default_period
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_bucket_key(self, endpoint: str) -> str:
        return f"ratelimit:basalam:{endpoint}"

    def _get_lock(self, endpoint: str) -> asyncio.Lock:
        if endpoint not in self._locks:
            self._locks[endpoint] = asyncio.Lock()
        return self._locks[endpoint]

    async def check_limit(
        self, endpoint: str, rate: int = None, period: int = None
    ) -> bool:
        key = self._get_bucket_key(endpoint)
        rate = rate or self.default_rate
        period = period or self.default_period

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
        current = await self.redis.get(key)
        if current is None:
            return self.default_rate
        return max(0, int(current))

    async def reset(self, endpoint: str):
        key = self._get_bucket_key(endpoint)
        await self.redis.delete(key)
