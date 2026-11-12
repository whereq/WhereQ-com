"""Request schemas for the Maps service POST endpoints (/route, /matrix)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    origin: LatLng
    destination: LatLng
    mode: str = "driving"                 # driving | walking | cycling
    departure_time: str | None = None     # "now" or a unix timestamp → traffic-aware
    alternatives: bool = False


class MatrixRequest(BaseModel):
    origins: list[LatLng] = Field(min_length=1)
    destinations: list[LatLng] = Field(min_length=1)
    mode: str = "driving"
