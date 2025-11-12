import logging
import os
import json
from datetime import datetime, timezone
from bson import ObjectId

import httpx
import aioredis
from pymongo import ASCENDING
from fastapi import (
    APIRouter,
    HTTPException,
    Header,
    status,
    Request,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from app.database import comments_collection
from app.schemas import CommentCreate, CommentRead
from app.models import CommentModel
from app.tasks import notify_project_owner, publish_event

# -------------------------------------------------------
# CONFIG & GLOBALS
# -------------------------------------------------------
PROJECTS_SERVICE_URL = os.getenv(
    "PROJECTS_SERVICE_URL", "http://web:8000/api/projects/startup-projects"
)
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://web:8000/api/users") # === for the future updates
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://web:8000/notifications/")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
CACHE_TTL = 300  # seconds

router = APIRouter(prefix="/comments", tags=["Comments"])
logger = logging.getLogger(__name__)

# -------------------------------------------------------
# Redis utils
# -------------------------------------------------------
async def get_redis():
    return await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)


# -------------------------------------------------------
# Create Comment
# -------------------------------------------------------
@router.post("/projects/{project_id}/", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    project_id: int,
    comment: CommentCreate,
    request: Request,
    http_user_id: int = Header(None, alias="user-id"),
    http_role: str = Header(None, alias="role"),
):
    """
    Add a comment to a project.
    Headers: user-id, role
    Body: {"text": "..."}
    """

    if not http_user_id or not http_role:
        logger.warning(f"Missing auth headers: user-id={http_user_id}, role={http_role}")
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = request.headers.get("Authorization")

    # --- Verify project existence via main API ---
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PROJECTS_SERVICE_URL}/{project_id}/",
            headers={"Authorization": token},
            timeout=5.0,
        )

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Project not found")
    elif resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to verify project")

    # --- Save comment ---
    data = {
        "project_id": project_id,
        "author_id": http_user_id,
        "text": comment.text,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "is_deleted": False,
    }

    result = await comments_collection.insert_one(data)
    new_comment = await comments_collection.find_one({"_id": result.inserted_id})
    if new_comment and isinstance(new_comment.get("_id"), ObjectId):
        new_comment["_id"] = str(new_comment["_id"])
    comment_obj = CommentModel(**new_comment)

    # --- Clear cache for this project ---
    redis = await get_redis()
    await redis.delete(f"comments:project:{project_id}")

    # --- Async background tasks ---
    notify_project_owner.delay(project_id, http_user_id, comment.text)
    publish_event.delay("comment_created", {
        "project_id": project_id,
        "user_id": http_user_id,
        "comment_id": str(result.inserted_id),
    })

    # --- Send notification to Notification Service ---
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            notif_payload = {
                "message": comment.text,
                "is_read": False,
                "notification_type": 1,
                "investor": 1, # temporarily, without investor ID comment can't be created
                "startup": 1. # temporarily, without startup ID comment can't be created
            }
            notif_resp = await client.post(
                NOTIFICATION_SERVICE_URL,
                headers={"Authorization": token, "Content-Type": "application/json"},
                json=notif_payload,
            )

            if notif_resp.status_code == 403:
                logger.info("Notification service returned 403 — likely sender is a startup, ignoring.")
            elif notif_resp.status_code >= 400:
                logger.warning(f"Notification service returned error {notif_resp.status_code}: {notif_resp.text}")
            else:
                logger.info(f"Notification successfully sent to {NOTIFICATION_SERVICE_URL}")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

    # --- Broadcast via WebSocket (real-time updates) ---
    await broadcast_comment(project_id, comment_obj)

    return comment_obj


