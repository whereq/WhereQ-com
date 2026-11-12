"""Pydantic schemas for the local-content (news/events/stories/topics) API."""

from datetime import datetime

from pydantic import BaseModel


class LocalPin(BaseModel):
    """Lightweight marker payload for viewport (map) queries."""

    id: int
    type: str
    category: str
    lat: float
    lng: float
    title: str
    source_name: str | None = None
    event_time: datetime | None = None
    publish_time: datetime | None = None
    image_url: str | None = None


class LocalContentDetail(BaseModel):
    """Full record for a selected marker."""

    id: int
    type: str
    category: str
    title: str
    summary: str | None = None
    description: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    event_time: datetime | None = None
    event_end_time: datetime | None = None
    publish_time: datetime | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None
    image_url: str | None = None
    confidence_score: float | None = None
    tags: list[str] = []
    created_at: datetime | None = None


class TaxItem(BaseModel):
    id: str
    name: str
    count: int


class SourceItem(BaseModel):
    id: int
    slug: str
    name: str
    count: int


class LocalTaxonomy(BaseModel):
    types: list[TaxItem]
    categories: list[TaxItem]
    sources: list[SourceItem]


class LocalSearchItem(BaseModel):
    id: int
    type: str
    category: str
    title: str
    summary: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    lat: float | None = None
    lng: float | None = None
    city: str | None = None
    event_time: datetime | None = None
    publish_time: datetime | None = None
    image_url: str | None = None


class LocalSearchResponse(BaseModel):
    total: int
    results: list[LocalSearchItem]
