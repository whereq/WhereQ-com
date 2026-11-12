"""WhereQ Maps service domain.

A keyed data API (``/api/maps/v1``) consumed server-to-server by other
applications. Auth is an opaque per-consumer key
(``wq_<env>_<random>``); only the sha256 hash + a short prefix are stored.

- ``MapsApiConsumer`` — one keyed app, with scopes + per-key limits.
- ``MapsApiUsage``    — per consumer/day/endpoint/provider counters (quota +
  cost attribution), upserted on each request.
- ``RouteCache``      — short-term cache for ``/route`` (+/matrix), TTL-checked
  on read per Google Maps ToS (routing results are not permanently cacheable).

Geocode/reverse results reuse the existing ``geocode_cache`` table.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Every scope a key may carry — mirrors the /api/maps/v1 endpoints.
MAPS_SCOPES = frozenset(
    {"autocomplete", "geocode", "reverse", "route", "matrix", "static"}
)


class MapsApiConsumer(Base):
    """A keyed consumer application of the Maps service."""

    __tablename__ = "maps_api_consumer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 hex of the plaintext key; the plaintext is never stored.
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    # First ~12 chars of the plaintext (e.g. "wq_live_9f3c") — for logs/UI only.
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="120")
    monthly_quota: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50000")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    usage: Mapped[list["MapsApiUsage"]] = relationship(
        back_populates="consumer", cascade="all, delete-orphan")


class MapsApiUsage(Base):
    """Per-consumer/day/endpoint/provider request counter."""

    __tablename__ = "maps_api_usage"
    __table_args__ = (
        UniqueConstraint("consumer_id", "day", "endpoint", "provider", name="uq_maps_usage"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    consumer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maps_api_consumer.id", ondelete="CASCADE"),
        nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    consumer: Mapped["MapsApiConsumer"] = relationship(back_populates="usage")


class RouteCache(Base):
    """Short-term cache for /route (+/matrix). TTL enforced on read (ToS)."""

    __tablename__ = "route_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_in_traffic_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    polyline: Mapped[str | None] = mapped_column(Text, nullable=True)
    bounds: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, server_default="google")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
