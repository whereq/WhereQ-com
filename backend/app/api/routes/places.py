from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_place_write_access
from app.core.security import Principal, get_optional_user, get_principal
from app.models.place import Place
from app.models.user import User
from app.schemas.place import PlaceCreate, PlacePin, PlaceRead, PlaceUpdate
from app.services.place_dedup import shadowed_stations
from app.services.place_taxonomy import expand_categories

router = APIRouter(prefix="/places", tags=["places"])

# ---------------------------------------------------------------------------
# Fuel categories
#
# whereq.cloud stations are stored under their own category ('gas') and source
# ('whereq_cloud') so they stay distinguishable from the generic OSM fuel POIs
# — the same physical station is often present in both feeds.
#
# The map exposes a single "Fuel" category: it serves the priced whereq.cloud
# rows *and* the OSM ones, and a station that exists in both is only shown
# once (the whereq.cloud row wins — it carries the live price and the brand).
#
# The vocabulary itself lives in app.services.place_taxonomy (shared with the
# nearby search) and the de-duplication in app.services.place_dedup.
# ---------------------------------------------------------------------------

#: Metadata keys that carry the live fuel price payload (whereq.cloud).
PRICE_META_KEYS = ("prices", "observed_at")


def _parse_bbox(bbox: str | None):
    """bbox = 'minLng,minLat,maxLng,maxLat' → tuple or None."""
    if not bbox:
        return None
    try:
        a, b, c, d = (float(x) for x in bbox.split(","))
        return a, b, c, d
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'")


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def _without_prices(meta: dict | None) -> dict | None:
    """Strip the live price payload out of a metadata blob."""
    if not isinstance(meta, dict) or not any(k in meta for k in PRICE_META_KEYS):
        return meta
    return {k: v for k, v in meta.items() if k not in PRICE_META_KEYS}


def _read(place: Place, *, include_prices: bool) -> PlaceRead:
    """Serialise a place, dropping the fuel prices for anonymous callers.

    The prices come from whereq.cloud (metered, licensed) and are served to
    signed-in users only; the station itself stays visible to everyone.
    """
    data = PlaceRead.model_validate(place)
    if not include_prices:
        data.metadata_json = _without_prices(data.metadata_json)
    return data


@router.get("", response_model=list[PlaceRead])
async def list_places(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Place)
    if category:
        q = q.where(Place.category == category)
    if kind:
        q = q.where(Place.kind == kind)
    if search:
        q = q.where(Place.name.ilike(f"%{search}%"))
    q = q.offset(skip).limit(limit).order_by(Place.view_count.desc())
    result = await db.execute(q)
    priced = user is not None
    return [_read(p, include_prices=priced) for p in result.scalars().all()]


