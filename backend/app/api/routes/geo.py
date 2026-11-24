"""Administrative geography — the areas that contain the places.

The whereq.cloud geography feed: provinces, regions, municipalities, cities,
towns, wards and neighbourhoods, with real outlines. This router serves the
rows already synced from the feed, so it never spends upstream quota and the
API key stays on the server.

**Public.** The feed is open data — OpenStreetMap under ODbL 1.0, geoBoundaries
under CC-BY 4.0 — both of which permit redistribution with attribution. So the
licence travels on every row and the UI shows it, but there is no licence
reason to hide the data from an anonymous visitor (unlike the fuel prices).

Two vocabularies are kept side by side and are never merged: a census
subdivision and an OSM city boundary describe the same town in two languages,
and the feed deliberately ships both. So a containment answer says *which*
vocabulary each hit came from.
"""

from __future__ import annotations

import json
import logging
import math
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.geo import GeoConcept, GeoPlace
from app.schemas.geo import (
    GeoAtRead,
    GeoAtResponse,
    GeoBoundaryListRead,
    GeoBoundaryRead,
    GeoConceptRead,
    GeoPlaceDetail,
    GeoPlaceRead,
)
from app.services.geo_places import concepts_with_counts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["geo"])

#: The kinds whose outlines are too big to draw.
#:
#: A province outline is 65 000 points even after the simplification (it is a
#: multipolygon of 4 000 lakes and islands), against 68 for a ward. They are
#: also off-screen at every zoom where the area layer is useful. So the
#: outlines endpoint leaves them out **unless a caller asks for them by name**;
#: the containment stack still reports them.
LARGE_KINDS = ("country", "province", "state")


def _parse_bbox(bbox: str | None):
    """bbox = 'minLng,minLat,maxLng,maxLat' → tuple or None."""
    if not bbox:
        return None
    try:
        a, b, c, d = (float(x) for x in bbox.split(","))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'")
    if a > c or b > d:
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'")
    return a, b, c, d


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


#: The metres in one degree, as a function of the latitude.
#:
#: These are the constants of the tolerance rule, defined ONCE so the readable
#: Python reference (:func:`_simplify_tolerance_degrees`) and the SQL expression
#: the database runs (:func:`_tolerance_expression`) cannot drift apart.
#:
#: * one degree of **latitude**: ``a - b·cos 2φ + c·cos 4φ``
#: * one degree of **longitude**: ``a·cos φ - b·cos 3φ``
M_PER_DEG_LAT = (111132.92, 559.82, 1.175)
M_PER_DEG_LON = (111412.84, 93.5)


def _simplify_tolerance_degrees(metres: float, lat: float | None) -> float:
    """The tolerance ``ST_Simplify`` wants, in degrees, for a given error in metres.

    PostGIS 3.7 has **no geography overload** of ``ST_Simplify`` — it works on
    geometry, whose unit here is a degree. A degree is not a fixed length: a
    degree of longitude is ~111 km at the equator and ~81 km at Toronto.

    So the tolerance is derived from the place's own latitude: the number of
    metres in one degree of longitude and one degree of latitude are both
    computed, and the tolerance is the budget divided by the **larger** of the
    two. A degree is the unit on *both* axes, so the axis with more metres per
    degree is the one that binds — and the other axis then moves less than the
    budget, never more.
    """
    if metres <= 0:
        return 0.0
    phi = math.radians(max(-89.0, min(89.0, lat if lat is not None else 0.0)))
    a, b, c = M_PER_DEG_LAT
    d, e = M_PER_DEG_LON
    m_per_deg_lat = a - b * math.cos(2 * phi) + c * math.cos(4 * phi)
    m_per_deg_lon = d * math.cos(phi) - e * math.cos(3 * phi)
    # At the poles a degree of longitude collapses; fall back to the latitude
    # scale rather than dividing by ~0.
    m_per_deg_lon = max(m_per_deg_lon, 1.0)
    per_degree = max(m_per_deg_lat, m_per_deg_lon)
    return metres / per_degree


def _tolerance_expression(metres: float):
    """The tolerance in degrees, as SQL — **each place at its own latitude**.

    The same rule as :func:`_simplify_tolerance_degrees`, written where the
    geometry is, so a whole viewport's outlines are simplified in one query.

    Per PLACE, not per batch: an outline's shape then does not depend on which
    other outlines happen to be in the same answer, so one place is the same
    shape whether it is drawn alone or in a viewport of three hundred. That is
    also what makes the upstream's outlines and these ones comparable — the
    upstream simplifies the same way, and two readers that batched the same
    places differently still agree about the same outline.
    """
    lat = func.least(89.0, func.greatest(-89.0, func.coalesce(GeoPlace.centroid_lat, 0.0)))
    phi = func.radians(lat)
    a, b, c = M_PER_DEG_LAT
    d, e = M_PER_DEG_LON
    m_per_deg_lat = a - b * func.cos(2 * phi) + c * func.cos(4 * phi)
    m_per_deg_lon = func.greatest(d * func.cos(phi) - e * func.cos(3 * phi), 1.0)
    return metres / func.greatest(m_per_deg_lat, m_per_deg_lon)


