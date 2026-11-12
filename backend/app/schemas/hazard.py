from datetime import datetime

from pydantic import BaseModel, Field


class HazardCreate(BaseModel):
    type: str = "hazard"
    severity: str = "med"
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class HazardPin(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    lat: float
    lng: float
    confirmations: int
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class HazardRead(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    description: str | None
    latitude: float
    longitude: float
    confirmations: int
    status: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}
