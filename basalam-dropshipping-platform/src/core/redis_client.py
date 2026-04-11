"""
Redis Client
============
Shared async Redis client with connection pooling.

Uses @lru_cache for singleton pattern — one connection pool per process.
"""
from functools import lru_cache

import redis.asyncio as redis

from src.core.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    """
    Get or create the shared async Redis client.

    Returns a cached redis.asyncio.Redis instance configured from settings.
    The client is reused across calls within the same process.
    """
    settings = get_settings()
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=50,
    )
