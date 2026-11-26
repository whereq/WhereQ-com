import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import require_place_write_access
from app.core.security import Principal, get_optional_user, get_principal
from app.models.place import Place
from app.models.user import User
from app.schemas.place import PlaceCreate, PlacePin, PlaceRead, PlaceUpdate
from app.services.cloud_fuel import station_external_id
from app.services.fuel_stations import (
    CURRENCY_BY_COUNTRY,
    FUEL_CATEGORY,
    FUEL_SOURCE,
    UNIT_BY_COUNTRY,
)
from app.services.place_dedup import shadowed_by_stations, shadowed_stations
from app.services.place_taxonomy import expand_categories

logger = logging.getLogger(__name__)

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

#: Metadata keys that carry the **upstream provenance** — which feed the row
#: came from, and that feed's own id for the station. It is our supply chain,
#: not the place: no client reads either key, and the station's identity is
#: already public in the `id` field (a live station's id is the negative of
#: the upstream's). So an anonymous caller gets neither.
PROVENANCE_META_KEYS = ("data_source", "station_id")

#: What an **anonymous** caller may see of a fuel station: the place's own
#: facts. The prices are licensed and need a session; the provenance is ours.
PUBLIC_STATION_META_KEYS = (
    "brand", "state", "state_iso", "municipality", "currency", "unit",
)


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
    """Strip the licensed price payload and the upstream provenance.

    The prices come from whereq.cloud (metered, licensed) and are served to
    signed-in users only. The provenance — which upstream feed supplied the row
    and what that feed calls the station — is our supply chain, and no client
    reads it, so it goes out to an anonymous caller neither.

    This is the **stored**-row path, where the blob may also hold ordinary OSM
    tags (operator, cuisine, website…), so the two licensed/provenance keys
    are removed rather than the whole shape rebuilt. The live-station path
    builds its own dict and uses :data:`PUBLIC_STATION_META_KEYS` instead.
    """
    if not isinstance(meta, dict):
        return meta
    hidden = PRICE_META_KEYS + PROVENANCE_META_KEYS
    if not any(k in meta for k in hidden):
        return meta
    return {k: v for k, v in meta.items() if k not in hidden}


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
    (and, for food, optional cuisine).

    **The fuel pins may come from whereq.cloud.** When the fuel category is on
    and ``FUEL_READ_MODE`` is ``cloud``, the priced stations are read from the
    platform live and merged into the answer — the local mirror is not read
    for them at all. A live station's pin id is the **negative** of the
    upstream's station id, unless the user has saved that station, in which
    case it is the id of the row whereq.com keeps for it.
    """
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

    live_pins: list[PlacePin] = []
    live_points: list[tuple[float, float]] = []
    if _live_fuel() and "fuel" in expand_categories(cat_list):
        # The priced stations are read from whereq.cloud, so the mirrored rows
        # are not read at all.
        stmt = stmt.where(Place.source != FUEL_SOURCE)
        live_pins, live_points = await _live_fuel_pins(db, bbox=bbox, limit=limit)

    if "fuel" in expand_categories(cat_list):
        if live_points:
            # The live stations shadow the OSM rows they cover, so a station
            # is shown once — the priced one wins.
            shadowed = await shadowed_by_stations(db, live_points)
            if shadowed:
                stmt = stmt.where(Place.id.not_in(shadowed))
        else:
            # "fuel" also serves the priced whereq.cloud stations — drop the
            # OSM row of any station that whereq.cloud already covers, so it
            # is shown once.
            stmt = stmt.where(Place.id.not_in(_shadowed_stations(envelope)))

    rows = (await db.execute(stmt.limit(max(0, limit - len(live_pins))))).all()
    pins = [PlacePin(id=r[0], name=r[1], lat=r[2], lng=r[3], kind=r[4], category=r[5], sub=r[6])
            for r in rows]
    # The live pins are counted against the limit too: the answer is at most
    # `limit` pins, and the room the fuel stations take is the room the local
    # rows give up.
    return pins + live_pins


def _live_fuel() -> bool:
    """Whether the fuel stations are read from whereq.cloud rather than here."""
    return (settings.FUEL_READ_MODE or "local").strip().lower() == "cloud"


async def _live_fuel_pins(db: AsyncSession, *, bbox: str | None,
                          limit: int) -> tuple[list[PlacePin], list[tuple[float, float]]]:
    """The priced stations of a viewport, read from whereq.cloud, as map pins.

    The upstream answers a viewport in pages of 500 and reports how many
    stations there are in total, so the pages are read until the viewport's
    stations are in hand — a viewport holding more than one page used to be
    cut at 500, and half of Toronto's stations never reached the map.

    The **pin id** is the negative of the upstream's station id — the local
    place ids are positive, so the two spaces cannot collide, and a card can
    tell a live station from a stored place by the sign. A station the user
    has saved is the exception: whereq.com keeps a row for it, and the pin
    carries that row's id, so the saved state and the map agree.

    Returns the pins and the station positions, so the caller can drop the
    OSM rows the stations shadow.
    """
    import asyncio

    from app.services.cloud_fuel import fetch_stations_paged, materialised_ids

    try:
        payload = await asyncio.to_thread(
            fetch_stations_paged, bbox=bbox, max_rows=limit)
    except Exception as exc:  # noqa: BLE001 — the upstream may fail in any way
        logger.warning("cloud fuel: the map stations could not be read — %s", exc)
        return [], []

    stations = payload.get("stations") or []
    if not stations:
        return [], []

    saved = await materialised_ids(db, stations)

    pins: list[PlacePin] = []
    points: list[tuple[float, float]] = []
    for station in stations:
        ext = station_external_id(station)
        lat, lng = station.get("lat"), station.get("lon")
        if lat is None or lng is None:
            continue
        points.append((lng, lat))
        # The live pin id is the negative of the upstream's station id. A
        # station without an id would land on 0 — a *local* place id — so it
        # is pushed to -1 and stays on the live side of the sign.
        live_id = -abs(int(station.get("id") or 0)) or -1
        pins.append(PlacePin(
            id=saved.get(ext, live_id),
            name=(station.get("name") or station.get("brand") or "Fuel station")[:255],
            lat=lat, lng=lng,
            kind="poi", category=FUEL_CATEGORY, sub=station.get("brand"),
        ))
    return pins[:limit], points


@router.get("/counts")
async def places_counts(bbox: str | None = None, db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    """Counts within the viewport by kind, plus `cat:<category>` for POIs —
    matches the shape the sidebar consumes (essentials + quick categories).

    **The fuel count may come from whereq.cloud.** When the stations are read
    live, the upstream reports the number of stations in the viewport, and the
    mirrored rows are not counted at all.
    """
    conds = []
    bb = _parse_bbox(bbox)
    if bb:
        mnlng, mnlat, mxlng, mxlat = bb
        conds.append(func.ST_Intersects(
            Place.geom, func.ST_MakeEnvelope(mnlng, mnlat, mxlng, mxlat, 4326)))

    if _live_fuel():
        # The mirrored stations are not part of the local answer any more.
        conds.append(Place.source != FUEL_SOURCE)

    counts: dict[str, int] = {}
    for kind, n in (await db.execute(
            select(Place.kind, func.count()).where(*conds).group_by(Place.kind))).all():
        counts[kind] = n
    for cat, n in (await db.execute(
            select(Place.category, func.count())
            .where(*conds, Place.kind == "poi").group_by(Place.category))).all():
        counts[f"cat:{cat}"] = n

    if _live_fuel() and bbox:
        live = await _live_fuel_count(bbox)
        if live is not None:
            # The priced stations are the `gas` bucket; `cat:fuel` keeps
            # counting the generic OSM fuel POIs, exactly as it did before.
            counts["cat:gas"] = live
    return counts


async def _live_fuel_count(bbox: str) -> int | None:
    """How many priced stations whereq.cloud holds for this viewport.

    The upstream reports the total with the page, so one request is enough —
    and the page itself is not read.
    """
    import asyncio

    from app.services.cloud_fuel import fetch_stations

    try:
        payload = await asyncio.to_thread(fetch_stations, bbox=bbox, limit=1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud fuel: the station count could not be read — %s", exc)
        return None
    total = payload.get("total")
    return int(total) if total is not None else len(payload.get("stations") or [])


@router.get("/{place_id}", response_model=PlaceRead)
async def get_place(
    place_id: int,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """One place, in full.

    **A negative id is a live fuel station.** The map's fuel pins are read from
    whereq.cloud when ``FUEL_READ_MODE`` is ``cloud``, and their ids are the
    negative of the upstream's station ids — the local place ids are positive,
    so the sign tells the two apart. The card is then served from the
    upstream, re-shaped into this app's place shape.

    The prices are the licensed part: they are included for a signed-in
    caller and stripped for an anonymous one, exactly as they are for a
    mirrored station.
    """
    if place_id < 0:
        return await _live_fuel_place(place_id, user is not None)

    # One statement for the whole read-and-count. The old code read the row,
    # added 1 in Python, committed, then re-read it with `db.refresh()` — three
    # statements and a round trip per view, and a **lost update**: two
    # concurrent readers both read 10 and both wrote 11. `view_count + 1` in the
    # UPDATE is atomic, and `RETURNING` hands the new row back in the same
    # statement, so the response needs no second SELECT.
    #
    # `synchronize_session=False` keeps SQLAlchemy from walking the session;
    # the row it returns is not dirty, so the commit writes it exactly once.
    place = (await db.execute(
        update(Place)
        .where(Place.id == place_id)
        .values(view_count=Place.view_count + 1)
        .returning(Place)
        .execution_options(synchronize_session=False)
    )).scalars().first()
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    await db.commit()
    return _read(place, include_prices=user is not None)


async def _live_fuel_place(place_id: int, include_prices: bool) -> PlaceRead:
    """A fuel station read from whereq.cloud, as this app's place shape."""
    import asyncio

    from app.services.cloud_fuel import fetch_station

    try:
        payload = await asyncio.to_thread(fetch_station, station_id=-place_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud fuel: the station could not be read — %s", exc)
        raise HTTPException(status_code=502, detail="Fuel station is unavailable") from exc

    station = (payload or {}).get("station") or (payload or {}).get("data") or {}
    if not station:
        raise HTTPException(status_code=404, detail="Place not found")

    country = (station.get("country") or "").upper() or None
    prices = station.get("prices") or {}
    stamps = [p.get("observed_at") for p in prices.values()
              if isinstance(p, dict) and p.get("observed_at")]
    meta: dict = {
        "brand": station.get("brand"),
        "state": station.get("state"),
        "state_iso": station.get("state_iso"),
        "municipality": station.get("municipality"),
        "prices": prices,
        "observed_at": max(stamps) if stamps else None,
        "currency": CURRENCY_BY_COUNTRY.get(country),
        "unit": UNIT_BY_COUNTRY.get(country),
        "data_source": station.get("source"),
        "station_id": station.get("id"),
    }
    if not include_prices:
        # The anonymous caller gets the place's own facts and nothing else:
        # not the prices (licensed), and not which upstream feed supplied them.
        # The dict is built here, so the allowlist is exact.
        meta = {k: meta[k] for k in PUBLIC_STATION_META_KEYS}

    return PlaceRead(
        id=place_id,
        name=(station.get("name") or station.get("brand") or "Fuel station")[:255],
        description=None,
        address=None,
        city=station.get("municipality"),
        country=country,
        latitude=station.get("lat"),
        longitude=station.get("lon"),
        category=FUEL_CATEGORY,
        kind="poi",
        sub=station.get("brand"),
        metadata_json=meta,
        view_count=0,
        created_at=datetime.now(timezone.utc),
    )


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
    # the ownership rules and the ingesters key their own rows on
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
