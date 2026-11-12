"""Fuel domain — whereq.cloud fuel data.

Two tables sit alongside the ``places`` rows that carry station-level prices:

- ``FuelSyncState``  — one row per coverage target (a country, a state, a
  municipality or a bbox), recording when it was last crawled, how many
  stations came back and whether the last attempt failed. The crawler uses it
  to rotate targets round-robin instead of re-pulling everything on every tick.
- ``FuelPriceSeries`` — the *aggregated* price series behind the charts
  (EIA weekly for the US, StatCan monthly for Canada, CRE for Mexico): state,
  national and metro averages per product. Station prices and these averages
  are different things — stations are what the map shows, series are the
  regional context around them.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FuelSyncState(Base):
    """Crawl bookkeeping for one fuel coverage target."""

    __tablename__ = "fuel_sync_state"

    # Stable key derived from the target spec (e.g. "ca:ontario" or
    # "bbox:-79.7,43.4,-79.3,43.9") — the upsert identity.
    target_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    country: Mapped[str | None] = mapped_column(String(2))
    state: Mapped[str | None] = mapped_column(String(120))
    municipality: Mapped[str | None] = mapped_column(String(160))
    bbox: Mapped[str | None] = mapped_column(String(128))

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    station_count: Mapped[int] = mapped_column(Integer, default=0)
    # Set when the last attempt failed; cleared on a successful crawl.
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FuelPriceSeries(Base):
    """One aggregated fuel price series (state / national / metro average)."""

    __tablename__ = "fuel_price_series"

    # The whereq.cloud series id — stable across refreshes.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(24), index=True)
    source: Mapped[str | None] = mapped_column(String(32), index=True)
    # Region slug ("ca", "us", "mx").
    region: Mapped[str | None] = mapped_column(String(24), index=True)
    # Place label ("Toronto, Ontario", "CALIFORNIA", "PADD 1").
    geo: Mapped[str | None] = mapped_column(String(160), index=True)
    item: Mapped[str] = mapped_column(Text)
    # Unit as reported by the source ("Cents per litre", "$/GAL", "MXN/L").
    unit: Mapped[str | None] = mapped_column(String(64))
    frequency: Mapped[str | None] = mapped_column(String(16))
    latest_period: Mapped[str | None] = mapped_column(String(32))
    latest_value: Mapped[float | None] = mapped_column(Float)
    prev_value: Mapped[float | None] = mapped_column(Float)
    points: Mapped[int | None] = mapped_column(Integer)
    # Recent history for the sparkline (list of floats).
    spark: Mapped[list | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
