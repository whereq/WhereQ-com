"""Per-consumer usage accounting for the Maps service.

Upserts a counter per (consumer, day, endpoint, provider) on each request —
feeding both the monthly-quota check and cost attribution/observability.

Usage is recorded for **every request that reaches an upstream provider**, not
only the successful ones: the monthly quota is a spend control, and a request
that reached Google costs money whether or not it returned a usable result.
Recording only on the success path would let a consumer burn upstream quota
with failing requests without ever being charged against its quota.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maps import MapsApiUsage

logger = logging.getLogger(__name__)


def _month_start(today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    return today.replace(day=1)


async def record_usage(db: AsyncSession, consumer_id: uuid.UUID, endpoint: str,
                       provider: str, *, count: int = 1) -> None:
    """Increment the (consumer, today, endpoint, provider) counter."""
    stmt = pg_insert(MapsApiUsage).values(
        consumer_id=consumer_id,
        day=datetime.now(timezone.utc).date(),
        endpoint=endpoint,
        provider=provider,
        count=count,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_maps_usage",
        set_={"count": MapsApiUsage.count + count},
    )
    await db.execute(stmt)
    await db.commit()


class _UsageState:
    """Mutable handle the handler uses to describe what it did."""

    __slots__ = ("provider", "failed")

    def __init__(self) -> None:
        self.provider: str | None = None
        self.failed: bool = False


@asynccontextmanager
async def usage_tracker(db: AsyncSession, consumer_id: uuid.UUID, endpoint: str):
    """Account for one Maps API request — counted even when it fails.

    The handler may set ``state.provider`` to name the provider that actually
    answered (``"cache"``, ``"miss"``, ``"google"``, …). If it does not, a
    failed request is recorded as ``"error"`` and a successful one as
    ``"unknown"``.

    Accounting never turns a working request into a failure: a write error
    here is logged and swallowed.
    """
    state = _UsageState()
    try:
        yield state
    except BaseException:
        state.failed = True
        raise
    finally:
        provider = state.provider or ("error" if state.failed else "unknown")
        try:
            if state.failed:
                # Clear any transaction the handler left in a failed state, so
                # the counter insert can run.
                await db.rollback()
            await record_usage(db, consumer_id, endpoint, provider)
        except Exception:
            logger.warning(
                "Could not record Maps usage for %s (provider=%s)", endpoint, provider,
                exc_info=True,
            )


async def monthly_request_count(db: AsyncSession, consumer_id: uuid.UUID) -> int:
    """Total requests this calendar month (all endpoints/providers)."""
    total = (await db.execute(
        select(func.coalesce(func.sum(MapsApiUsage.count), 0))
        .where(MapsApiUsage.consumer_id == consumer_id,
               MapsApiUsage.day >= _month_start())
    )).scalar_one()
    return int(total or 0)
