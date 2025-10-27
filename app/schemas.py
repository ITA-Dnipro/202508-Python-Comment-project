from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class CommentBase(BaseModel):
    project_id: int
    author_id: int
    text: str = Field(..., max_length=500)

    @field_validator("text")
    def validate_text(cls, v):
        if len(v.strip()) < 3:
            raise ValueError("Comment must contain at least 3 characters.")
        if len(v) > 500:
            raise ValueError("Comment exceeds 500 character limit.")
        return v

class CommentCreate(CommentBase):
    pass

class CommentRead(CommentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
