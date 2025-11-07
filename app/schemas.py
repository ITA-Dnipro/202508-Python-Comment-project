# app/schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CommentCreate(BaseModel):
    text: str


class CommentRead(BaseModel):
    id: Optional[str]
    project_id: int
    author_id: int
    text: str
    created_at: datetime
    updated_at: datetime
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None

    class Config:
        from_attributes = True
