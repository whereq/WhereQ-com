"""Administrative geography — the areas that contain the places.

The whereq.cloud geography feed: provinces, regions, municipalities, cities,
towns, wards and neighbourhoods, with real outlines. This router serves the
rows already crawled from the feed, so it never spends upstream quota and the
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
import math

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.crawler.upstream.geo_places import concepts_with_counts

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


def _simplify_tolerance_degrees(metres: float, lat: float | None) -> float:
    """The tolerance ``ST_Simplify`` wants, in degrees, for a given error in metres.

    PostGIS 3.7 has **no geography overload** of ``ST_Simplify`` — it works on
    geometry, whose unit here is a degree. A degree is not a fixed length: a
    degree of longitude is ~111 km at the equator and ~80 km at Toronto.

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
    m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    m_per_deg_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
    # At the poles a degree of longitude collapses; fall back to the latitude
    # scale rather than dividing by ~0.
    m_per_deg_lon = max(m_per_deg_lon, 1.0)
    per_degree = max(m_per_deg_lat, m_per_deg_lon)
    return metres / per_degree


@router.get("/concepts", response_model=list[GeoConceptRead])
async def geo_concepts(db: AsyncSession = Depends(get_db)):
    """The vocabulary — every kind of administrative place, with our counts.

    ``places`` is how many *we* hold (the ones the app can draw);
    ``upstream_places`` is the feed's own count for the whole dataset.
    """
    return await concepts_with_counts(db)


@router.get("/places", response_model=list[GeoPlaceRead])
async def geo_places(
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
    return [GeoPlaceRead(
        uid=r[0], kind=r[1], name=r[2], name_en=r[3], name_zh=r[4],
        name_local=r[5], official_name=r[6], source=r[7], source_url=r[8],
        license=r[9], country_code=r[10], province_code=r[11], population=r[12],
        area_km2=r[13], centroid_lon=r[14], centroid_lat=r[15],
        has_boundary=bool(r[16]),
    ) for r in rows]


@router.get("/boundaries", response_model=GeoBoundaryListRead)
async def geo_boundaries(
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

    metres = simplify_m if simplify_m is not None else settings.GEO_BOUNDARY_SIMPLIFY_M
    items = await _boundaries(db, rows, metres)
    return GeoBoundaryListRead(
        total=total, truncated=len(items) < total, items=items,
    )


@router.get("/at", response_model=GeoAtResponse)
async def geo_at(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    """Everything that contains this point — broadest first.

    The answer is computed locally with PostGIS (``ST_Covers``), not by asking
    the upstream API per request: the polygons are already here, and the
    upstream call would cost a request for every pan of the map.

    ``ST_Covers`` rather than ``ST_Contains``: a point exactly *on* an edge
    belongs to that edge's polygon, and a point on a shared boundary between
    two wards belongs to both.
    """
    pt = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    rows = (await db.execute(
        select(GeoPlace.uid, GeoPlace.kind, GeoPlace.name, GeoPlace.source,
               GeoPlace.license, GeoPlace.centroid_lon, GeoPlace.centroid_lat,
               GeoConcept.rank)
        .outerjoin(GeoConcept, GeoConcept.kind == GeoPlace.kind)
        .where(func.ST_Covers(GeoPlace.geom, pt))
        .order_by(func.coalesce(GeoConcept.rank, 100), GeoPlace.name)
    )).all()
    return GeoAtResponse(
        lat=lat, lng=lng,
        places=[GeoAtRead(uid=r[0], kind=r[1], name=r[2], source=r[3], license=r[4],
                          centroid_lon=r[5], centroid_lat=r[6]) for r in rows],
    )


@router.get("/places/{uid}", response_model=GeoPlaceDetail)
async def geo_place(uid: str, db: AsyncSession = Depends(get_db)):
    """One administrative place, in full.

    The columns are listed one by one rather than selecting the entity: the
    entity carries the full-resolution outline, and this endpoint does not
    return it.
    """
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
    return GeoPlaceDetail(
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


@router.get("/places/{uid}/boundary", response_model=GeoBoundaryRead)
async def geo_boundary(
    uid: str,
    simplify_m: float | None = Query(None, ge=0, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """One place's outline, as GeoJSON.

    The stored outline is **full resolution** — the point-in-polygon test must
    not be fooled by a simplified edge — and it is simplified here, on the way
    out, to whatever the caller asks for (default: the server's configured
    ``GEO_BOUNDARY_SIMPLIFY_M``). A polygon with 40 000 points is not
    something a browser should download to draw a neighbourhood outline.
    """
    row = (await db.execute(
        select(
            GeoPlace.uid, GeoPlace.name, GeoPlace.kind, GeoPlace.source,
            GeoPlace.license, GeoPlace.source_url, GeoPlace.area_km2,
            GeoPlace.centroid_lon, GeoPlace.centroid_lat,
        ).where(GeoPlace.uid == uid, GeoPlace.geom.is_not(None))
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Geo place has no boundary")

    metres = simplify_m if simplify_m is not None else settings.GEO_BOUNDARY_SIMPLIFY_M
    out = await _boundaries(db, [row], metres)
    if not out:
        raise HTTPException(status_code=404, detail="Geo place has no boundary")
    return out[0]


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

    The simplification tolerance is derived from a single latitude for the
    whole batch — the places of one viewport sit within a few tenths of a
    degree of each other, so the error is under a percent, and it keeps the
    whole layer to one round trip.
    """
    if not places:
        return []
    lats = [p[8] for p in places if p[8] is not None]
    tolerance = _simplify_tolerance_degrees(metres, sum(lats) / len(lats) if lats else 0.0)

    simplified = func.ST_SimplifyPreserveTopology(GeoPlace.geom, tolerance) if tolerance > 0 \
        else GeoPlace.geom
    rows = (await db.execute(
        select(*PLACE_COLUMNS,
               func.ST_AsGeoJSON(func.ST_Multi(simplified), 6))
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