# -------------------------------------------------------
# List Comments (with caching + author enrichment)
# -------------------------------------------------------
@router.get("/projects/{project_id}/", response_model=list[CommentRead])
async def list_project_comments(
    project_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
):
    skip = (page - 1) * limit
    redis = await get_redis()
    cache_key = f"comments:project:{project_id}:page:{page}"

    cached = await redis.get(cache_key)
    if cached:
        logger.info(f"Cache hit for {cache_key}")
        return [CommentRead(**c) for c in json.loads(cached)]

    logger.info(f"Cache miss for {cache_key}")
    comments_cursor = (
        comments_collection.find({"project_id": project_id, "is_deleted": False})
        .sort("created_at", ASCENDING)
        .skip(skip)
        .limit(limit)
    )
    comments = await comments_cursor.to_list(length=limit)

    # --- Enrich with author info ---
    session = httpx.AsyncClient(timeout=3.0)
    enriched = []
    for c in comments:
        author_info = {"name": "Unknown", "avatar": None}
        try:
            response = await session.get(f"{USER_SERVICE_URL}/{c['author_id']}/") # === for the future updates
            if response.status_code == 200:
                j = response.json()
                author_info = {
                    "name": j.get("name", "Unknown"),
                    "avatar": j.get("avatar", None),
                }
        except Exception as e:
            logger.warning(f"Failed to fetch user info for {c['author_id']}: {e}")

        c["author_name"] = author_info["name"]
        c["author_avatar"] = author_info["avatar"]
        if "_id" in c and isinstance(c["_id"], ObjectId):
            c["_id"] = str(c["_id"])
        enriched.append(CommentModel(**c))

    await session.aclose()

    # --- Cache serialized result ---
    await redis.set(cache_key, json.dumps([e.dict() for e in enriched], default=str), ex=CACHE_TTL)

    logger.info(f"Loaded {len(enriched)} comments for project {project_id}")
    return enriched


# -------------------------------------------------------
# Edit Comment (PATCH)
# -------------------------------------------------------
@router.patch("/{comment_id}/", response_model=CommentRead)
async def edit_comment(
    comment_id: str,
    updated_data: dict,
    request: Request,
    http_user_id: int = Header(None, alias="user-id"),
):
    """
    Edit your own comment text.
    Only author can edit their comment.
    """
    if not http_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    comment = await comments_collection.find_one({"_id": ObjectId(comment_id)})
    if not comment or comment.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Comment not found")

    if int(comment["author_id"]) != http_user_id:
        raise HTTPException(status_code=403, detail="Not allowed to edit this comment")

    new_text = updated_data.get("text")
    if not new_text:
        raise HTTPException(status_code=400, detail="Text is required")

    await comments_collection.update_one(
        {"_id": ObjectId(comment_id)},
        {
            "$set": {
                "text": new_text,
                "updated_at": datetime.now(timezone.utc),
                "edited": True,
            }
        },
    )

    # clear cache
    redis = await get_redis()
    await redis.delete(f"comments:project:{comment['project_id']}")

    # reload
    updated_comment = await comments_collection.find_one({"_id": ObjectId(comment_id)})
    updated_comment["_id"] = str(updated_comment["_id"])

    # broadcast websocket update
    await broadcast_comment(comment["project_id"], CommentModel(**updated_comment))

    return CommentModel(**updated_comment)


# -------------------------------------------------------
# Delete Comment (Soft Delete)
# -------------------------------------------------------
@router.delete("/{comment_id}/", status_code=204)
async def delete_comment(
    comment_id: str,
    http_user_id: int = Header(None, alias="user-id"),
):
    """
    Soft delete a comment. Only author can delete.
    """
    if not http_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    comment = await comments_collection.find_one({"_id": ObjectId(comment_id)})
    if not comment or comment.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Comment not found")

    if int(comment["author_id"]) != http_user_id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this comment")

    await comments_collection.update_one(
        {"_id": ObjectId(comment_id)},
        {"$set": {"is_deleted": True, "updated_at": datetime.now(timezone.utc)}},
    )

    # clear cache
    redis = await get_redis()
    await redis.delete(f"comments:project:{comment['project_id']}")

    # optional: broadcast deletion
    await broadcast_comment(
        comment["project_id"],
        CommentModel(**{**comment, "is_deleted": True})
    )

    return None


# -------------------------------------------------------
# Real-time WebSocket Broadcast
# -------------------------------------------------------
active_connections: dict[int, list[WebSocket]] = {}

async def broadcast_comment(project_id: int, comment: CommentModel):
    """Send real-time updates to connected clients"""
    if project_id in active_connections:
        data_dict = comment.model_dump()
        for k, v in data_dict.items():
            if isinstance(v, datetime):
                data_dict[k] = v.isoformat()

        message = {"event": "comment_created", "data": data_dict}

        for ws in active_connections[project_id]:
            await ws.send_json(message)


@router.websocket("/ws/projects/{project_id}/comments")
async def websocket_endpoint(websocket: WebSocket, project_id: int):
    """WebSocket endpoint for live comment updates"""
    await websocket.accept()
    active_connections.setdefault(project_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        active_connections[project_id].remove(websocket)
        if not active_connections[project_id]:
            del active_connections[project_id]
