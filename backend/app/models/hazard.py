"""User-reported map hazards / incidents (the 'Hazards & Reports' layer).

Short-lived community reports (road closures, accidents, police, weather, etc.)
with a PostGIS POINT for viewport queries. They expire automatically (per-type
window, extended when other users confirm).
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Hazard(Base):
    __tablename__ = "hazards"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # accident | closure | police | weather | hazard | other
    type: Mapped[str] = mapped_column(String(24), default="hazard", index=True)
    severity: Mapped[str] = mapped_column(String(8), default="med")  # low | med | high
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(8), default="active", index=True)  # active | expired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
