from fastapi import FastAPI
from app.routers import comments, comment_analytics

app = FastAPI(title="Comments Microservice")

app.include_router(comments.router, prefix="/api", tags=["comments"])
app.include_router(comment_analytics.router, prefix="/api", tags=["comment_analytics"])

@app.get("/")
async def root():
    return {"message": "Comments service is running"}
