from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field

class CommentModel(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    project_id: int
    author_id: int
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = False

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}
