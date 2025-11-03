from fastapi import APIRouter, HTTPException, Header, status, Request
from datetime import datetime
from app.database import comments_collection
from app.schemas import CommentCreate, CommentRead
from app.models import CommentModel
import httpx
import os
from app.tasks import notify_project_owner, publish_event

PROJECTS_SERVICE_URL = os.getenv("PROJECTS_SERVICE_URL", "http://web:8000/api/projects/startup-projects")

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.post("/projects/{project_id}/", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    project_id: int,
    comment: CommentCreate,
    request: Request,
    http_user_id: int = Header(None, alias="HTTP_USER_ID"),
    http_role: str = Header(None, alias="HTTP_ROLE"),
):
    """
    Add comment to a project.
    Headers: HTTP_USER_ID, HTTP_ROLE
    Body: {"text": "..."}
    """

    if not http_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # --- Перевірка існування проекту через основний сервіс ---
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PROJECTS_SERVICE_URL}/{project_id}/",
            headers={"Authorization": request.headers.get("Authorization")},
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Project not found")
    elif response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to verify project")

    # --- Зберігаємо коментар ---
    data = {
        "project_id": project_id,
        "author_id": http_user_id,
        "text": comment.text,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_deleted": False,
    }

    result = await comments_collection.insert_one(data)
    new_comment = await comments_collection.find_one({"_id": result.inserted_id})
    comment_obj = CommentModel(**new_comment)

    # --- Асинхронні події ---
    notify_project_owner.delay(project_id, http_user_id, comment.text)
    publish_event.delay("comment_created", {
        "project_id": project_id,
        "user_id": http_user_id,
        "comment_id": str(result.inserted_id),
    })

    return comment_obj
