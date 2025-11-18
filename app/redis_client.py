import aioredis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

_redis = None

async def get_redis():
    """
    Singleton Redis client.
    """
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
    return _redis
