"""The dual-read ledger — one row per comparison.

The migration off whereq.com's own crawler is decided by **reading** the
differences between the two answers, not by assuming there are none. So the
comparisons are recorded, in a table, with the counts and the identities
that differ — a comparison that is not written down is a comparison nobody
can read later.

One row per dual-read, on the surface it was taken for. The rows are the
evidence the cut decision rests on.

This is deliberately NOT a cache and NOT a queue: the local mirror is still
the source of truth for the response while the mode is ``dual``, and these
rows are a record of what was compared.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CloudParityCheck(Base):
    """One comparison between the local mirror and whereq.cloud."""

    __tablename__ = "cloud_parity_checks"
    __table_args__ = (
        Index("ix_cloud_parity_surface_checked", "surface", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: Which surface was compared — "geo_places", "fuel_stations".
    surface: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    #: When the comparison was taken.
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), index=True)

    #: "match" — the two answers agree. "differ" — they do not.
    #: "error" — the cloud side could not be read at all.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="match")

    #: How many rows each side returned.
    local_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cloud_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The identities only one side had. Capped — a total disagreement would
    #: otherwise write a whole feed's worth of ids into one row.
    only_local: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    only_cloud: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    #: The identities both sides had, but with different values. The shape is
    #: ``{"uid": {"field": {"local": ..., "cloud": ...}}}``.
    differing: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: The request that produced the comparison — so a difference can be
    #: reproduced.
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: Why the comparison failed, when it did.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
