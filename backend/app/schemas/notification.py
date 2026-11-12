from datetime import datetime
from pydantic import BaseModel


class NotificationCreate(BaseModel):
    title: str
    body: str | None = None
    kind: str = "info"


class NotificationRead(BaseModel):
    id: int
    user_id: int
    title: str
    body: str | None
    kind: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
