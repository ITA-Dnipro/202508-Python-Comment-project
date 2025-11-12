import os
import logging
from datetime import datetime
from bson import ObjectId

import httpx
from fastapi import APIRouter, HTTPException, Header
from app.database import comments_collection

logger = logging.getLogger(__name__)

PROJECTS_SERVICE_URL = os.getenv("PROJECTS_SERVICE_URL", "http://web:8000/api/projects/startup-projects")

router = APIRouter(prefix="/comments/analytics", tags=["Comment Analytics"])

# -------------------------------------------------------
# GET: Analytics for one project
# -------------------------------------------------------
@router.get("/projects/{project_id}/")
async def get_project_comment_analytics(project_id: int):
    """
    Return comment analytics for a specific project:
    - total comments
    - unique users
    - average response time (optional)
    """
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
        return {
            "project_id": project_id,
            "total_comments": 0,
            "unique_users": 0,
            "average_response_time_hours": 0,
        }

    stats = data[0]
    total_comments = stats["total_comments"]
    unique_users = len(stats["unique_users"])

    avg_response_time = 0
    if total_comments > 1:
        delta = stats["last_comment"] - stats["first_comment"]
        avg_response_time = round(delta.total_seconds() / 3600 / total_comments, 2)

    return {
        "project_id": project_id,
        "total_comments": total_comments,
        "unique_users": unique_users,
        "average_response_time_hours": avg_response_time,
    }


# -------------------------------------------------------
# GET: Global summary for startup
# -------------------------------------------------------
@router.get("/summary/")
async def get_global_comment_analytics(http_user_id: int = Header(None, alias="user-id"), token: str = Header(None, alias="Authorization")):
    """
    Return aggregated comment analytics for all projects of the current startup user.
    Requires user-id header from Krakend.
    """
    if not http_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Fetch all startup's projects
    async with httpx.AsyncClient() as client:
        # ToDo: implement this endpoint in monolith(get startup projects from current startuper)
        # now endpoint returns all projects
        resp = await client.get(f"{PROJECTS_SERVICE_URL}/?owner={http_user_id}", headers={"Authorization": token})
        if resp.status_code != 200:
            logger.error(f"Failed to fetch projects for user {http_user_id}: {resp.text}")
            raise HTTPException(status_code=500, detail="Failed to fetch projects")
        projects = resp.json()

    results = []
    for project in projects:
        project_id = project.get("id")
        if not project_id:
            continue

        pipeline = [
            {"$match": {"project_id": project_id, "is_deleted": False}},
            {
                "$group": {
                    "_id": None,
                    "total_comments": {"$sum": 1},
                    "unique_users": {"$addToSet": "$author_id"},
                }
            },
        ]
        data = await comments_collection.aggregate(pipeline).to_list(length=1)
        if not data:
            continue

        results.append({
            "project_id": project_id,
            "project_name": project.get("title", "Untitled"),
            "total_comments": data[0]["total_comments"],
            "unique_users": len(data[0]["unique_users"]),
        })

    return results
