from fastapi import FastAPI
from contextlib import asynccontextmanager
import httpx
import redis.asyncio as redis
from app.routers import comments, comment_analytics
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    app.state.http_client = httpx.AsyncClient(timeout=5.0)

    app.state.redis = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True
    )

    print("Lifespan: resources created")
    yield

    # --- Shutdown ---
    await app.state.http_client.aclose()
    await app.state.redis.aclose()
    print("Lifespan: resources closed")

app = FastAPI(lifespan=lifespan, title="Comments Microservice")

app.include_router(comments.router, prefix="/api", tags=["comments"])
app.include_router(comment_analytics.router, prefix="/api", tags=["comment_analytics"])

@app.get("/")
async def root():
    return {"message": "Comments service is running"}


