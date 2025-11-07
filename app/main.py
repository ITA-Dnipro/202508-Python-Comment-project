from fastapi import FastAPI, Request
from app.routers import comments
import logging

logger = logging.getLogger("headers_logger")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Comments Microservice")

app.include_router(comments.router, prefix="/api", tags=["comments"])

@app.get("/")
async def root():
    return {"message": "Comments service is running"}


@app.middleware("http")
async def log_request_headers(request: Request, call_next):
    headers_dict = dict(request.headers)
    logger.info(f"📦 Incoming headers: {headers_dict}")
    response = await call_next(request)
    return response