"""Google Routes API for the Maps service — /route + /matrix.

Uses the **Routes API** (``routes.googleapis.com``), the going-forward
replacement for the legacy Directions + Distance Matrix web services:

- ``/route``  → ``POST directions/v2:computeRoutes``
- ``/matrix`` → ``POST distanceMatrix/v2:computeRouteMatrix``

Auth is the ``X-Goog-Api-Key`` header; every call requires an ``X-Goog-FieldMask``
naming the fields to return. No free road-routing provider is configured, so
Google is the sole provider.

Per Google Maps ToS, routing results may be cached only short-term: ``/route``
results are cached in ``route_cache`` with a TTL (``MAPS_ROUTE_CACHE_TTL_SECONDS``)
keyed on mode + coordinates rounded to ~5 dp. ``/matrix`` is not cached — dispatch
inputs (live driver positions) vary too much for a useful hit rate.

Distances are metres, durations seconds; polylines are Google encoded polylines
(precision 5), drawn directly by consumers (e.g. a Leaflet map).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.maps import RouteCache

logger = logging.getLogger(__name__)

_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"

# public mode → Routes API travelMode
_MODE_MAP = {"driving": "DRIVE", "walking": "WALK", "cycling": "BICYCLE"}
VALID_MODES = frozenset(_MODE_MAP)

Coord = tuple[float, float]


def is_configured() -> bool:
    return bool(settings.maps_google_key)


def _google_mode(mode: str) -> str:
    return _MODE_MAP.get((mode or "driving").lower(), "DRIVE")


def _route_cache_key(mode: str, origin: Coord, destination: Coord, traffic: bool) -> str:
    o = f"{origin[0]:.5f},{origin[1]:.5f}"
    d = f"{destination[0]:.5f},{destination[1]:.5f}"
    raw = f"route|{_google_mode(mode)}|{o}|{d}|traffic={int(traffic)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_duration(val) -> int | None:
    """Routes API durations are strings like ``"2040s"`` → seconds int."""
    if val is None:
        return None
    try:
        return int(round(float(str(val).rstrip("s"))))
    except (ValueError, TypeError):
        return None


def _waypoint(coord: Coord) -> dict:
    return {"location": {"latLng": {"latitude": coord[0], "longitude": coord[1]}}}


def _rfc3339(departure_time: str) -> str | None:
    """Convert a caller departure_time to RFC3339, or None to use 'now' default.

    ``"now"`` → None (Routes API defaults departureTime to request time). A unix
    timestamp (all digits) → RFC3339 Z. Anything else is assumed already RFC3339.
    """
    if not departure_time or departure_time == "now":
        return None
    if departure_time.isdigit():
        dt = datetime.fromtimestamp(int(departure_time), tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    return departure_time


def _parse_route(body: dict, traffic: bool = False) -> dict | None:
    """Normalize a computeRoutes response to the §3.4 route object.

    ``duration`` is traffic-aware when ``routingPreference=TRAFFIC_AWARE``;
    ``staticDuration`` is the free-flow baseline. We report the baseline as
    ``duration_s`` and only surface ``duration_in_traffic_s`` when traffic was
    requested (else null, per the contract).
    """
    routes = body.get("routes") or []
    if not routes:
        return None
    r = routes[0]
    duration_s = _parse_duration(r.get("duration"))
    static_s = _parse_duration(r.get("staticDuration"))

    vp = r.get("viewport") or {}
    low, high = vp.get("low") or {}, vp.get("high") or {}
    bounds = None
    if low and high:
        bounds = {"north": high.get("latitude"), "south": low.get("latitude"),
                  "east": high.get("longitude"), "west": low.get("longitude")}

    return {
        "distance_m": int(r.get("distanceMeters") or 0),
        "duration_s": static_s if static_s is not None else duration_s,
        "duration_in_traffic_s": duration_s if traffic else None,
        "polyline": (r.get("polyline") or {}).get("encodedPolyline"),
        "bounds": bounds,
    }


async def route(
    db: AsyncSession, *,
    origin: Coord,
    destination: Coord,
    mode: str = "driving",
    departure_time: str | None = None,
    alternatives: bool = False,
) -> tuple[dict | None, bool]:
    """Road distance/duration/geometry. Returns ``(route_obj, cached)``."""
    travel_mode = _google_mode(mode)
    traffic = bool(departure_time) and travel_mode == "DRIVE"
    key = _route_cache_key(mode, origin, destination, traffic)

    row = (await db.execute(
        select(RouteCache).where(RouteCache.key == key))).scalar_one_or_none()
    if row is not None:
        age = (datetime.now(timezone.utc) - row.created_at).total_seconds()
        if age <= settings.MAPS_ROUTE_CACHE_TTL_SECONDS:
            return ({
                "distance_m": row.distance_m,
                "duration_s": row.duration_s,
                "duration_in_traffic_s": row.duration_in_traffic_s,
                "polyline": row.polyline,
                "bounds": row.bounds,
            }, True)
        await db.delete(row)   # stale → re-fetch + re-cache below
        await db.commit()

    if not is_configured():
        return None, False

    payload: dict = {
        "origin": _waypoint(origin),
        "destination": _waypoint(destination),
        "travelMode": travel_mode,
        "polylineEncoding": "ENCODED_POLYLINE",
        "computeAlternativeRoutes": bool(alternatives),
    }
    if traffic:
        payload["routingPreference"] = "TRAFFIC_AWARE"
        dep = _rfc3339(departure_time)
        if dep:
            payload["departureTime"] = dep

    headers = {
        "X-Goog-Api-Key": settings.maps_google_key,
        "X-Goog-FieldMask": ("routes.distanceMeters,routes.duration,"
                             "routes.staticDuration,routes.polyline.encodedPolyline,"
                             "routes.viewport"),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.post(_ROUTES_URL, json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()

    parsed = _parse_route(body, traffic)
    if parsed is None:
        return None, False

    await _store_route(db, key, parsed)
    return parsed, False


async def _store_route(db: AsyncSession, key: str, parsed: dict) -> None:
    stmt = pg_insert(RouteCache).values(
        key=key,
        distance_m=parsed["distance_m"],
        duration_s=parsed["duration_s"],
        duration_in_traffic_s=parsed["duration_in_traffic_s"],
        polyline=parsed["polyline"],
        bounds=parsed["bounds"],
        provider="google",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "distance_m": parsed["distance_m"],
            "duration_s": parsed["duration_s"],
            "duration_in_traffic_s": parsed["duration_in_traffic_s"],
            "polyline": parsed["polyline"],
            "bounds": parsed["bounds"],
            "created_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()


def _parse_matrix(elements: list[dict], n_origins: int, n_destinations: int) -> dict:
    """Rebuild the §3.5 rows/elements grid from computeRouteMatrix's flat list.

    computeRouteMatrix returns a flat array of elements carrying ``originIndex``
    / ``destinationIndex``; we scatter them into an origins × destinations grid.
    """
    grid = [[{"distance_m": None, "duration_s": None, "status": "ZERO_RESULTS"}
             for _ in range(n_destinations)] for _ in range(n_origins)]
    for el in elements or []:
        oi, di = el.get("originIndex"), el.get("destinationIndex")
        if oi is None or di is None or oi >= n_origins or di >= n_destinations:
            continue
        if el.get("condition") == "ROUTE_EXISTS":
            grid[oi][di] = {
                "distance_m": el.get("distanceMeters"),
                "duration_s": _parse_duration(el.get("duration")),
                "status": "OK",
            }
        else:
            grid[oi][di] = {"distance_m": None, "duration_s": None,
                            "status": el.get("condition") or "ZERO_RESULTS"}
    return {"rows": [{"elements": row} for row in grid]}


async def matrix(
    db: AsyncSession, *,
    origins: list[Coord],
    destinations: list[Coord],
    mode: str = "driving",
) -> tuple[dict | None, str | None]:
    """Many-to-one (or many-to-many) distances. Returns ``(matrix_obj, provider)``.

    Not cached (see module docstring). ``db`` is accepted for signature symmetry
    and future usage accounting.
    """
    if not is_configured():
        return None, None

    travel_mode = _google_mode(mode)
    payload: dict = {
        "origins": [{"waypoint": _waypoint(o)} for o in origins],
        "destinations": [{"waypoint": _waypoint(d)} for d in destinations],
        "travelMode": travel_mode,
    }
    if travel_mode == "DRIVE":
        payload["routingPreference"] = "TRAFFIC_AWARE"

    headers = {
        "X-Goog-Api-Key": settings.maps_google_key,
        "X-Goog-FieldMask": ("originIndex,destinationIndex,distanceMeters,"
                             "duration,condition"),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.post(_MATRIX_URL, json=payload, headers=headers)
        resp.raise_for_status()
        elements = resp.json()   # flat JSON array of RouteMatrixElement

    return _parse_matrix(elements, len(origins), len(destinations)), "google"
