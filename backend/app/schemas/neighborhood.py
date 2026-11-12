from datetime import datetime
from pydantic import BaseModel


class NeighborhoodCreate(BaseModel):
    name: str
    description: str | None = None
    city: str
    country: str
    latitude: float | None = None
    longitude: float | None = None
    safety_score: int | None = None
    walkability_score: int | None = None
    transit_score: int | None = None
    food_score: int | None = None
    schools_score: int | None = None
    overall_score: int | None = None


class NeighborhoodRead(BaseModel):
    id: int
    name: str
    description: str | None
    city: str
    country: str
    latitude: float | None
    longitude: float | None
    safety_score: int | None
    walkability_score: int | None
    transit_score: int | None
    food_score: int | None
    schools_score: int | None
    overall_score: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NeighborhoodUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    safety_score: int | None = None
    walkability_score: int | None = None
    transit_score: int | None = None
    food_score: int | None = None
    schools_score: int | None = None
    overall_score: int | None = None
