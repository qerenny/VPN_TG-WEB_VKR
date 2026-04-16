from backend.utils.async_redis_client import AsyncRedisClient, RedisClientError
from shared.utils.async_redis_client import AsyncRedisClient as SharedAsyncRedisClient
from shared.utils.async_redis_client import RedisClientError as SharedRedisClientError


def test_backend_async_redis_client_reexports_shared_implementation():
    assert AsyncRedisClient is SharedAsyncRedisClient
    assert RedisClientError is SharedRedisClientError
