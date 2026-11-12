"""Aggregated fuel price series from whereq.cloud.

``/v1/prices?domain=fuel`` returns the *series* behind the charts: weekly
averages per US state and PADD region (EIA), monthly metro and provincial
averages for Canada (StatCan) and regional averages for Mexico (CRE).

These are a different thing from the station prices in
``app.crawler.upstream.fuel_stations``: a station is a single pump at a single
address with a price right now, a series is the regional average over time.
The map shows stations; this gives the regional context around them.

Refreshed on a slow cadence — the underlying series are weekly or monthly, so
a daily crawl is plenty.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import whereq_cloud

from app.core.config import settings
from app.models.fuel import FuelPriceSeries
from app.models.place import Place

logger = logging.getLogger(__name__)

#: The API caps a page at this many series.
_PAGE_SIZE = 100


def configured_regions() -> list[str]:
    """Region slugs to crawl (``ca``, ``us``, ``mx``)."""
    seen: list[str] = []
    for slug in settings.FUEL_PRICES_REGIONS.split(","):
        slug = slug.strip().lower()
        if slug and slug not in seen:
            seen.append(slug)
    return seen

# ── unit handling ───────────────────────────────────────────────────────────
#: Litres in a US gallon — EIA quotes $/GAL, everything else per litre.
LITRES_PER_GALLON = 3.785411784

#: Source unit -> (currency, multiplier to local currency per litre).
_UNIT_SCALES: dict[str, tuple[str, float]] = {
    "cents per litre": ("CAD", 0.01),
    "mxn/l": ("MXN", 1.0),
    "$/gal": ("USD", 1.0 / LITRES_PER_GALLON),
}


def normalize_per_litre(unit: str | None, value: float | None) -> tuple[float | None, str | None]:
    """Convert a series value to *local currency per litre*.

    Station prices come from whereq.cloud in local currency per litre
    (CAD/L, USD/L, MXN/L), but the aggregated series use their own units —
    StatCan quotes "Cents per litre" and EIA quotes "$/GAL". Normalising here
    lets the UI put a regional average next to a station price without
    silently mixing units. Returns ``(value_per_litre, currency)``.
    """
    if value is None:
        return None, None
    currency, scale = _UNIT_SCALES.get((unit or "").strip().lower(), (None, 1.0))
    if currency is None:
        # Unknown unit: pass the value through untouched rather than guess.
        return value, None
    return round(value * scale, 4), currency


def product_key(item: str | None) -> str | None:
    """Normalise a series item name to a product key.

    The sources describe the same product differently ("Regular Gasoline" vs
    "Regular unleaded gasoline at self service filling stations"), so the UI
    can group them with one vocabulary.
    """
    text = (item or "").lower()
    if "diesel" in text:
        return "diesel"
    if "midgrade" in text:
        return "midgrade"
    if "premium" in text:
        return "premium"
    if "regular" in text:
        return "regular"
    if "heating" in text:
        return "heating"
    return None


async def _fetch_region(client: whereq_cloud.Client, region: str) -> list[dict]:
    """All series for one region, paging until the reported count is reached."""
    rows: list[dict] = []
    offset = 0
    while True:
        page = await asyncio.to_thread(
            client.fuel_prices, region=region, limit=_PAGE_SIZE, offset=offset)
        data = page.get("data") or []
        if not data:
            break
        rows.extend(data)
        offset += len(data)
        total = page.get("count")
        if total is not None and offset >= total:
            break
    return rows


async def upsert_series(db: AsyncSession, series: list[dict], batch: int = 200) -> int:
    """Upsert price series by their whereq.cloud id."""
    written = 0
    for i in range(0, len(series), batch):
        chunk = series[i:i + batch]
        values = [{
            "id": s.get("id"),
            "domain": s.get("domain") or "fuel",
            "source": s.get("source"),
            "region": (s.get("region") or "").lower() or None,
            "geo": s.get("geo"),
            "item": s.get("item") or "",
            "unit": s.get("unit"),
            "frequency": s.get("frequency"),
            "latest_period": s.get("latest_period"),
            "latest_value": s.get("latest_value"),
            "prev_value": s.get("prev_value"),
            "points": s.get("points"),
            "spark": s.get("spark") or None,
        } for s in chunk if s.get("id") is not None]
        if not values:
            continue
        stmt = pg_insert(FuelPriceSeries).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[FuelPriceSeries.id],
            set_={
                "domain": stmt.excluded.domain,
                "source": stmt.excluded.source,
                "region": stmt.excluded.region,
                "geo": stmt.excluded.geo,
                "item": stmt.excluded.item,
                "unit": stmt.excluded.unit,
                "frequency": stmt.excluded.frequency,
                "latest_period": stmt.excluded.latest_period,
                "latest_value": stmt.excluded.latest_value,
                "prev_value": stmt.excluded.prev_value,
                "points": stmt.excluded.points,
                "spark": stmt.excluded.spark,
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
        written += len(values)
    return written


async def crawl_price_series(db: AsyncSession, *,
                             regions: list[str] | None = None) -> dict[str, int]:
    """Crawl the aggregated series for the configured regions.

    Returns ``{region: series written}``.
    """
    regions = regions if regions is not None else configured_regions()
    if not settings.WHEREQ_CLOUD_API_KEY:
        logger.warning("fuel price series crawl skipped — no WHEREQ_CLOUD_API_KEY")
        return {}

    results: dict[str, int] = {}
    with whereq_cloud.Client(api_key=settings.WHEREQ_CLOUD_API_KEY,
                             timeout=settings.WHEREQ_CLOUD_TIMEOUT) as client:
        for region in regions:
            try:
                rows = await _fetch_region(client, region)
            except whereq_cloud.WhereqError as exc:
                logger.warning("fuel price series (%s) failed: %s", region, exc)
                results[region] = 0
                continue
            if rows:
                await upsert_series(db, rows)
                await db.commit()
            results[region] = len(rows)
            logger.info("fuel price series %s: %d series", region, len(rows))
    return results


async def list_series(db: AsyncSession, *, region: str | None = None,
                      geo: str | None = None, q: str | None = None,
                      limit: int = 100, offset: int = 0) -> list[FuelPriceSeries]:
    """Stored price series, newest id first."""
    stmt = select(FuelPriceSeries)
    if region:
        stmt = stmt.where(FuelPriceSeries.region == region.lower())
    if geo:
        stmt = stmt.where(FuelPriceSeries.geo.ilike(f"%{geo}%"))
    if q:
        stmt = stmt.where(FuelPriceSeries.item.ilike(f"%{q}%"))
    stmt = stmt.order_by(FuelPriceSeries.region, FuelPriceSeries.geo,
                          FuelPriceSeries.item).offset(offset).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def list_regions(db: AsyncSession) -> list[dict]:
    """Distinct region/geo pairs that have series (for a picker)."""
    rows = (await db.execute(
        select(FuelPriceSeries.region, FuelPriceSeries.geo, FuelPriceSeries.unit)
        .distinct()
        .order_by(FuelPriceSeries.region, FuelPriceSeries.geo)
    )).all()
    return [{"region": r, "geo": g, "unit": u} for r, g, u in rows]

#: Display order for the products we surface.
PRODUCT_ORDER = ("regular", "midgrade", "premium", "diesel", "heating")


def _series_rank(series: dict) -> tuple:
    """Rank candidate series for one product — the best one wins.

    The Canadian series come in full-service and self-service flavours, and
    some of the full-service ones stopped being updated years ago. The most
    recent series wins; between two equally recent ones, self-service is
    preferred (it is what most drivers actually pay), then the longer
    history.
    """
    item = (series.get("item") or "").lower()
    if "self service" in item:
        service = 0
    elif "full service" in item:
        service = 1
    else:
        service = 2
    return (series.get("latest_period") or "", -service, series.get("points") or 0)


def preferred_series(series: list[dict]) -> list[dict]:
    """One representative series per product, in display order."""
    best: dict[str, dict] = {}
    for row in series:
        key = row.get("product")
        if not key:
            continue
        current = best.get(key)
        if current is None or _series_rank(row) > _series_rank(current):
            best[key] = row
    return sorted(
        best.values(),
        key=lambda r: (PRODUCT_ORDER.index(r["product"])
                       if r["product"] in PRODUCT_ORDER else 99, r.get("geo") or ""),
    )


async def price_series_due(db: AsyncSession, interval_hours: int | None = None) -> bool:
    """Whether the stored series are stale enough to refresh.

    The tick runs hourly but only crawls when the data is older than the
    refresh interval, so a failed run (e.g. the crawler started before the
    migration) is retried within the hour instead of a whole interval later.
    """
    interval = interval_hours if interval_hours is not None else settings.FUEL_PRICES_INTERVAL_HOURS
    try:
        newest = (await db.execute(
            select(func.max(FuelPriceSeries.updated_at)))).scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.warning("fuel price series unavailable (%s) — treating as due", exc)
        return True
    if newest is None:
        return True
    age = datetime.now(timezone.utc) - newest
    return age >= timedelta(hours=interval)


# ── viewport resolution ─────────────────────────────────────────────────────
@dataclass
class ViewportRegion:
    """The area the user is looking at, resolved from the crawled stations."""

    country: str | None = None
    state: str | None = None
    municipality: str | None = None
    station_count: int = 0
    slug: str | None = None
    geo: str | None = None


def series_to_dict(row: FuelPriceSeries) -> dict:
    """A stored series as the API returns it (with the litre-normalized value)."""
    value_per_litre, currency = normalize_per_litre(row.unit, row.latest_value)
    return {
        "id": row.id,
        "domain": row.domain,
        "source": row.source,
        "region": row.region,
        "geo": row.geo,
        "item": row.item,
        "product": product_key(row.item),
        "unit": row.unit,
        "currency": currency,
        "value_per_litre": value_per_litre,
        "frequency": row.frequency,
        "latest_period": row.latest_period,
        "latest_value": row.latest_value,
        "prev_value": row.prev_value,
        "points": row.points,
        "spark": row.spark,
        "updated_at": row.updated_at,
    }


async def resolve_viewport_region(db: AsyncSession, bbox: str | None = None) -> ViewportRegion:
    """Resolve the country/state/municipality of the fuel stations in view.

    The stations we crawl carry their country, state and city, so the map
    viewport tells us which region the user is looking at — which in turn
    picks the matching regional price average.
    """
    # The JSONB extraction must appear in GROUP BY as the full expression,
    # not just the column.
    state_expr = Place.metadata_json["state"].astext
    stmt = (
        select(
            Place.country,
            state_expr,
            Place.city,
            func.count(),
        )
        .where(Place.source == "whereq_cloud")
        .group_by(Place.country, state_expr, Place.city)
        .order_by(func.count().desc())
        .limit(1)
    )
    if bbox:
        parts = [p.strip() for p in bbox.split(",")]
        if len(parts) == 4:
            mn_lng, mn_lat, mx_lng, mx_lat = (float(p) for p in parts)
            stmt = stmt.where(func.ST_Intersects(
                Place.geom,
                func.ST_MakeEnvelope(mn_lng, mn_lat, mx_lng, mx_lat, 4326),
            ))
    row = (await db.execute(stmt)).first()
    if not row:
        return ViewportRegion()
    country, state, municipality, count = row
    country = (country or "").upper() or None
    return ViewportRegion(
        country=country,
        state=state,
        municipality=municipality,
        station_count=count or 0,
        slug=country.lower() if country else None,
    )


def _candidate_geos(country: str | None, state: str | None,
                    municipality: str | None, geos: list[str]) -> list[str]:
    """Geo labels that could hold the average for an area, best match first.

    The US series are per state (and city) plus a national "U.S." row; the
    Canadian ones are per metro ("Toronto, Ontario") plus a national
    "Canada" row. Mexican ones are per state.
    """
    if not country:
        return []
    code = country.upper()
    if code == "US":
        out = [state.upper()] if state else []
        out.append("U.S.")
        return out
    if code == "CA":
        out = []
        if municipality and state:
            out.append(f"{municipality}, {state}")
        if state:
            lowered = state.lower()
            out.extend(g for g in geos if g.lower().endswith(f", {lowered}"))
        out.append("Canada")
        return out
    return [state] if state else []


async def viewport_averages(db: AsyncSession, bbox: str | None = None) -> dict:
    """Regional fuel averages for the area the user is looking at.

    Returns the resolved region plus the matching price series. Falls back to
    the national average when the exact region has no series.
    """
    region = await resolve_viewport_region(db, bbox)
    if not region.slug:
        return {"region": None, "series": []}

    rows = await list_series(db, region=region.slug, limit=500)
    geos = [r.geo for r in rows if r.geo]
    wanted = _candidate_geos(region.country, region.state, region.municipality, geos)
    wanted_lower = {g.lower() for g in wanted}

    matched = [r for r in rows if r.geo and r.geo.lower() in wanted_lower]
    # Keep the best match only — the national row is a fallback, not a peer.
    if matched:
        best = wanted_lower
        first = next((g for g in wanted if g.lower() in best), None)
        chosen = [r for r in matched if first and r.geo.lower() == first.lower()]
        if not chosen:
            chosen = matched
        geo_label = chosen[0].geo
    else:
        chosen = []
        geo_label = None

    region.geo = geo_label
    return {
        "region": {
            "country": region.country,
            "state": region.state,
            "municipality": region.municipality,
            "geo": region.geo,
            "station_count": region.station_count,
        },
        # One representative series per product (self-service, most recent).
        "series": preferred_series([series_to_dict(r) for r in chosen]),
    }
