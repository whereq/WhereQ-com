from datetime import datetime
from pydantic import BaseModel


class SavedPlaceCreate(BaseModel):
    place_id: int
    label: str | None = None


class SavedPlaceRead(BaseModel):
    id: int
    user_id: int
    place_id: int
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
