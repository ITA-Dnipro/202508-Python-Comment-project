from fastapi import FastAPI, Request
from app.routers import comments

app = FastAPI(title="Comments Microservice")

app.include_router(comments.router, prefix="/api", tags=["comments"])

@app.get("/")
async def root():
    return {"message": "Comments service is running"}
