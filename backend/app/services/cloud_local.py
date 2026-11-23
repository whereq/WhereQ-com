"""The local layer — **read** from whereq.cloud instead of collected here.

whereq.cloud owns the collection now. This module is the whereq.com side of
that: it pulls the rows the platform publishes and upserts them into the
local tables, so the map and the search keep answering from the local mirror
while the *collection* happens once, in one place.

It is the same shape as the other two feeds that already read from
whereq.cloud — the fuel stations and the geography — so the three behave
alike:

* **The key never leaves the backend.** ``WHEREQ_CLOUD_API_KEY`` is read from
  the server environment and sent by the SDK; the browser only ever talks to
  our own ``/api`` endpoints.
* **One shared limiter.** The upstream allows 30 requests per minute for the
  whole account, so the throttle is shared with the fuel and geography feeds
  rather than each having its own.
* **Paging.** The upstream caps a page at 200 rows, so both feeds are read
  page by page.

THE TWO FEEDS
--------------
``/v1/local/content``
    Keyset-paged, newest first, and it grows all day. The sync therefore
    reads only the **newest pages** on each pass and upserts them: the rows
    are already here, so re-reading them is cheap and self-correcting, and a
    tick that failed loses nothing because the next one reads the same head
    of the feed.

``/v1/local/places``
    Offset-paged, and the upstream's rows are upserted in place every time
    its weekly OSM sweep runs — so there is no "changed since" marker to ask
    for, and the only honest read is the **whole catalogue**. That is a few
    hundred pages, so it runs on a slow cycle, the same weekly cadence the
    upstream's own sweep runs on. The upsert is idempotent: a second full
    pass writes the same rows.

WHAT IS NOT COPIED
------------------
The local tables keep their own columns where the upstream has nothing to
say. ``local_content.description`` is whereq.com's own article text (its
crawler fetched the page); the upstream does not publish it, so the sync
leaves it alone rather than nulling a column it cannot fill.

The join keys agree on both sides, and that is what makes the sync an upsert
rather than a duplicate: the upstream's ``external_id`` is the feed's own
guid (``https://toronto.citynews.ca/?p=4967131``), which is byte for byte
the value whereq.com's crawler already stored, and the source slugs match
one for one.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.local_content import LocalContent, NewsSource
from app.models.place import Place
from app.services.whereq_cloud_client import (
    call_with_retry,
    client as cloud_client,
    shared_throttle,
)

logger = logging.getLogger(__name__)

#: The upstream's own page ceiling (``data_api/routers/local.py``).
PAGE_SIZE = 200

#: The POI categories the upstream publishes. The upstream's rows carry the
#: category, so the sync does not have to know them — but it does have to
#: *ask* for them, because the upstream answers one category at a time when
#: a category is named, and the catalogue is only reachable as a whole.
POI_CATEGORIES: tuple[str, ...] = (
    "pharmacy", "clinic", "library", "plaza", "food", "coffee",
    "fuel", "parking", "stays", "transit", "park", "bike",
)


# ── reading the upstream ────────────────────────────────────────────────────
def _fetch_content_page(cursor: str | None, limit: int) -> dict:
    """One page of ``/v1/local/content``, newest first. Synchronous."""
    client = cloud_client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(
            client.local_content, limit=limit, cursor=cursor)
    finally:
        client.close()
    return payload or {}


def _fetch_places_page(offset: int, limit: int, category: str | None) -> dict:
    """One page of ``/v1/local/places``. Synchronous."""
    client = cloud_client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(
            client.local_places, limit=limit, offset=offset, category=category)
    finally:
        client.close()
    return payload or {}


def _parse_dt(value: Any) -> datetime | None:
    """An upstream timestamp into an aware datetime, or ``None``."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ── the content sync ───────────────────────────────────────────────────────
async def _source_ids(db: AsyncSession) -> dict[str, int]:
    """The local ``news_source`` ids, by slug.

    The upstream names its source; the local table keys on an integer. The
    slugs are the same on both sides — whereq.cloud's seeds were copied from
    whereq.com's — so the slug is the join.
    """
    rows = await db.execute(select(NewsSource.id, NewsSource.slug))
    return {slug: sid for sid, slug in rows.all()}


