"""Local content domain — news, events, community stories, and local topics
that appear as markers on the map.

A crawler (``app.crawler``) discovers items from ``news_source`` definitions,
normalizes them, geocodes a location, classifies a category, and upserts
``local_content`` rows. Coordinates are WGS84 (SRID 4326); ``geom`` is a PostGIS
POINT with a GiST index for viewport (bounding-box) queries at scale.

Retention is expressed via ``expires_at`` + ``status`` (a sweep flips stale
rows to ``expired`` rather than deleting, so history is preserved).
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Vocabularies (kept as plain strings in the DB for flexibility; these document
# the expected values and are reused by the crawler + API for validation).
CONTENT_TYPES = ("news", "event", "story", "topic")
CATEGORIES = (
    "accident", "crime", "fire", "weather", "transportation", "construction",
    "festival", "event", "business", "education", "government", "community",
    "health", "other",
)


class NewsSource(Base):
    """A crawler source definition (RSS feed, HTML page, or API endpoint)."""

    __tablename__ = "news_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="rss")  # rss|html|api
    url: Mapped[str] = mapped_column(String(1024), nullable=False)       # feed / seed URL
    homepage_url: Mapped[str | None] = mapped_column(String(512))

    # Defaults applied to items from this source when not otherwise detected.
    default_type: Mapped[str] = mapped_column(String(16), server_default="news")
    default_category: Mapped[str | None] = mapped_column(String(32))
    default_city: Mapped[str | None] = mapped_column(String(128))
    default_province: Mapped[str | None] = mapped_column(String(16))
    default_country: Mapped[str | None] = mapped_column(String(8), server_default="CA")

    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true", index=True)
    crawl_interval_minutes: Mapped[int] = mapped_column(Integer, server_default="60")
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(16))          # ok|error
    last_error: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict | None] = mapped_column(JSONB)                   # selectors, limits, region bias

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contents: Mapped[list["LocalContent"]] = relationship(back_populates="source")


class LocalContent(Base):
    """A normalized news/event/story/topic record shown on the map."""

    __tablename__ = "local_content"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_local_source_external"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("news_source.id"), index=True)

    type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="news", index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, server_default="other", index=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    source_name: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255))

    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    # PostGIS POINT; GiST index created in the migration (spatial_index=False here
    # to avoid geoalchemy2 auto-creating a duplicate during create_table).
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))

    address: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(128), index=True)
    province: Mapped[str | None] = mapped_column(String(16))
    country: Mapped[str | None] = mapped_column(String(8))

    # none|no location extracted · failed|no provider answered · rejected|the
    # geocode was implausible and was not used · ok|a real location.
    # 'fallback_city' was legacy: those rows were placed at the city centre and
    # were unplaced by migration 014 (their coordinates are gone); migration 016
    # reset the leftover marker to 'none'.
    geocode_status: Mapped[str] = mapped_column(String(16), server_default="none")
    geocode_source: Mapped[str | None] = mapped_column(String(32))                  # provider name|coords|manual
    confidence_score: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active", index=True)
    image_url: Mapped[str | None] = mapped_column(String(1024))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    dedup_key: Mapped[str | None] = mapped_column(String(64), index=True)  # near-dup: norm(title)+date+geo bucket
    raw: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    source: Mapped["NewsSource | None"] = relationship(back_populates="contents")
    tags: Mapped[list["LocalContentTag"]] = relationship(
        back_populates="content", cascade="all, delete-orphan")
    locations: Mapped[list["LocalContentLocation"]] = relationship(
        back_populates="content", cascade="all, delete-orphan")


class LocalContentTag(Base):
    __tablename__ = "local_content_tag"
    __table_args__ = (UniqueConstraint("content_id", "tag", name="uq_local_content_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("local_content.id", ondelete="CASCADE"), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    content: Mapped["LocalContent"] = relationship(back_populates="tags")


class LocalContentLocation(Base):
    """Future expansion: multiple geocoded locations for a single item."""

    __tablename__ = "local_content_location"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("local_content.id", ondelete="CASCADE"), nullable=False, index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
    address: Mapped[str | None] = mapped_column(String(512))
    label: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default="false")

    content: Mapped["LocalContent"] = relationship(back_populates="locations")


class GeocodeProviderUsage(Base):
    """Per-provider request counter within a quota window (day or month).

    Persisted so quota tracking survives across separate crawler processes
    (the crawler runs per cron invocation). ``period`` is 'YYYY-MM-DD' for
    daily-quota providers or 'YYYY-MM' for monthly-quota providers.
    """

    __tablename__ = "geocode_provider_usage"
    __table_args__ = (UniqueConstraint("provider", "period", name="uq_geocode_usage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GeocodeCache(Base):
    """Cache of geocoding lookups to avoid repeat geocoding API calls/billing."""

    __tablename__ = "geocode_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    formatted_address: Mapped[str | None] = mapped_column(String(512))
    confidence: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(16), server_default="google")
    hit_count: Mapped[int] = mapped_column(Integer, server_default="0")
    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
