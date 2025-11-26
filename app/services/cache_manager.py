import aioredis
import json
import os
from app.schemas import CommentRead

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
CACHE_TTL = 300  # 5 min

async def get_redis():
    return await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

async def get_project_comments_cached(project_id: int, loader):
    redis = await get_redis()
    cache_key = f"comments:project:{project_id}"
    data = await redis.get(cache_key)

    if data:
        return [CommentRead(**c) for c in json.loads(data)]

    comments = await loader()
    await redis.set(cache_key, json.dumps([c.dict() for c in comments]), ex=CACHE_TTL)
    return comments
