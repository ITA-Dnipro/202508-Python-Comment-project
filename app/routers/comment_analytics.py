import os
import logging
from datetime import datetime
from typing import Optional

import httpx
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Header, Depends

from app.database import comments_collection
from app.dependencies import get_http_client
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

PROJECTS_SERVICE_URL = os.getenv(
    "PROJECTS_SERVICE_URL",
    "http://web:8000/api/projects/startup-projects"
)

router = APIRouter(prefix="/comments/analytics", tags=["Comment Analytics"])


# -------------------------------------------------------
# Helper: analytics for one project
# -------------------------------------------------------
async def calculate_project_stats(project_id: int):
    pipeline = [
        {"$match": {"project_id": project_id, "is_deleted": False}},
        {
            "$group": {
                "_id": None,
                "total_comments": {"$sum": 1},
                "unique_users": {"$addToSet": "$author_id"},
                "first_comment": {"$min": "$created_at"},
                "last_comment": {"$max": "$created_at"},
            }
        },
    ]

    data = await comments_collection.aggregate(pipeline).to_list(length=1)
    if not data:
        return None

    stats = data[0]

    total_comments = stats["total_comments"]
    unique_users = len(stats["unique_users"])

    avg_resp = 0
    if total_comments > 1:
        delta = stats["last_comment"] - stats["first_comment"]
        avg_resp = round(delta.total_seconds() / 3600 / total_comments, 2)

    return {
        "project_id": project_id,
        "total_comments": total_comments,
        "unique_users": unique_users,
        "average_response_time_hours": avg_resp,
    }


# -------------------------------------------------------
# GET: Analytics for one project
# -------------------------------------------------------
@router.get("/projects/{project_id}/")
async def get_project_comment_analytics(project_id: int):
    stats = await calculate_project_stats(project_id)
    if not stats:
        return {
            "project_id": project_id,
            "total_comments": 0,
            "unique_users": 0,
            "average_response_time_hours": 0,
        }
    return stats


# -------------------------------------------------------
# GET: Global summary for startup (all projects)
# -------------------------------------------------------
@router.get("/summary/")
async def get_global_comment_analytics(
    http_user_id: int = Header(None, alias="user-id"),
    authorization: str = Header(None, alias="Authorization"),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    """
    Returns aggregated analytics for all projects owned by the startup user.
    """
    # Fetch startup projects
    if not http_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    resp = await client.get(
        f"{PROJECTS_SERVICE_URL}/?owner={http_user_id}",
        headers={"Authorization": authorization},
    )

    if resp.status_code != 200:
        logger.error(f"Failed to fetch projects for user {http_user_id}: {resp.text}")
        raise HTTPException(status_code=500, detail="Failed to fetch projects")

    projects = resp.json()
    results = []

    for project in projects:
        project_id = project.get("id")
        if not project_id:
            continue

        stats = await calculate_project_stats(project_id)
        if stats:
            stats["project_name"] = project.get("title", "Untitled")
            results.append(stats)

    return results
