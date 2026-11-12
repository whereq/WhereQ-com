from datetime import datetime
from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), default="general")
    kind: Mapped[str] = mapped_column(String(32), default="poi", index=True)
    sub: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    # Provenance for crawled POIs (e.g. source="osm", external_id="node/123"),
    # used for idempotent upserts. Manual rows leave these null/"manual".
    source: Mapped[str] = mapped_column(String(16), default="manual", index=True)
    external_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # Creator of a user-authored place (null for pipeline-managed rows and for
    # places that existed before ownership was tracked). Writes are restricted
    # to this user; staff may override. ON DELETE SET NULL so removing a user
    # never deletes the POI dataset.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # PostGIS POINT (WGS84) with a GiST index (created in the migration) for
    # viewport bounding-box queries at scale.
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stories: Mapped[list["Story"]] = relationship(back_populates="place", lazy="select")
    owner: Mapped["User"] = relationship(back_populates="places", lazy="select")