@router.get("/concepts", response_model=list[GeoConceptRead])
async def geo_concepts(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """The vocabulary — every kind of administrative place, with our counts.

    ``places`` is how many *we* hold (the ones the app can draw);
    ``upstream_places`` is the feed's own count for the whole dataset.

    The three read modes apply here too: ``dual`` compares the vocabulary
    with the upstream's and serves the local one; ``cloud`` serves the
    upstream's. The **counts** are not compared — the mirror's copy of the
    feed's count is a snapshot of the last sync, and the upstream's is live,
    so the two drift apart as the upstream grows. That is not a difference
    in the data; it is the passage of time.
    """
    mode = _mode()
    if mode == "cloud":
        from app.services.cloud_geo import concepts_to_read

        payload = await _cloud_concepts()
        return [GeoConceptRead(**c) for c in concepts_to_read(payload)]

    local = await concepts_with_counts(db)
    if mode == "dual":
        background_tasks.add_task(_record_concepts_parity, local)
    return local


@router.get("/places", response_model=list[GeoPlaceRead])
async def geo_places(
    background_tasks: BackgroundTasks,
    bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat of the viewport"),
    kind: str | None = Query(None, description="One or more kinds, comma separated"),
    source: str | None = Query(None, description="One or more sources: osm, geoboundaries"),
    q: str | None = Query(None, description="Name search"),
    has_boundary: bool | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """The administrative places inside a viewport (or filtered some other way).

    This is the layer the map draws: the outlines of the cities, wards and
    neighbourhoods the user is looking at.

    WHERE THE ROWS COME FROM
    ------------------------
    Three modes, switched by ``CLOUD_READ_MODE`` — see the migration guide:

    * ``local``  — the local mirror. Today's behaviour.
    * ``dual``   — both. The two answers are compared and the comparison is
      written down, and the **local** answer is what the caller gets. The app
      behaves exactly as it did, and the ledger fills up with the evidence.
    * ``cloud``  — whereq.cloud directly. The mirror is no longer read here.

    In ``dual`` mode an upstream failure must not fail the request: the
    caller still gets the local answer, and the failed comparison is recorded
    as a failure — never as a clean one.
    """
    conds = []
    bb = _parse_bbox(bbox)
    if bb:
        # The feed gives every place its own bounding box, so the viewport
        # filter does not need the outline: a place we hold no geometry for
        # still belongs in the viewport it sits in.
        mnlng, mnlat, mxlng, mxlat = bb
        conds.append(and_(
            GeoPlace.bbox_max_lon >= mnlng,
            GeoPlace.bbox_min_lon <= mxlng,
            GeoPlace.bbox_max_lat >= mnlat,
            GeoPlace.bbox_min_lat <= mxlat,
        ))

    kinds = _csv(kind)
    if kinds:
        conds.append(GeoPlace.kind.in_(kinds))
    sources = _csv(source)
    if sources:
        conds.append(GeoPlace.source.in_(sources))
    if q:
        pattern = f"%{q.strip()}%"
        conds.append(or_(
            GeoPlace.name.ilike(pattern),
            GeoPlace.name_local.ilike(pattern),
            GeoPlace.official_name.ilike(pattern),
        ))
    if has_boundary is not None:
        conds.append(GeoPlace.geom.is_not(None) if has_boundary
                     else GeoPlace.geom.is_(None))

    mode = _mode()
    params = {
        "bbox": bbox, "kind": kind, "source": source, "q": q,
        "has_boundary": has_boundary, "limit": limit,
    }

    if mode == "cloud":
        rows = await _cloud_places(bbox, kinds, sources, q, has_boundary, limit)
        return [GeoPlaceRead(**r) for r in rows]

    # Only the columns the response carries. Selecting the whole entity would
    # pull the full-resolution outline (JSONB) *and* the PostGIS geometry
    # (as EWKB) into memory — megabytes per request for rows whose outline
    # this endpoint never returns.
    rows = (await db.execute(
        select(
            GeoPlace.uid, GeoPlace.kind, GeoPlace.name, GeoPlace.name_en,
            GeoPlace.name_zh, GeoPlace.name_local, GeoPlace.official_name,
            GeoPlace.source, GeoPlace.source_url, GeoPlace.license,
            GeoPlace.country_code, GeoPlace.province_code, GeoPlace.population,
            GeoPlace.area_km2, GeoPlace.centroid_lon, GeoPlace.centroid_lat,
            GeoPlace.geom.is_not(None).label("has_boundary"),
        ).where(*conds).order_by(GeoPlace.kind, GeoPlace.name).limit(limit)
    )).all()
    local = [dict(
        uid=r[0], kind=r[1], name=r[2], name_en=r[3], name_zh=r[4],
        name_local=r[5], official_name=r[6], source=r[7], source_url=r[8],
        license=r[9], country_code=r[10], province_code=r[11], population=r[12],
        area_km2=r[13], centroid_lon=r[14], centroid_lat=r[15],
        has_boundary=bool(r[16]),
    ) for r in rows]

    if mode == "dual":
        # The local answer is whole only if the limit did not cut it short:
        # a truncated local answer cannot be compared against a truncated
        # upstream one, because neither of them says what it left out.
        local_complete = len(local) < limit
        # The comparison runs AFTER the response. The window must not make
        # the app wait on the upstream — that would make the app's speed and
        # its availability depend on the very thing the window is testing.
        background_tasks.add_task(
            _record_parity, bbox, kinds, sources, q, has_boundary, limit,
            local, local_complete)

    return [GeoPlaceRead(**r) for r in local]


def _mode() -> str:
    """Which copy of the geography this API reads: local | dual | cloud."""
    return (settings.CLOUD_READ_MODE or "local").strip().lower()


def _boundaries_mode() -> str:
    """Which copy the OUTLINES read: local | dual | cloud.

    The outlines have their own switch, because their cut needed a bulk
    geometry endpoint on the platform and their window is therefore their
    own decision. Empty means the geography's own switch, so an operator
    who never touches it gets one switch for the whole geography.
    """
    own = (settings.GEO_BOUNDARIES_READ_MODE or "").strip().lower()
    return own or _mode()


async def _cloud_places(bbox, kinds, sources, q, has_boundary, limit) -> list[dict]:
    """The upstream's answer, as this app's reader returns it.

    The SDK is **synchronous**, so the call is put on a thread. The crawler's
    own service calls it inline, which is fine there — one job at a time in
    a container of its own — but this is the API server, and blocking the
    event loop on an upstream round trip would stall every other request the
    map server is serving.
    """
    import asyncio

    from app.services.cloud_geo import fetch_cloud_places

    answer = await asyncio.to_thread(
        fetch_cloud_places,
        bbox=bbox, kinds=kinds, sources=sources, q=q,
        has_boundary=has_boundary, limit=limit,
    )
    return answer.rows


async def _record_parity(bbox, kinds, sources, q, has_boundary, limit, local,
                         local_complete: bool = True) -> None:
    """Compare this answer with upstream's and write the comparison down.

    The comparison is best-effort by design: a failure to read upstream, or
    to write the ledger, must never fail the request the user is waiting
    for. But a failure is never silent either — it is logged, and the
    comparison is recorded as a failure.
    """
    import asyncio

    from app.core.database import AsyncSessionLocal
    from app.services.cloud_geo import fetch_cloud_places
    from app.services.cloud_parity import record, record_error

    params = {
        "bbox": bbox, "kind": ",".join(kinds) or None,
        "source": ",".join(sources) or None, "q": q,
        "has_boundary": has_boundary, "limit": limit,
    }
    try:
        answer = await asyncio.to_thread(
            fetch_cloud_places,
            bbox=bbox, kinds=kinds, sources=sources, q=q,
            has_boundary=has_boundary, limit=limit,
        )
    except Exception as exc:  # noqa: BLE001 — upstream may fail in any way
        logger.warning("cloud parity: upstream could not be read — %s", exc)
        try:
            async with AsyncSessionLocal() as session:
                await record_error(session, "geo_places", str(exc), params)
        except Exception as inner:  # noqa: BLE001
            logger.error("cloud parity: the failure could not be recorded — %s", inner)
        return

    params = {**params, "upstream_total": answer.total,
              "upstream_complete": answer.complete}
    try:
        async with AsyncSessionLocal() as session:
            await record(session, "geo_places", local, answer.rows, params,
                         local_complete=local_complete,
                         cloud_complete=answer.complete)
    except Exception as exc:  # noqa: BLE001
        logger.error("cloud parity: the comparison could not be recorded — %s", exc)


async def _cloud_concepts() -> dict:
    """The upstream's vocabulary."""
    import asyncio

    from app.services.cloud_geo import fetch_cloud_concepts

    return await asyncio.to_thread(fetch_cloud_concepts)


#: The vocabulary's fields, compared by kind. The counts are left out on
#: purpose — the mirror's copy of the feed's count is a snapshot of the last
#: sync and the upstream's is live, so they drift apart as the feed grows.
CONCEPT_FIELDS = ("name", "name_cn", "description", "description_cn", "rank")


async def _record_concepts_parity(local) -> None:
    """Compare the vocabulary with the upstream's and write it down."""
    import asyncio

    from app.core.database import AsyncSessionLocal
    from app.services.cloud_parity import compare, is_clean, record, record_error

    params = {"surface": "geo_concepts"}
    try:
        payload = await _cloud_concepts()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: the vocabulary could not be read — %s", exc)
        try:
            async with AsyncSessionLocal() as session:
                await record_error(session, "geo_concepts", str(exc), params)
        except Exception as inner:  # noqa: BLE001
            logger.error("cloud parity: the failure could not be recorded — %s", inner)
        return

    from app.services.cloud_geo import concepts_to_read

    cloud = concepts_to_read(payload)
    # The concepts have no uid; their identity is their kind.
    local_rows = [{"uid": c.get("kind"), **{f: c.get(f) for f in CONCEPT_FIELDS}}
                  for c in local]
    cloud_rows = [{"uid": c.get("kind"), **{f: c.get(f) for f in CONCEPT_FIELDS}}
                  for c in cloud]

    try:
        async with AsyncSessionLocal() as session:
            await record(session, "geo_concepts", local_rows, cloud_rows, params,
                         fields=CONCEPT_FIELDS)
    except Exception as exc:  # noqa: BLE001
        logger.error("cloud parity: the comparison could not be recorded — %s", exc)



async def _cloud_boundaries(
    bbox, kinds, sources, excluded_kinds, simplify_m, limit,
) -> dict:
    """The upstream's outlines for a viewport, in one request.

    The SDK is **synchronous**, so the call is put on a thread — this is the
    API server, and blocking the event loop on an upstream round trip would
    stall every other request the map server is serving.
    """
    import asyncio

    from app.services.cloud_geo import fetch_cloud_boundaries

    return await asyncio.to_thread(
        fetch_cloud_boundaries,
        bbox=bbox, kinds=kinds, sources=sources,
        excluded_kinds=excluded_kinds, simplify_m=simplify_m, limit=limit,
    )


async def _record_boundaries_parity(local, params) -> None:
    """Compare this app's outlines with the upstream's and write it down.

    The comparison is best-effort by design: a failure to read upstream, or
    to write the ledger, must never fail the request the user is waiting
    for. But a failure is never silent either — it is logged, and the
    comparison is recorded as a failure.
    """
    import asyncio

    from app.core.database import AsyncSessionLocal
    from app.services.cloud_geo import boundaries_to_read, fetch_cloud_boundaries
    from app.services.cloud_geo_parity import compare_boundaries
    from app.services.cloud_parity import record_error, record_result

    try:
        payload = await asyncio.to_thread(
            fetch_cloud_boundaries,
            bbox=params.get("bbox"),
            kinds=[k for k in (params.get("kind") or "").split(",") if k] or None,
            excluded_kinds=None if params.get("kind") else list(LARGE_KINDS),
            sources=[s for s in (params.get("source") or "").split(",") if s] or None,
            simplify_m=params.get("simplify_m"),
            limit=params.get("limit"),
        )
    except Exception as exc:  # noqa: BLE001 — upstream may fail in any way
        logger.warning("cloud parity: the outlines could not be read — %s", exc)
        try:
            async with AsyncSessionLocal() as session:
                await record_error(session, "geo_boundaries", str(exc), params)
        except Exception as inner:  # noqa: BLE001
            logger.error("cloud parity: the failure could not be recorded — %s", inner)
        return

    local_reads = [item.model_dump() for item in local]
    cloud = boundaries_to_read(payload)
    result = compare_boundaries(local_reads, cloud)
    try:
        async with AsyncSessionLocal() as session:
            await record_result(
                session, "geo_boundaries", result,
                local_count=len(local_reads),
                cloud_count=int(payload.get("count") or len(cloud)),
                params={**params, "upstream_total": payload.get("count")},
                complete=not payload.get("truncated"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("cloud parity: the comparison could not be recorded — %s", exc)


@router.get("/boundaries", response_model=GeoBoundaryListRead)
async def geo_boundaries(
    background_tasks: BackgroundTasks,
    bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat of the viewport"),
    kind: str | None = Query(None, description="One or more kinds, comma separated"),
    source: str | None = Query(None, description="One or more sources: osm, geoboundaries"),
    simplify_m: float | None = Query(None, ge=0, le=5000),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Every outline inside a viewport, in one response.

    The map layer needs the *shapes*, not just the names, and one request per
    place would be one request per polygon — so the outlines come back
    together, already simplified for drawing.

    Only places we actually hold an outline for are returned, and the response
    says whether it was **truncated**: the kinds are ordered smallest first,
    so a truncated answer drops the *large* areas (which are off-screen at
    street level) rather than the small ones the user is looking at — but the
    client is told, so it never silently loses a ward.

    **This route reads whereq.cloud in the ``cloud`` mode**, and compares the
    two answers in ``dual``. The upstream serves a viewport's worth of
    outlines in one request now (``GET /v1/geo/boundaries``), which is what
    the cut needed: asking it for the outlines one place at a time was N
    upstream requests for one map pan, far past the 30 requests/minute the
    API allows.

    The upstream is asked for the same set this app's own query selects — the
    same viewport, the same kinds, and the same exclusion of the country, the
    province and the state — so the two answers are like with like and the
    comparison is a comparison.
    """
    conds = [GeoPlace.geom.is_not(None)]
    bb = _parse_bbox(bbox)
    if bb:
        mnlng, mnlat, mxlng, mxlat = bb
        conds.append(func.ST_Intersects(
            GeoPlace.geom, func.ST_MakeEnvelope(mnlng, mnlat, mxlng, mxlat, 4326)))
    kinds = _csv(kind)
    if kinds:
        conds.append(GeoPlace.kind.in_(kinds))
    else:
        # No kind asked for → the drawable set (see LARGE_KINDS).
        conds.append(GeoPlace.kind.not_in(LARGE_KINDS))
    sources = _csv(source)
    if sources:
        conds.append(GeoPlace.source.in_(sources))

    metres = simplify_m if simplify_m is not None else settings.GEO_BOUNDARY_SIMPLIFY_M
    mode = _boundaries_mode()

    if mode == "cloud":
        from app.services.cloud_geo import boundaries_to_read

        payload = await _cloud_boundaries(
            bbox=bbox, kinds=kinds, sources=sources,
            excluded_kinds=None if kinds else list(LARGE_KINDS),
            simplify_m=metres, limit=limit,
        )
        items = [
            GeoBoundaryRead(**item) for item in
            boundaries_to_read(payload)
        ]
        if items:
            return GeoBoundaryListRead(
                total=int(payload.get("count") or len(items)),
                truncated=bool(payload.get("truncated")),
                items=items,
            )
        # An empty upstream answer is not an answer — it is a failure that
        # looks like an empty viewport. Logged, because a silent fallback
        # is how a cut quietly stops being a cut.
        logger.warning(
            "geo boundaries: the upstream returned no outlines — "
            "serving the local answer")

    # The count first, so the client is told when the answer is truncated.
    total = (await db.execute(
        select(func.count()).select_from(GeoPlace).where(*conds)
    )).scalar_one()

    # Ordered smallest first: when the limit truncates, the *large* areas are
    # the ones dropped — and at street level those are off-screen anyway,
    # while the wards and neighbourhoods on screen are kept.
    rows = (await db.execute(
        select(
            GeoPlace.uid, GeoPlace.name, GeoPlace.kind, GeoPlace.source,
            GeoPlace.license, GeoPlace.source_url, GeoPlace.area_km2,
            GeoPlace.centroid_lon, GeoPlace.centroid_lat,
        ).where(*conds)
        .order_by(GeoPlace.area_km2.asc().nullslast(), GeoPlace.name)
        .limit(limit)
    )).all()

    items = await _boundaries(db, rows, metres)

    if mode == "dual":
        background_tasks.add_task(
            _record_boundaries_parity, items,
            {"bbox": bbox, "kind": ",".join(kinds) or None,
             "source": ",".join(sources) or None, "simplify_m": metres,
             "limit": limit},
        )

    return GeoBoundaryListRead(
        total=total, truncated=len(items) < total, items=items,
    )


#: Whether the upstream's containment stack carries the licence.
#:
#: It does not — checked against the live upstream on 2026-11-21 — and the
#: licence is the attribution the open licences (ODbL 1.0, CC-BY 4.0) require
#: the UI to carry, so the local answer is served until it does.
#:
#: The answer is remembered, because checking it means reading the upstream,
#: and reading the upstream to throw the answer away would be a request per
#: map pan for nothing. It is re-checked once an hour, so the cut happens by
#: itself the day whereq.cloud publishes the attribution.
_AT_LICENCE_CHECKED_AT: float | None = None
_AT_HAS_LICENCE = False
_AT_LICENCE_TTL = 3600.0


async def _upstream_at_carries_the_licence() -> bool:
    """Whether whereq.cloud's containment stack publishes the licence."""
    global _AT_LICENCE_CHECKED_AT, _AT_HAS_LICENCE
    now = time.monotonic()
    if _AT_LICENCE_CHECKED_AT is not None and now - _AT_LICENCE_CHECKED_AT < _AT_LICENCE_TTL:
        return _AT_HAS_LICENCE
    try:
        payload = await _cloud_at(-79.4, 43.65)
    except Exception as exc:  # noqa: BLE001 — the upstream may fail in any way
        logger.warning("geo at: the upstream could not be checked — %s", exc)
        return _AT_HAS_LICENCE
    from app.services.cloud_geo import at_places_to_read

    places = at_places_to_read(payload)
    _AT_HAS_LICENCE = bool(places) and all(p.get("license") for p in places)
    _AT_LICENCE_CHECKED_AT = now
    return _AT_HAS_LICENCE


@router.get("/at", response_model=GeoAtResponse)
async def geo_at(
    background_tasks: BackgroundTasks,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    """Everything that contains this point — broadest first.

    In ``cloud`` mode the answer is the **upstream's** containment stack; the
    local mirror is only read when the upstream cannot be. In ``dual`` mode
    the two are compared and the local one is served.

    ``ST_Covers`` rather than ``ST_Contains``: a point exactly *on* an edge
    belongs to that edge's polygon, and a point on a shared boundary between
    two wards belongs to both. The upstream uses the same predicate, so the
    two answers are comparable.

    **This route used to be blocked on one thing**: the upstream's
    ``/v1/geo/at`` did not publish the licence, and the licence is the
    attribution the open licences (ODbL 1.0, CC-BY 4.0) require the UI to
    carry. Serving the upstream's stack as it stood would have dropped that
    attribution from the map's place cards.

    So the route **checks**: the upstream's answer is served when it carries
    the licence, and the local one is served when it does not. That way the
    cut happens by itself the day whereq.cloud publishes the attribution —
    there is no flag to remember to flip.

    **It has.** The upstream publishes the licence now — one column in
    ``data_api/routers/geo_places.py`` and one field in the SDK's
    ``GeoAtPlace`` type — so the upstream's stack is what this route serves,
    and the licence is on every row of it.
    """
    mode = _mode()
    if mode == "cloud":
        from app.services.cloud_geo import at_places_to_read

        if await _upstream_at_carries_the_licence():
            payload = await _cloud_at(lng, lat)
            upstream = at_places_to_read(payload)
            if upstream:
                return GeoAtResponse(
                    lat=lat, lng=lng,
                    places=[GeoAtRead(**p) for p in upstream],
                )
        # The upstream does not carry the attribution yet, so the local
        # answer is the one that keeps it. Logged, because a silent
        # fallback is how a cut quietly stops being a cut.
        logger.info(
            "geo at: the upstream does not publish the licence — "
            "serving the local answer (the attribution the open licences "
            "require)")

    pt = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    rows = (await db.execute(
        select(GeoPlace.uid, GeoPlace.kind, GeoPlace.name, GeoPlace.source,
               GeoPlace.license, GeoPlace.centroid_lon, GeoPlace.centroid_lat,
               GeoConcept.rank)
        .outerjoin(GeoConcept, GeoConcept.kind == GeoPlace.kind)
        .where(func.ST_Covers(GeoPlace.geom, pt))
        .order_by(func.coalesce(GeoConcept.rank, 100), GeoPlace.name)
    )).all()
    local = [dict(uid=r[0], kind=r[1], name=r[2], source=r[3], license=r[4],
                  centroid_lon=r[5], centroid_lat=r[6]) for r in rows]

    if mode == "dual":
        background_tasks.add_task(_record_at_parity, local, lat, lng)

    return GeoAtResponse(lat=lat, lng=lng, places=[GeoAtRead(**p) for p in local])


async def _cloud_at(lng: float, lat: float) -> dict:
    """The upstream's containment stack."""
    import asyncio

    from app.services.cloud_geo import fetch_cloud_at

    return await asyncio.to_thread(fetch_cloud_at, lon=lng, lat=lat)


#: The containment stack's comparable fields.
#:
#: The **licence is one of them.** It used not to be: the upstream's
#: ``/v1/geo/at`` did not publish it while this app's local answer did, and
#: comparing a field the upstream does not publish against one it does would
#: report a difference on every row of every stack, forever, and it would be
#: telling the truth about nothing.
#:
#: The upstream publishes it now — one column in
#: ``data_api/routers/geo_places.py`` and one field in the SDK's
#: ``GeoAtPlace`` type — so the attribution is compared like any other
#: field. A difference there is not a formality: it means one side cannot
#: be attributed, which is the one thing the open licences require.
AT_FIELDS = ("kind", "name", "source", "license", "centroid_lon", "centroid_lat")


async def _record_at_parity(local, lat: float, lng: float) -> None:
    """Compare the containment stack with the upstream's and write it down."""
    from app.core.database import AsyncSessionLocal
    from app.services.cloud_parity import record, record_error

    params = {"lat": lat, "lng": lng}
    try:
        payload = await _cloud_at(lng, lat)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: the containment stack could not be read — %s", exc)
        try:
            async with AsyncSessionLocal() as session:
                await record_error(session, "geo_at", str(exc), params)
        except Exception as inner:  # noqa: BLE001
            logger.error("cloud parity: the failure could not be recorded — %s", inner)
        return

    from app.services.cloud_geo import at_places_to_read

    cloud = at_places_to_read(payload)
    try:
        async with AsyncSessionLocal() as session:
            # Both sides are whole: neither the local query nor the upstream
            # answer has a limit, so both populations are complete.
            await record(session, "geo_at", local, cloud, params, fields=AT_FIELDS)
    except Exception as exc:  # noqa: BLE001
        logger.error("cloud parity: the comparison could not be recorded — %s", exc)


@router.get("/places/{uid}", response_model=GeoPlaceDetail)
async def geo_place(
    uid: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """One administrative place, in full.

    The columns are listed one by one rather than selecting the entity: the
    entity carries the full-resolution outline, and this endpoint does not
    return it.

    The three read modes apply: ``dual`` compares the local row with the
    upstream's and serves the local one; ``cloud`` serves the upstream's.
    A place the upstream does not have is a real difference, not an error —
    the mirror has something the original lost.
    """
    mode = _mode()
    if mode == "cloud":
        place = await _cloud_place(uid)
        if place is None:
            raise HTTPException(status_code=404, detail="Geo place not found")
        return GeoPlaceDetail(**place)

    row = (await db.execute(
        select(
            GeoPlace.uid, GeoPlace.kind, GeoPlace.name, GeoPlace.name_en,
            GeoPlace.name_zh, GeoPlace.name_local, GeoPlace.official_name,
            GeoPlace.source, GeoPlace.source_url, GeoPlace.license,
            GeoPlace.country_code, GeoPlace.province_code, GeoPlace.population,
            GeoPlace.area_km2, GeoPlace.centroid_lon, GeoPlace.centroid_lat,
            GeoPlace.geom.is_not(None).label("has_boundary"),
            GeoPlace.kind_source, GeoPlace.source_id, GeoPlace.raw_admin_level,
            GeoPlace.raw_place, GeoPlace.raw_boundary, GeoPlace.iso_code,
            GeoPlace.ref, GeoPlace.population_date, GeoPlace.wikidata,
            GeoPlace.wikipedia, GeoPlace.website, GeoPlace.capital,
            GeoPlace.bbox_min_lon, GeoPlace.bbox_min_lat,
            GeoPlace.bbox_max_lon, GeoPlace.bbox_max_lat,
        ).where(GeoPlace.uid == uid)
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Geo place not found")
    local = dict(
        uid=row[0], kind=row[1], name=row[2], name_en=row[3], name_zh=row[4],
        name_local=row[5], official_name=row[6], source=row[7], source_url=row[8],
        license=row[9], country_code=row[10], province_code=row[11],
        population=row[12], area_km2=row[13], centroid_lon=row[14],
        centroid_lat=row[15], has_boundary=bool(row[16]),
        kind_source=row[17], source_id=row[18], raw_admin_level=row[19],
        raw_place=row[20], raw_boundary=row[21], iso_code=row[22], ref=row[23],
        population_date=row[24], wikidata=row[25], wikipedia=row[26],
        website=row[27], capital=row[28],
        bbox_min_lon=row[29], bbox_min_lat=row[30],
        bbox_max_lon=row[31], bbox_max_lat=row[32],
    )

    if mode == "dual":
        background_tasks.add_task(_record_place_parity, local, uid)

    return GeoPlaceDetail(**local)


async def _cloud_place(uid: str) -> dict | None:
    """One place from upstream. ``None`` means upstream does not have it."""
    import asyncio

    from app.services.cloud_geo import fetch_cloud_place

    return await asyncio.to_thread(fetch_cloud_place, uid=uid)


async def _record_place_parity(local: dict, uid: str) -> None:
    """Compare one place with the upstream's and write the comparison down."""
    from app.core.database import AsyncSessionLocal
    from app.services.cloud_parity import DETAIL_FIELDS, COMPARABLE_FIELDS
    from app.services.cloud_parity import record, record_error

    params = {"uid": uid}
    try:
        cloud = await _cloud_place(uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: the place could not be read — %s", exc)
        try:
            async with AsyncSessionLocal() as session:
                await record_error(session, "geo_place", str(exc), params)
        except Exception as inner:  # noqa: BLE001
            logger.error("cloud parity: the failure could not be recorded — %s", inner)
        return

    try:
        async with AsyncSessionLocal() as session:
            # An upstream that does not have the place is not an error — it
            # is the mirror holding something the original lost, which is
            # exactly what "only_local" means.
            await record(session, "geo_place", [local],
                         [cloud] if cloud else [], params,
                         fields=tuple(COMPARABLE_FIELDS) + tuple(DETAIL_FIELDS))
    except Exception as exc:  # noqa: BLE001
        logger.error("cloud parity: the comparison could not be recorded — %s", exc)


@router.get("/places/{uid}/boundary", response_model=GeoBoundaryRead)
async def geo_boundary(
    uid: str,
    background_tasks: BackgroundTasks,
    simplify_m: float | None = Query(None, ge=0, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """One place's outline, as GeoJSON.

    The stored outline is **full resolution** — the point-in-polygon test must
    not be fooled by a simplified edge — and it is simplified here, on the way
    out, to whatever the caller asks for (default: the server's configured
    ``GEO_BOUNDARY_SIMPLIFY_M``). A polygon with 40 000 points is not
    something a browser should download to draw a neighbourhood outline.

    The three read modes apply: ``dual`` compares the local outline with the
    upstream's and serves the local one; ``cloud`` serves the upstream's.
    The comparison is between the two **full-resolution** outlines — a
    simplified shape would differ from a full one for reasons that have
    nothing to do with the data.
    """
    mode = _mode()
    if mode == "cloud":
        cloud = await _cloud_boundary(uid)
        if cloud is None:
            raise HTTPException(status_code=404, detail="Geo place has no boundary")
        return cloud

    row = (await db.execute(
        select(
            GeoPlace.uid, GeoPlace.name, GeoPlace.kind, GeoPlace.source,
            GeoPlace.license, GeoPlace.source_url, GeoPlace.area_km2,
            GeoPlace.centroid_lon, GeoPlace.centroid_lat,
            GeoPlace.boundary_geojson,
        ).where(GeoPlace.uid == uid, GeoPlace.geom.is_not(None))
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Geo place has no boundary")

    metres = simplify_m if simplify_m is not None else settings.GEO_BOUNDARY_SIMPLIFY_M
    out = await _boundaries(db, [row], metres)
    if not out:
        raise HTTPException(status_code=404, detail="Geo place has no boundary")

    if mode == "dual":
        background_tasks.add_task(
            _record_boundary_parity,
            dict(uid=row[0], name=row[1], kind=row[2], source=row[3],
                 license=row[4], source_url=row[5], area_km2=row[6],
                 centroid_lon=row[7], centroid_lat=row[8],
                 geometry=row[9]),
            uid,
        )

    return out[0]


async def _cloud_boundary_payload(uid: str) -> dict | None:
    """The upstream's outline for a place, at full resolution.

    ``None`` means upstream has no outline for this place.
    """
    import asyncio

    from app.services.cloud_geo import fetch_cloud_boundary

    return await asyncio.to_thread(fetch_cloud_boundary, uid=uid)


async def _cloud_boundary(uid: str) -> GeoBoundaryRead | None:
    """One place's outline from upstream, in this app's response shape.

    The upstream's boundary payload carries the outline and the place's
    attributes, but not the place's centroid — so the place is fetched as
    well, and the outline is served with the centroid the feed itself
    reports. Without it the map would place the place at the null island.
    """
    import asyncio

    from app.services.cloud_geo import fetch_cloud_place

    payload = await _cloud_boundary_payload(uid)
    if payload is None:
        return None
    properties = payload.get("properties") or {}

    centroid_lon = centroid_lat = None
    place = await asyncio.to_thread(fetch_cloud_place, uid=uid)
    if place:
        centroid_lon = place.get("centroid_lon")
        centroid_lat = place.get("centroid_lat")

    return GeoBoundaryRead(
        uid=properties.get("uid") or uid,
        name=properties.get("name") or "",
        kind=properties.get("kind") or "",
        source=properties.get("source") or "",
        license=properties.get("license"),
        source_url=None,
        geometry=payload.get("geometry") or {},
        simplified_m=0.0,
        area_km2=properties.get("area_km2"),
        centroid_lon=centroid_lon,
        centroid_lat=centroid_lat,
    )


async def _record_boundary_parity(local: dict, uid: str) -> None:
    """Compare the local outline with the upstream's and write it down."""
    from app.core.database import AsyncSessionLocal
    from app.services.cloud_parity import compare_boundary, record_error, record_result

    params = {"uid": uid}
    try:
        cloud = await _cloud_boundary_payload(uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: the outline could not be read — %s", exc)
        try:
            async with AsyncSessionLocal() as session:
                await record_error(session, "geo_boundary", str(exc), params)
        except Exception as inner:  # noqa: BLE001
            logger.error("cloud parity: the failure could not be recorded — %s", inner)
        return

    if cloud is None:
        # The mirror holds an outline the upstream does not have. That is a
        # real difference, not an error.
        result = {"only_local": [uid], "only_cloud": [], "differing": {}}
    else:
        result = compare_boundary(local, cloud)

    try:
        async with AsyncSessionLocal() as session:
            await record_result(session, "geo_boundary", result,
                                local_count=1, cloud_count=1 if cloud else 0,
                                params=params)
    except Exception as exc:  # noqa: BLE001
        logger.error("cloud parity: the comparison could not be recorded — %s", exc)


#: The columns a boundary response needs. Selecting the whole entity would
#: pull the full-resolution outline (JSONB) *and* the PostGIS geometry (as
#: EWKB) into memory — megabytes per request for rows the response does not
#: carry.
PLACE_COLUMNS = (
    GeoPlace.uid, GeoPlace.name, GeoPlace.kind, GeoPlace.source,
    GeoPlace.license, GeoPlace.source_url, GeoPlace.area_km2,
    GeoPlace.centroid_lon, GeoPlace.centroid_lat,
)


async def _boundaries(
    db: AsyncSession, places: list, metres: float
) -> list[GeoBoundaryRead]:
    """The outlines of the given places, simplified, in **one** query.

    ``places`` are the column tuples of :data:`PLACE_COLUMNS` — never the
    entities, which would carry the full-resolution outline into memory.

    ``ST_SimplifyPreserveTopology`` keeps the result a valid polygon (no
    self-intersecting rings), and the result is coerced back to a MultiPolygon
    because that is what the column is.

    The simplification tolerance is derived from **each place's own latitude**,
    not from a summary of the batch: an outline's shape then does not depend on
    which other outlines happen to be in the same answer, so one place is the
    same shape whether it is drawn alone or in a viewport of three hundred —
    and the upstream's outlines are directly comparable with these ones.
    """
    if not places:
        return []
    simplified = (func.ST_SimplifyPreserveTopology(
        GeoPlace.geom, _tolerance_expression(metres)) if metres > 0 else GeoPlace.geom)
    rows = (await db.execute(
        select(*PLACE_COLUMNS,
               func.ST_AsGeoJSON(func.ST_Multi(func.ST_CollectionExtract(simplified, 3)), 6))
        .where(GeoPlace.uid.in_([p[0] for p in places]))
    )).all()
    by_uid = {r[0]: r for r in rows}

    out: list[GeoBoundaryRead] = []
    for place in places:
        row = by_uid.get(place[0])
        if not row or not row[9]:
            continue
        out.append(GeoBoundaryRead(
            uid=row[0], name=row[1], kind=row[2], source=row[3],
            license=row[4], source_url=row[5],
            geometry=json.loads(row[9]), simplified_m=metres, area_km2=row[6],
            centroid_lon=row[7], centroid_lat=row[8],
        ))
    return out