def _content_row(row: dict, source_ids: dict[str, int]) -> dict | None:
    """One upstream content row into a local row, or ``None`` if it cannot go.

    A row without an external id cannot be upserted — it would land twice —
    and a row whose source slug is unknown locally has no ``source_id`` to
    point at. Both are reported rather than guessed.
    """
    external_id = row.get("external_id")
    if not external_id:
        return None
    source_id = source_ids.get(row.get("source_slug") or "")
    if source_id is None:
        return None

    latitude = row.get("latitude")
    longitude = row.get("longitude")
    geom = None
    if latitude is not None and longitude is not None:
        # The point is built in the same statement as the row, the way the
        # POI ingest does it: a PostGIS POINT, not two loose floats.
        geom = f"SRID=4326;POINT({float(longitude)} {float(latitude)})"

    return {
        "source_id": source_id,
        "type": row.get("type") or "news",
        "category": row.get("category") or "other",
        "title": (row.get("title") or "")[:512],
        "summary": row.get("summary"),
        "source_name": row.get("source_name"),
        "source_url": row.get("source_url"),
        "external_id": external_id,
        "event_time": _parse_dt(row.get("event_time")),
        "event_end_time": _parse_dt(row.get("event_end_time")),
        "publish_time": _parse_dt(row.get("publish_time")),
        "latitude": latitude,
        "longitude": longitude,
        "geom": geom,
        "address": row.get("address"),
        "city": row.get("city"),
        "province": row.get("province"),
        "country": row.get("country"),
        "geocode_status": row.get("geocode_status") or "none",
        "geocode_source": row.get("geocode_source"),
        "confidence_score": row.get("confidence_score"),
        "status": row.get("status") or "active",
        "image_url": row.get("image_url"),
        "expires_at": _parse_dt(row.get("expires_at")),
        "content_sha256": row.get("content_sha256"),
        "dedup_key": row.get("dedup_key"),
    }


async def sync_local_content(db: AsyncSession, *, pages: int | None = None,
                              commit: bool = True) -> dict:
    """Upsert the newest upstream content rows into ``local_content``.

    Only the **newest** pages are read: the rows behind them are already
    here, and the feed grows at the head. Every pass re-reads the same head,
    so a pass that failed halfway costs nothing — the next one picks up
    where it left off.

    Returns ``{"written": n, "skipped": n, "pages": n}``.
    """
    limit = settings.LOCAL_CONTENT_SYNC_PAGE_SIZE
    max_pages = pages if pages is not None else settings.LOCAL_CONTENT_SYNC_PAGES
    source_ids = await _source_ids(db)

    written = 0
    skipped = 0
    cursor: str | None = None
    read_pages = 0

    for _ in range(max_pages):
        payload = await asyncio.to_thread(_fetch_content_page, cursor, limit)
        rows = payload.get("data") or []
        if not rows:
            break
        read_pages += 1

        prepared: list[dict] = []
        for row in rows:
            local = _content_row(row, source_ids)
            if local is None:
                skipped += 1
                continue
            prepared.append(local)
        if prepared:
            written += await _upsert_content(db, prepared)

        cursor = (payload.get("pagination") or {}).get("next_cursor")
        if not cursor:
            break

    if commit:
        await db.commit()
    logger.info("local content sync: %d row(s) written across %d page(s), %d skipped",
                written, read_pages, skipped)
    return {"written": written, "skipped": skipped, "pages": read_pages}


async def _upsert_content(db: AsyncSession, rows: list[dict]) -> int:
    """Upsert content rows on ``(source_id, external_id)``.

    ``description`` is deliberately **not** in the update set: it is
    whereq.com's own article text, and the upstream does not publish it.
    Nulling it would destroy a column the sync cannot refill.
    """
    stmt = pg_insert(LocalContent).values(rows)
    update_columns = {
        "type": stmt.excluded.type,
        "category": stmt.excluded.category,
        "summary": stmt.excluded.summary,
        "source_name": stmt.excluded.source_name,
        "source_url": stmt.excluded.source_url,
        "event_time": stmt.excluded.event_time,
        "event_end_time": stmt.excluded.event_end_time,
        "publish_time": stmt.excluded.publish_time,
        "latitude": stmt.excluded.latitude,
        "longitude": stmt.excluded.longitude,
        "geom": stmt.excluded.geom,
        "address": stmt.excluded.address,
        "city": stmt.excluded.city,
        "province": stmt.excluded.province,
        "country": stmt.excluded.country,
        "geocode_status": stmt.excluded.geocode_status,
        "geocode_source": stmt.excluded.geocode_source,
        "confidence_score": stmt.excluded.confidence_score,
        "status": stmt.excluded.status,
        "image_url": stmt.excluded.image_url,
        "expires_at": stmt.excluded.expires_at,
        "content_sha256": stmt.excluded.content_sha256,
        "dedup_key": stmt.excluded.dedup_key,
        # The mirror was refreshed from the upstream at this moment. The
        # legacy collectors restamped it the same way, and the places
        # sync's due-ness reads it as its watermark.
        "updated_at": func.now(),
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[LocalContent.source_id, LocalContent.external_id],
        set_=update_columns,
    )
    await db.execute(stmt)
    return len(rows)


