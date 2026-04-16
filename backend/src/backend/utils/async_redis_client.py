"""Backward-compatible backend import for the shared Redis client."""

from shared.utils.async_redis_client import AsyncRedisClient, RedisClientError

__all__ = ["AsyncRedisClient", "RedisClientError"]
