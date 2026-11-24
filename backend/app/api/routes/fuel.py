"""Fuel price data (whereq.cloud) — signed-in users only.

The whereq.cloud API key stays on the server: the browser calls these
endpoints, which read whereq.cloud over the SDK. Nothing here spends metered
quota at request time *in the local mode*; in the ``cloud`` mode the read is
live, and the key's tier is what bounds it.

The data itself is licensed and metered upstream, so the whole router
requires a session (Keycloak token). Anonymous visitors still see the fuel
stations on the map — the prices are stripped from the place payloads instead.

WHERE THE ROWS COME FROM
------------------------
Three modes, switched by ``FUEL_READ_MODE`` — the same three movements as the
geography's ``CLOUD_READ_MODE``:

* ``local``  — this app's own mirror: the stations in ``places`` and the
               series in ``fuel_price_series``.
* ``dual``   — both. The two answers are compared and the comparison is
  written down, and the **local** answer is what the caller gets.
* ``cloud``  — whereq.cloud directly.

In ``cloud`` mode the upstream's payload is **re-shaped** into this app's own
shape (``app.services.cloud_fuel``), never passed through verbatim — and a
demo preview is an error, not a fallback: whereq.cloud's preview carries
prices too, so serving it would serve a frozen slice as though it were live.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.fuel import (
    FuelAveragesRead,
    FuelRegionRead,
    FuelSeriesRead,
    FuelStationRead,
)
from app.services.fuel_prices import (
    list_regions,
    list_series,
    series_to_dict,
    viewport_averages,
)
from app.services.fuel_stations import find_stations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fuel", tags=["fuel"], dependencies=[Depends(get_current_user)])


def _mode() -> str:
    """Which copy of the fuel data this API reads: local | dual | cloud."""
    return (settings.FUEL_READ_MODE or "local").strip().lower()


@router.get("/prices", response_model=list[FuelSeriesRead])
async def fuel_prices(
    region: str | None = Query(None, description="Region slug: ca, us, mx"),
    geo: str | None = Query(None, description="Place label, e.g. 'Toronto, Ontario' or 'CALIFORNIA'"),
    q: str | None = Query(None, description="Search the product/item name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated fuel price averages (state / national / metro)."""
    mode = _mode()
    if mode == "cloud":
        return await _cloud_series(region=region, geo=geo, q=q, limit=limit)

    rows = await list_series(db, region=region, geo=geo, q=q, limit=limit, offset=offset)
    return [series_to_dict(r) for r in rows]


