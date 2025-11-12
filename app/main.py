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

