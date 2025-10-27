from fastapi import APIRouter, HTTPException, status
from datetime import datetime
from app.database import comments_collection
from app.schemas.comment import CommentCreate, CommentRead
from app.models.comment import CommentModel

router = APIRouter(prefix="/comments", tags=["Comments"])

@router.post("/", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(comment: CommentCreate):
    data = comment.dict()
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()
    data["is_deleted"] = False

    result = await comments_collection.insert_one(data)
    new_comment = await comments_collection.find_one({"_id": result.inserted_id})
    return CommentModel(**new_comment)

@router.get("/", response_model=list[CommentRead])
async def list_comments():
    comments_cursor = comments_collection.find({"is_deleted": False})
    comments = await comments_cursor.to_list(length=100)
    return [CommentModel(**c) for c in comments]
