from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class CommentBase(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class CommentCreate(CommentBase):
    pass


class CommentRead(CommentBase):
    id: Optional[str]
    project_id: int
    author_id: int

    created_at: datetime
    updated_at: datetime

    # Optional UX fields
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None

    edited: Optional[bool] = False
    is_deleted: bool = False

    class Config:
        from_attributes = True
