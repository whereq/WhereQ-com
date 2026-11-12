from datetime import datetime
from pydantic import BaseModel


class StoryCreate(BaseModel):
    place_id: int
    title: str
    content: str
    category: str = "memorial"


class StoryRead(BaseModel):
    id: int
    place_id: int
    author_id: int
    title: str
    content: str
    category: str
    is_published: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StoryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    is_published: bool | None = None