@router.get("/stations", response_model=list[FuelStationRead])
async def fuel_stations(
    q: str | None = Query(None, description="Station, brand or city name"),
    lat: float | None = Query(None, description="Latitude to measure distance from"),
    lng: float | None = Query(None, description="Longitude to measure distance from"),
    radius_km: float | None = Query(None, ge=0.1, le=500, description="Search radius (km)"),
    bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat of the viewport"),
    product: str = Query("regular", description="Product used for the price sort"),
    sort: str = Query("distance", pattern="^(distance|price)$"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Gas stations with their prices — nearest first, or cheapest first.

    In ``cloud`` mode the stations come from whereq.cloud live. The upstream
    filters by bbox and name; the distance sort and the radius are applied
    here, on the answer, because the upstream has no radius filter.
    """
    mode = _mode()
    if mode == "cloud":
        return await _cloud_stations(
            q=q, lat=lat, lng=lng, radius_km=radius_km, bbox=bbox,
            product=product, sort=sort, limit=limit)

    return await find_stations(db, q=q, lat=lat, lng=lng, radius_km=radius_km,
                               bbox=bbox, product=product, sort=sort, limit=limit)


@router.get("/averages", response_model=FuelAveragesRead)
async def fuel_averages(
    bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat of the map viewport"),
    db: AsyncSession = Depends(get_db),
):
    """Fuel averages for the area the map is showing.

    The region is resolved from the fuel stations inside the viewport, so the
    average always matches what the user is looking at (a Canadian metro, a
    US state, …) and falls back to the national figure when the exact region
    has no series.
    """
    mode = _mode()
    if mode == "cloud":
        return await _cloud_averages(bbox=bbox)
    return await viewport_averages(db, bbox)


@router.get("/regions", response_model=list[FuelRegionRead])
async def fuel_regions(db: AsyncSession = Depends(get_db)):
    """The region/geo pairs that have price series (for a picker)."""
    mode = _mode()
    if mode == "cloud":
        return await _cloud_regions()
    return await list_regions(db)


# ── the live reads ──────────────────────────────────────────────────────────
async def _cloud_series(*, region: str | None, geo: str | None, q: str | None,
                        limit: int) -> list[dict]:
    """The upstream's price series, re-shaped into this app's shape."""
    from app.services.cloud_fuel import fetch_all_series, series_to_read

    try:
        rows = await asyncio.to_thread(
            fetch_all_series, region=region, geo=geo, q=q, max_rows=limit)
    except Exception as exc:  # noqa: BLE001 — the upstream may fail in any way
        logger.warning("cloud fuel: the price series could not be read — %s", exc)
        raise HTTPException(status_code=502, detail="Fuel prices are unavailable") from exc
    return [series_to_read(r) for r in rows]


async def _cloud_stations(*, q: str | None, lat: float | None, lng: float | None,
                           radius_km: float | None, bbox: str | None,
                           product: str, sort: str, limit: int) -> list[dict]:
    """The upstream's stations, re-shaped and ordered here.

    The upstream filters by bbox and by name; the **distance** sort and the
    **radius** are applied to the answer, because the upstream has neither.
    A radius therefore needs a bbox to ask with, and the box is the one the
    radius describes.

    The whole box is read, page by page, because the upstream orders the rows
    by its own station id: sorting a single page would sort an arbitrary slice
    of the area, and the "nearest" station of that slice can be 16 km away
    while the real one is 685 m away. The upstream reports the total with
    every page, so a box that holds more than the read ceiling is known, and
    the answer says it was truncated.
    """
    from app.services.cloud_fuel import fetch_stations_paged, station_to_read

    query_box = bbox
    if radius_km and lat is not None and lng is not None:
        # The radius is the tighter of the two constraints, so the box asked
        # for is the intersection — the same set the local query returned
        # (the viewport AND the circle), and far fewer rows to read.
        radius_box = _radius_box(lat, lng, radius_km)
        query_box = _intersect_box(query_box, radius_box) or radius_box

    try:
        payload = await asyncio.to_thread(
            fetch_stations_paged, bbox=query_box, q=q)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud fuel: the stations could not be read — %s", exc)
        raise HTTPException(status_code=502, detail="Fuel stations are unavailable") from exc

    stations = payload.get("stations") or []
    if not payload.get("complete", True):
        total = payload.get("total")
        logger.warning(
            "cloud fuel: the box holds %s stations and only %s could be read — "
            "the order of the answer is a best effort", total, len(stations))
    out = [station_to_read(s, product=product) for s in stations]
    out = [s for s in out if s.get("lat") is not None and s.get("lng") is not None]

    distance = None
    if lat is not None and lng is not None:
        for s in out:
            s["distance_km"] = _distance_km(lat, lng, s["lat"], s["lng"])
        if radius_km:
            out = [s for s in out if (s["distance_km"] or 0) <= radius_km]
        distance = True

    if sort == "price":
        # Cheapest first; stations without that product sort last.
        out.sort(key=lambda s: (s.get("price") is None, s.get("price") or 0))
    elif distance:
        out.sort(key=lambda s: s.get("distance_km") or 0)
    else:
        out.sort(key=lambda s: s.get("name") or "")
    return out[:limit]


def _intersect_box(a: str | None, b: str | None) -> str | None:
    """The overlap of two ``minLng,minLat,maxLng,maxLat`` boxes.

    ``None`` when either box is missing (nothing to intersect) or when the
    boxes do not overlap.
    """
    def parts(box: str | None) -> tuple[float, float, float, float] | None:
        if not box:
            return None
        try:
            vals = tuple(float(v) for v in box.split(","))
        except ValueError:
            return None
        if len(vals) != 4:
            return None
        return vals  # type: ignore[return-value]

    pa, pb = parts(a), parts(b)
    if pa is None:
        return pb and ",".join(str(v) for v in pb)
    if pb is None:
        return ",".join(str(v) for v in pa)
    lo_lng, lo_lat = max(pa[0], pb[0]), max(pa[1], pb[1])
    hi_lng, hi_lat = min(pa[2], pb[2]), min(pa[3], pb[3])
    if lo_lng > hi_lng or lo_lat > hi_lat:
        return None
    return ",".join(str(v) for v in (lo_lng, lo_lat, hi_lng, hi_lat))


async def _cloud_regions() -> list[dict]:
    """The region/geo pairs that have series, read from the upstream.

    The upstream has no "distinct regions" route, so the series are read and
    reduced here. The series are few (122 for Canada) but the page is 100
    rows, so this costs two or three requests.
    """
    from app.services.cloud_fuel import fetch_all_series, series_to_read

    try:
        rows = await asyncio.to_thread(fetch_all_series, max_rows=2000)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud fuel: the regions could not be read — %s", exc)
        raise HTTPException(status_code=502, detail="Fuel regions are unavailable") from exc

    seen: dict[tuple, dict] = {}
    for row in rows:
        series = series_to_read(row)
        key = (series.get("region"), series.get("geo"), series.get("unit"))
        if key not in seen:
            seen[key] = {"region": key[0], "geo": key[1], "unit": key[2]}
    return sorted(seen.values(), key=lambda r: (r["region"] or "", r["geo"] or ""))


async def _cloud_averages(*, bbox: str | None) -> dict:
    """Regional averages, with the region resolved from the live stations.

    The local version resolves the region from the **mirrored** stations; the
    live version resolves it from the stations whereq.cloud serves for the
    viewport, which is the same answer by a different route.
    """
    from app.services.cloud_fuel import fetch_all_series, fetch_stations, series_to_read
    from app.services.fuel_prices import _candidate_geos, preferred_series

    region: dict[str, Any] = {}
    if bbox:
        try:
            payload = await asyncio.to_thread(fetch_stations, bbox=bbox, limit=100)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cloud fuel: the viewport stations could not be read — %s", exc)
            raise HTTPException(status_code=502, detail="Fuel averages are unavailable") from exc
        stations = payload.get("stations") or []
        if stations:
            country = (stations[0].get("country") or "").upper() or None
            state = stations[0].get("state")
            municipality = stations[0].get("municipality")
            region = {
                "country": country,
                "state": state,
                "municipality": municipality,
                "geo": None,
                "station_count": payload.get("total") or len(stations),
            }

    if not region.get("country"):
        return {"region": None, "series": []}

    slug = region["country"].lower()
    try:
        rows = await asyncio.to_thread(fetch_all_series, region=slug, max_rows=500)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud fuel: the averages could not be read — %s", exc)
        raise HTTPException(status_code=502, detail="Fuel averages are unavailable") from exc

    series = [series_to_read(r) for r in rows]
    geos = [s.get("geo") for s in series if s.get("geo")]
    wanted = _candidate_geos(region["country"], region.get("state"),
                             region.get("municipality"), geos)
    wanted_lower = {g.lower() for g in wanted}
    matched = [s for s in series if s.get("geo") and s["geo"].lower() in wanted_lower]
    if matched:
        first = next((g for g in wanted if g.lower() in wanted_lower), None)
        chosen = ([s for s in matched if s["geo"].lower() == first.lower()]
                  if first else matched) or matched
        region["geo"] = chosen[0].get("geo")
    else:
        chosen = []

    return {"region": region, "series": preferred_series(chosen)}


def _radius_box(lat: float, lng: float, radius_km: float) -> str:
    """The bbox a radius describes — for the upstream's bbox filter.

    One degree of latitude is ~111.32 km; one degree of longitude is that
    times the cosine of the latitude. The box is a little generous, because
    the upstream filters on the point and the distance is applied here.
    """
    import math

    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 1e-6))
    return f"{lng - dlon:.6f},{lat - dlat:.6f},{lng + dlon:.6f},{lat + dlat:.6f}"


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
