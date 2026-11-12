from datetime import datetime
from typing import Any
from pydantic import BaseModel


class PlaceCreate(BaseModel):
    name: str
    description: str | None = None
    latitude: float
    longitude: float
    address: str | None = None
    city: str | None = None
    country: str | None = None
    category: str = "general"
    kind: str = "poi"
    sub: str | None = None
    metadata_json: dict[str, Any] | None = None


class PlaceRead(BaseModel):
    id: int
    name: str
    description: str | None
    latitude: float
    longitude: float
    address: str | None
    city: str | None
    country: str | None
    category: str
    kind: str
    sub: str | None
    metadata_json: dict[str, Any] | None
    view_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PlacePin(BaseModel):
    """Lightweight pin for the viewport map layer."""
    id: int
    name: str
    lat: float
    lng: float
    kind: str
    category: str
    sub: str | None = None

    model_config = {"from_attributes": True}


class PlaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    address: str | None = None
    category: str | None = None
    kind: str | None = None
    sub: str | None = None
    metadata_json: dict[str, Any] | None = None