@router.get("/nearby", response_model=list[PlaceRead])
async def list_nearby_places(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_km: float = Query(5.0, ge=0.1, le=50),
    kind: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Return places within radius_km of (lat, lng) using bounding-box approximation."""
    # ~0.009 degrees per km at mid-latitudes
    delta_lat = radius_km * 0.009
    delta_lng = radius_km * 0.009 / max(0.1, abs(__import__("math").cos(__import__("math").radians(lat))))

    q = select(Place).where(
        Place.latitude.between(lat - delta_lat, lat + delta_lat),
        Place.longitude.between(lng - delta_lng, lng + delta_lng),
    )
    if kind:
        q = q.where(Place.kind == kind)
    q = q.limit(limit)
    result = await db.execute(q)
    priced = user is not None
    return [_read(p, include_prices=priced) for p in result.scalars().all()]


def _poi_condition(cats: list[str], cuisines: list[str]):
    """POI rows matching the requested categories. When 'food' is requested with
    cuisines, food is restricted to those cuisines (matched against `sub`, which
    holds the OSM cuisine tag, e.g. 'italian;pizza'); other categories are not."""
    cats = expand_categories(cats)
    if "food" in cats and cuisines:
        food = and_(Place.category == "food",
                    or_(*[Place.sub.ilike(f"%{c}%") for c in cuisines]))
        others = [c for c in cats if c != "food"]
        cat_cond = or_(food, Place.category.in_(others)) if others else food
    else:
        cat_cond = Place.category.in_(cats)
    return and_(Place.kind == "poi", cat_cond)


def _shadowed_stations(envelope=None):
    """Ids of the OSM fuel POIs that a whereq.cloud station already covers.

    OSM and whereq.cloud both carry the same physical stations, ~100 m apart;
    showing both would double every station on the map. The priced whereq.cloud
    row wins, so the OSM row is dropped.

    The implementation lives in app.services.place_dedup — the nearby search
    filters the same stations.
    """
    return shadowed_stations(envelope)


@router.get("/map", response_model=list[PlacePin])
async def places_map(
    bbox: str | None = None,
    kinds: str | None = Query(None, description="CSV of kinds, e.g. school,pharmacy,library"),
    categories: str | None = Query(None, description="CSV of POI categories, e.g. food,coffee"),
    cuisines: str | None = Query(None, description="CSV of food cuisines, e.g. chinese,italian"),
    limit: int = Query(2000, ge=1, le=8000),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight pins inside the viewport, filtered by kind and/or POI category
    (and, for food, optional cuisine)."""
    conds = []
    bb = _parse_bbox(bbox)
    envelope = None
    if bb:
        mnlng, mnlat, mxlng, mxlat = bb
        envelope = func.ST_MakeEnvelope(mnlng, mnlat, mxlng, mxlat, 4326)
        conds.append(func.ST_Intersects(Place.geom, envelope))

    kind_list, cat_list, cuisine_list = _csv(kinds), _csv(categories), _csv(cuisines)
    clauses = []
    if kind_list:
        clauses.append(and_(Place.kind.in_(kind_list), Place.kind != "poi"))
    if cat_list:
        clauses.append(_poi_condition(cat_list, cuisine_list))
    if clauses:
        conds.append(or_(*clauses) if len(clauses) > 1 else clauses[0])

    stmt = select(Place.id, Place.name, Place.latitude, Place.longitude, Place.kind,
                  Place.category, Place.sub).where(*conds)
    # "fuel" also serves the priced whereq.cloud stations — drop the OSM row of
    # any station that whereq.cloud already covers, so it is shown once.
    if "fuel" in expand_categories(cat_list):
        stmt = stmt.where(Place.id.not_in(_shadowed_stations(envelope)))
    rows = (await db.execute(stmt.limit(limit))).all()
    return [PlacePin(id=r[0], name=r[1], lat=r[2], lng=r[3], kind=r[4], category=r[5], sub=r[6])
            for r in rows]


@router.get("/counts")
async def places_counts(bbox: str | None = None, db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    """Counts within the viewport by kind, plus `cat:<category>` for POIs —
    matches the shape the sidebar consumes (essentials + quick categories)."""
    conds = []
    bb = _parse_bbox(bbox)
    if bb:
        mnlng, mnlat, mxlng, mxlat = bb
        conds.append(func.ST_Intersects(
            Place.geom, func.ST_MakeEnvelope(mnlng, mnlat, mxlng, mxlat, 4326)))

    counts: dict[str, int] = {}
    for kind, n in (await db.execute(
            select(Place.kind, func.count()).where(*conds).group_by(Place.kind))).all():
        counts[kind] = n
    for cat, n in (await db.execute(
            select(Place.category, func.count())
            .where(*conds, Place.kind == "poi").group_by(Place.category))).all():
        counts[f"cat:{cat}"] = n
    return counts


@router.get("/{place_id}", response_model=PlaceRead)
async def get_place(
    place_id: int,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    place = await db.get(Place, place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    place.view_count += 1
    await db.commit()
    await db.refresh(place)
    return _read(place, include_prices=user is not None)


@router.post("", response_model=PlaceRead, status_code=201)
async def create_place(
    data: PlaceCreate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    """Create a place. The creator becomes its owner — only they (or staff)
    may edit or delete it afterwards."""
    place = Place(**data.model_dump())
    place.user_id = principal.id
    # A user-created place is never a pipeline-managed row: `source` drives
    # the ownership rules and the crawlers key their own rows on
    # (source, external_id).
    place.source = "manual"
    place.geom = func.ST_SetSRID(func.ST_MakePoint(data.longitude, data.latitude), 4326)
    db.add(place)
    await db.commit()
    await db.refresh(place)
    return place


@router.patch("/{place_id}", response_model=PlaceRead)
async def update_place(
    place_id: int,
    data: PlaceUpdate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    place = await db.get(Place, place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    require_place_write_access(principal, place)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(place, field, value)
    await db.commit()
    await db.refresh(place)
    return place


@router.delete("/{place_id}", status_code=204)
async def delete_place(
    place_id: int,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    place = await db.get(Place, place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    require_place_write_access(principal, place)
    await db.delete(place)
    await db.commit()
