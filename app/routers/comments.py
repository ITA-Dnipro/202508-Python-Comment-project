import logging
import os
import json
from datetime import datetime, timezone
from bson import ObjectId
import asyncio

import httpx
from fastapi import (
    APIRouter,
    HTTPException,
    Header,
    status,
    Request,
    Query,
    WebSocket,
    WebSocketDisconnect,
    Depends,
)
from pymongo import ASCENDING

from app.database import comments_collection
from app.schemas import CommentCreate, CommentRead
from app.models import CommentModel
from app.redis_client import get_redis
from app.dependencies import get_http_client
from app.tasks import notify_project_owner, publish_event


# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
PROJECTS_SERVICE_URL = os.getenv(
    "PROJECTS_SERVICE_URL",
    "http://web:8000/api/projects/startup-projects"
)
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://web:8000/api/users")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://web:8000/api/notifications/")
CACHE_TTL = 300

router = APIRouter(prefix="/comments", tags=["Comments"])
logger = logging.getLogger(__name__)

# -------------------------------------------------------
# WebSocket connections
# -------------------------------------------------------
active_connections: dict[int, list[WebSocket]] = {}


async def broadcast_comment(project_id: int, comment: CommentModel):
    """Send real-time updates to connected clients"""
    if project_id not in active_connections:
        return

    data = comment.model_dump()
    for k, v in data.items():
        if isinstance(v, datetime):
            data[k] = v.isoformat()

    message = {"event": "comment_created", "data": data}

    for ws in active_connections.get(project_id, []):
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.warning(f"WebSocket send failed: {e}")


# -------------------------------------------------------
# CREATE COMMENT
# -------------------------------------------------------
@router.post("/projects/{project_id}/", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    project_id: int,
    comment: CommentCreate,
    request: Request,
    http_user_id: int = Header(None, alias="user-id"),
    http_role: str = Header(None, alias="role"),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    """
        Add a comment to a project.
        Headers: user-id, role
        Body: {"text": "..."}
    """

    if not http_user_id or not http_role:
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = request.headers.get("Authorization")

    # Verify project
    project_resp = await client.get(
        f"{PROJECTS_SERVICE_URL}/{project_id}/",
        headers={"Authorization": token},
    )

    if project_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Project not found")
    if project_resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to verify project")

    # Save comment
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

    new_comment["_id"] = str(new_comment["_id"])
    comment_obj = CommentModel(**new_comment)

    # Clear cache
    redis = await get_redis()
    await redis.delete(f"comments:project:{project_id}")

    # Background tasks
    notify_project_owner.delay(project_id, http_user_id, comment.text)
    publish_event.delay("comment_created", {
        "project_id": project_id,
        "user_id": http_user_id,
        "comment_id": str(result.inserted_id),
    })

    # Send notification to Notification Service
    try:
        notif_payload = {
            "message": comment.text,
            "is_read": False,
            "notification_type": 1,
            "investor": 1, # temporarily, without investor ID comment can't be created
            "startup": 1, # temporarily, without startup ID comment can't be created
        }
        notif_resp = await client.post(
            NOTIFICATION_SERVICE_URL,
            headers={"Authorization": token},
            json=notif_payload,
        )

        if notif_resp.status_code == 403:
            logger.info("Notification service returned 403 (ignored).")
        elif notif_resp.status_code >= 400:
            logger.warning(f"Notification service error {notif_resp.status_code}")
    except Exception as e:
        logger.error(f"Notification send failed: {e}")

    await broadcast_comment(project_id, comment_obj)

    return comment_obj


# -------------------------------------------------------
# LIST COMMENTS
# -------------------------------------------------------
@router.get("/projects/{project_id}/", response_model=list[CommentRead])
async def list_project_comments(
    project_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    skip = (page - 1) * limit
    redis = await get_redis()
    cache_key = f"comments:project:{project_id}:page:{page}"

    cached = await redis.get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return [CommentRead(**c) for c in json.loads(cached)]

    cursor = (
        comments_collection.find({"project_id": project_id, "is_deleted": False})
        .sort("created_at", ASCENDING)
        .skip(skip)
        .limit(limit)
    )
    comments = await cursor.to_list(length=limit)

    # Parallel author enrichment
    tasks = [
        client.get(f"{USER_SERVICE_URL}/{c['author_id']}/", timeout=3.0)
        for c in comments
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    enriched = []
    for c, resp in zip(comments, responses):
        if isinstance(resp, Exception) or resp.status_code != 200:
            c["author_name"] = "Unknown"
            c["author_avatar"] = None
        else:
            j = resp.json()
            c["author_name"] = j.get("name")
            c["author_avatar"] = j.get("avatar")

        c["_id"] = str(c["_id"])
        enriched.append(CommentModel(**c))

    await redis.set(
        cache_key,
        json.dumps([e.model_dump() for e in enriched]),
        ex=CACHE_TTL,
    )

    return enriched


# -------------------------------------------------------
# EDIT COMMENT
# -------------------------------------------------------
@router.patch("/{comment_id}/", response_model=CommentRead)
async def edit_comment(
    comment_id: str,
    updated_data: dict,
    http_user_id: int = Header(None, alias="user-id"),
):
    """
        Edit your own comment text.
        Only author can edit their comment.
    """
    if not http_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    comment = await comments_collection.find_one({"_id": ObjectId(comment_id)})
    if not comment or comment["is_deleted"]:
        raise HTTPException(status_code=404, detail="Comment not found")

    if int(comment["author_id"]) != http_user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    new_text = updated_data.get("text")
    if not new_text:
        raise HTTPException(status_code=400, detail="Text is required")

    await comments_collection.update_one(
        {"_id": ObjectId(comment_id)},
        {"$set": {"text": new_text, "updated_at": datetime.now(timezone.utc), "edited": True}},
    )

    redis = await get_redis()
    await redis.delete(f"comments:project:{comment['project_id']}")

    new_comment = await comments_collection.find_one({"_id": ObjectId(comment_id)})
    new_comment["_id"] = str(new_comment["_id"])

    comment_obj = CommentModel(**new_comment)
    await broadcast_comment(comment["project_id"], comment_obj)

    return comment_obj


# -------------------------------------------------------
# DELETE COMMENT
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
    if not comment or comment["is_deleted"]:
        raise HTTPException(status_code=404, detail="Comment not found")

    if int(comment["author_id"]) != http_user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    await comments_collection.update_one(
        {"_id": ObjectId(comment_id)},
        {"$set": {"is_deleted": True, "updated_at": datetime.now(timezone.utc)}},
    )

    redis = await get_redis()
    await redis.delete(f"comments:project:{comment['project_id']}")

    safe_comment = dict(comment)
    safe_comment["_id"] = str(safe_comment["_id"])
    safe_comment["is_deleted"] = True

    await broadcast_comment(
        comment["project_id"],
        CommentModel(**safe_comment),
    )

    return None


# -------------------------------------------------------
# WEBSOCKET
# -------------------------------------------------------
@router.websocket("/ws/projects/{project_id}/comments")
async def websocket_endpoint(websocket: WebSocket, project_id: int):
    """WebSocket endpoint for live comment updates"""
    await websocket.accept()
    active_connections.setdefault(project_id, []).append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        try:
            conns = active_connections.get(project_id)
            if conns and websocket in conns:
                conns.remove(websocket)
            if conns and not conns:
                del active_connections[project_id]
        except Exception as e:
            logger.warning(f"WebSocket disconnect error: {e}")
