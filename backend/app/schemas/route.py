from datetime import datetime
from pydantic import BaseModel
from typing import Any


class Waypoint(BaseModel):
    lat: float
    lng: float
    timestamp: str | None = None
    note: str | None = None


class RouteCreate(BaseModel):
    name: str
    description: str | None = None
    waypoints: list[Waypoint] = []
    total_distance_km: float | None = None
    duration_minutes: int | None = None
    is_public: bool = False


class RouteRead(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None
    waypoints: list[Any]
    total_distance_km: float | None
    duration_minutes: int | None
    is_public: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RouteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None