# ── the places sync ────────────────────────────────────────────────────────
def _place_row(row: dict) -> dict | None:
    """One upstream place row into a local place row, or ``None``."""
    external_id = row.get("external_id")
    latitude = row.get("latitude")
    longitude = row.get("longitude")
    if not external_id or latitude is None or longitude is None:
        return None
    return {
        "name": (row.get("name") or "")[:255],
        "description": row.get("description"),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "address": row.get("address"),
        "city": row.get("city"),
        "country": row.get("country"),
        "category": row.get("category") or "general",
        "kind": row.get("kind") or "poi",
        "sub": row.get("sub"),
        "metadata_json": row.get("metadata") or None,
        "source": row.get("source") or "osm",
        "external_id": external_id,
        "geom": f"SRID=4326;POINT({float(longitude)} {float(latitude)})",
    }


async def sync_local_places(db: AsyncSession, *,
                             categories: Iterable[str] | None = None,
                             max_rows: int | None = None,
                             commit: bool = True) -> dict:
    """Upsert the upstream's whole POI catalogue into ``places``.

    The upstream re-upserts every row its weekly sweep touches, so there is
    no "changed since" marker: the only honest read is the whole catalogue,
    page by page. The upsert is idempotent, so a second pass writes the same
    rows.

    Returns ``{"written": n, "skipped": n, "pages": n}``.
    """
    wanted = list(categories) if categories is not None else list(POI_CATEGORIES)
    limit = PAGE_SIZE
    cap = max_rows if max_rows is not None else settings.LOCAL_PLACES_SYNC_MAX_ROWS

    written = 0
    skipped = 0
    pages = 0

    for category in wanted:
        offset = 0
        while True:
            payload = await asyncio.to_thread(
                _fetch_places_page, offset, limit, category)
            rows = payload.get("data") or []
            if not rows:
                break
            pages += 1

            prepared: list[dict] = []
            for row in rows:
                local = _place_row(row)
                if local is None:
                    skipped += 1
                    continue
                prepared.append(local)
            if prepared:
                written += await _upsert_places(db, prepared)

            offset += len(rows)
            if offset >= cap:
                logger.warning("local places sync: stopping at the %d row cap "
                               "(category %s)", cap, category)
                break

    if commit:
        await db.commit()
    logger.info("local places sync: %d row(s) written across %d page(s), %d skipped",
                written, pages, skipped)
    return {"written": written, "skipped": skipped, "pages": pages}


async def _upsert_places(db: AsyncSession, rows: list[dict]) -> int:
    """Upsert place rows on ``(source, external_id)``.

    The same key the OSM ingest used, so the upstream's rows land **on** the
    rows that are already there instead of beside them.
    """
    stmt = pg_insert(Place).values(rows)
    update_columns = {
        "name": stmt.excluded.name,
        "description": stmt.excluded.description,
        "latitude": stmt.excluded.latitude,
        "longitude": stmt.excluded.longitude,
        "geom": stmt.excluded.geom,
        "address": stmt.excluded.address,
        "city": stmt.excluded.city,
        "country": stmt.excluded.country,
        "category": stmt.excluded.category,
        "kind": stmt.excluded.kind,
        "sub": stmt.excluded.sub,
        "metadata_json": stmt.excluded.metadata_json,
        # The watermark the places sync's due-ness reads: a sync
        # restamps every row it refreshes, so the newest one says when
        # the catalogue was last read.
        "updated_at": func.now(),
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[Place.source, Place.external_id],
        index_where=Place.external_id.isnot(None),
        set_=update_columns,
    )
    await db.execute(stmt)
    return len(rows)


__all__ = ["sync_local_content", "sync_local_places", "POI_CATEGORIES"]
