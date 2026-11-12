"""The nearby search — everything around the map centre, in one list.

Public (anonymous browsing), with one exception: the live fuel prices are
licensed whereq.cloud data, so they are only included for a signed-in caller —
the station itself stays visible to everyone, exactly like ``/api/places``.

Four sources are merged into a single list, each with the distance semantics
its table allows:

* ``places``       — the POIs and the local essentials. PostGIS: a true radius
  (``ST_DWithin`` on the geography cast, so the third argument is metres) and
  a distance (``ST_DistanceSphere``).
* ``local_content`` — news, events, stories and topics. Same PostGIS treatment.
* ``hazards``      — user-reported incidents. Same, plus the liveness filters
  (an expired hazard must not show up).
* ``school``       — the school domain. It has plain ``lat``/``lng`` columns
  and no geometry, so it gets a numeric bounding box and an exact
  great-circle distance computed here.

The category vocabulary is the one the map already uses (see
``app.services.place_taxonomy``), so the same filter chips work everywhere.

**Every category is fetched and counted on its own.** A single "nearest N"
query per table would let one source swallow the list, so the places query
partitions by category (a window function keeps the nearest of each and
counts each) and the list is interleaved across the categories.
"""

import math

from fastapi import APIRouter, Depends, Query
from geoalchemy2 import Geography
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_optional_user
from app.models.hazard import Hazard
from app.models.local_content import LocalContent
from app.models.place import Place
from app.models.school import School
from app.models.user import User
from app.schemas.nearby import NearbyCenter, NearbyItem, NearbyResponse
from app.services.place_dedup import DEDUP_EXPAND_DEG, shadowed_stations
from app.services.place_taxonomy import (
    PLACE_KIND_CATEGORIES,
    PLACE_POI_CATEGORIES,
    expand_categories,
)

router = APIRouter(prefix="/nearby", tags=["nearby"])

#: The categories the filter chips use. The POI + essentials categories come
#: from the place taxonomy; "school", "news" and "alerts" are the other three
#: tables.
NEARBY_CATEGORIES: tuple[str, ...] = (
    "food", "coffee", "fuel", "parking", "stays",
    "pharmacy", "clinic", "library", "plaza", "memorial",
    "school", "news", "alerts",
)

#: How many items per category are kept before the list is interleaved. It is
#: generous enough that a category the radius happens not to contain is never
#: lost behind a nearer one.
PER_CATEGORY_LIMIT = 50

#: The cap for the sources that are a single category (news, alerts, schools).
PER_SOURCE_LIMIT = 200

#: Metres per degree of latitude — the numeric fallback for the schools, which
#: have no geometry to index.
_M_PER_DEG_LAT = 111_320.0

#: The product whose price is shown for a fuel station.
_PRICE_PRODUCT = "regular"


def _csv(value: str | None) -> list[str]:
    return [v.strip().lower() for v in value.split(",") if v.strip()] if value else []


def _requested_categories(raw: str | None) -> list[str]:
    """The categories to apply. Absent or empty means every category."""
    if raw is None or not raw.strip():
        return list(NEARBY_CATEGORIES)
    return [c for c in _csv(raw) if c in NEARBY_CATEGORIES]


def _bbox(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """The bounding box of the radius — (min_lng, min_lat, max_lng, max_lat)."""
    d_lat = radius_km * 1000.0 / _M_PER_DEG_LAT
    cos_lat = max(0.01, abs(math.cos(math.radians(lat))))
    d_lng = radius_km * 1000.0 / (_M_PER_DEG_LAT * cos_lat)
    return lng - d_lng, lat - d_lat, lng + d_lng, lat + d_lat


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """The great-circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _place_category_case():
    """SQL for the filter key a place row belongs under.

    It mirrors ``_place_category`` (the Python mapping) so the counts and the
    buckets agree with what the UI groups by.
    """
    return case(
        (and_(Place.kind == "poi", Place.category.in_(("fuel", "gas"))), "fuel"),
        (Place.kind == "poi", Place.category),
        (or_(Place.kind == "memorial", Place.category == "memorial"), "memorial"),
        else_=Place.kind,
    )


def _place_conditions(cats: list[str]) -> list:
    """SQL matching the requested categories.

    A category can live on ``places.kind`` (the essentials, the memorials) or
    on ``places.category`` (the POI rows), so both are checked — the map's own
    ``/places/map`` splits them into two parameters for the same reason.
    """
    clauses = []
    kinds = [c for c in cats if c in PLACE_KIND_CATEGORIES]
    pois = expand_categories([c for c in cats if c in PLACE_POI_CATEGORIES])
    if kinds:
        clauses.append(Place.kind.in_(kinds))
    if pois:
        clauses.append(and_(Place.kind == "poi", Place.category.in_(pois)))
    if "memorial" in cats:
        # A memorial is a place with a story attached; the legacy seed rows
        # carry it on `kind`, but a user-created one may use `category`.
        clauses.append(or_(Place.kind == "memorial", Place.category == "memorial"))
    if not clauses:
        return []
    return [or_(*clauses) if len(clauses) > 1 else clauses[0]]


def _place_category(place_kind: str, place_category: str) -> str:
    """The filter key a place row belongs under."""
    if place_kind == "poi":
        return "fuel" if place_category in ("fuel", "gas") else place_category
    if place_kind == "memorial" or place_category == "memorial":
        return "memorial"
    return place_kind


def _price_fields(meta: dict, include_prices: bool) -> tuple[float | None, str | None, str | None]:
    """(price, currency, observed_at) from a station's metadata.

    The prices are licensed whereq.cloud data: they are only ever included
    for a signed-in caller. The station itself stays visible to everyone.
    """
    if not include_prices:
        return None, None, None
    product = (meta.get("prices") or {}).get(_PRICE_PRODUCT) or {}
    return product.get("price"), meta.get("currency"), meta.get("observed_at")


def _places_stmt(lat, lng, radius_m, cats, per_category):
    """The statement behind the places half of the nearby list.

    The window functions do two jobs at once: ``row_number`` over the category
    partition keeps the nearest N of *each* category (so a category the radius
    happens not to contain is not lost behind a nearer one), and ``count``
    over the same partition gives the true number of that category nearby —
    a badge the truncated list could never supply.
    """
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    distance = func.ST_DistanceSphere(Place.geom, point).label("distance_m")
    cat = _place_category_case()

    conds = [
        Place.geom.is_not(None),
        func.ST_DWithin(Place.geom.cast(Geography), point.cast(Geography), radius_m),
    ]
    conds += _place_conditions(cats)

    if "fuel" in cats:
        # The OSM row of a station that whereq.cloud already covers is dropped,
        # so a station is listed once — the priced row wins.
        min_lng, min_lat, max_lng, max_lat = _bbox(lat, lng, radius_m / 1000.0)
        envelope = func.ST_MakeEnvelope(
            min_lng - DEDUP_EXPAND_DEG, min_lat - DEDUP_EXPAND_DEG,
            max_lng + DEDUP_EXPAND_DEG, max_lat + DEDUP_EXPAND_DEG, 4326)
        conds.append(Place.id.not_in(shadowed_stations(envelope)))

    inner = select(
        Place.id.label("id"),
        Place.name.label("name"),
        Place.kind.label("kind"),
        Place.category.label("category"),
        Place.sub.label("sub"),
        Place.city.label("city"),
        Place.latitude.label("latitude"),
        Place.longitude.label("longitude"),
        Place.metadata_json.label("metadata_json"),
        cat.label("cat"),
        distance,
        func.row_number().over(partition_by=cat, order_by=distance).label("rn"),
        func.count().over(partition_by=cat).label("cat_count"),
    ).where(*conds).subquery()

    return select(
        inner.c.id, inner.c.name, inner.c.kind, inner.c.category, inner.c.sub,
        inner.c.city, inner.c.latitude, inner.c.longitude, inner.c.metadata_json,
        inner.c.cat, inner.c.distance_m, inner.c.cat_count,
    ).where(inner.c.rn <= per_category).order_by(inner.c.cat, inner.c.rn)


async def _nearby_places(db, lat, lng, radius_m, cats, per_category, include_prices):
    """The POIs and local essentials within the radius.

    Returns ``(buckets, counts)``: the nearest items of each category, and the
    true number of that category nearby.
    """
    rows = (await db.execute(_places_stmt(lat, lng, radius_m, cats, per_category))).all()
    buckets: dict[str, list[NearbyItem]] = {}
    counts: dict[str, int] = {}
    for r in rows:
        price, currency, observed_at = _price_fields(r.metadata_json or {}, include_prices)
        item = NearbyItem(
            id=f"place-{r.id}",
            type="place",
            category=r.cat,
            subcategory=r.sub,
            name=r.name,
            meta=r.city or r.sub,
            lat=r.latitude,
            lng=r.longitude,
            distance_m=int(round(r.distance_m or 0)),
            price=price,
            currency=currency,
            observed_at=observed_at,
        )
        buckets.setdefault(r.cat, []).append(item)
        counts[r.cat] = int(r.cat_count)
    return buckets, counts


async def _nearby_local_content(db, lat, lng, radius_m, cats, limit):
    """The news, events, stories and topics within the radius.

    Returns ``(items, count)`` — the count comes from a window function over
    the whole result, so it is the true number nearby even though only
    ``limit`` rows are fetched.
    """
    if "news" not in cats:
        return [], 0
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    distance = func.ST_DistanceSphere(LocalContent.geom, point).label("distance_m")

    stmt = select(
        LocalContent.id, LocalContent.type, LocalContent.category, LocalContent.title,
        LocalContent.source_name, LocalContent.event_time, LocalContent.publish_time,
        LocalContent.latitude, LocalContent.longitude, LocalContent.source_url,
        LocalContent.image_url, distance,
        func.count().over().label("total"),
    ).where(
        LocalContent.status == "active",
        LocalContent.geom.is_not(None),
        func.ST_DWithin(LocalContent.geom.cast(Geography), point.cast(Geography), radius_m),
        or_(LocalContent.expires_at.is_(None), LocalContent.expires_at > func.now()),
    ).order_by(distance.asc()).limit(limit)

    rows = (await db.execute(stmt)).all()
    items = [NearbyItem(
        id=f"local-{r.id}",
        type="local",
        category="news",
        subcategory=r.category,
        name=r.title,
        meta=r.source_name,
        lat=r.latitude,
        lng=r.longitude,
        distance_m=int(round(r.distance_m or 0)),
        url=r.source_url,
        image_url=r.image_url,
        when=r.event_time or r.publish_time,
    ) for r in rows]
    return items, int(rows[0].total) if rows else 0


async def _nearby_hazards(db, lat, lng, radius_m, cats, limit):
    """The live user-reported incidents within the radius."""
    if "alerts" not in cats:
        return [], 0
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    distance = func.ST_DistanceSphere(Hazard.geom, point).label("distance_m")

    stmt = select(
        Hazard.id, Hazard.type, Hazard.severity, Hazard.title, Hazard.description,
        Hazard.latitude, Hazard.longitude, distance,
        func.count().over().label("total"),
    ).where(
        Hazard.status == "active",
        Hazard.geom.is_not(None),
        Hazard.expires_at > func.now(),
        func.ST_DWithin(Hazard.geom.cast(Geography), point.cast(Geography), radius_m),
    ).order_by(distance.asc()).limit(limit)

    rows = (await db.execute(stmt)).all()
    items = [NearbyItem(
        id=f"hazard-{r.id}",
        type="hazard",
        category="alerts",
        subcategory=r.type,
        name=r.title,
        meta=r.description or r.type,
        lat=r.latitude,
        lng=r.longitude,
        distance_m=int(round(r.distance_m or 0)),
    ) for r in rows]
    return items, int(rows[0].total) if rows else 0


async def _nearby_schools(db, lat, lng, radius_m, cats, limit):
    """The schools within the radius.

    ``school`` has plain ``lat``/``lng`` columns and no geometry, so the
    radius is a numeric bounding box followed by an exact great-circle
    distance here. The count is exact for the same reason.
    """
    if "school" not in cats:
        return [], 0
    min_lng, min_lat, max_lng, max_lat = _bbox(lat, lng, radius_m / 1000.0)
    stmt = select(
        School.id, School.name, School.type, School.city, School.lat, School.lng,
    ).where(
        School.lat.is_not(None),
        School.lng.is_not(None),
        School.lat.between(min_lat, max_lat),
        School.lng.between(min_lng, max_lng),
    ).limit(limit)

    rows = (await db.execute(stmt)).all()
    items = []
    for r in rows:
        distance = _haversine_m(lat, lng, r.lat, r.lng)
        if distance > radius_m:
            continue
        items.append(NearbyItem(
            id=f"school-{r.id}",
            type="school",
            category="school",
            subcategory=r.type,
            name=r.name,
            meta=r.city or r.type,
            lat=r.lat,
            lng=r.lng,
            distance_m=int(round(distance)),
        ))
    items.sort(key=lambda i: i.distance_m)
    return items[:limit], len(items)


def _interleave(buckets: dict[str, list[NearbyItem]], order: tuple[str, ...]) -> list[NearbyItem]:
    """Merge the per-category lists round-robin, nearest first within each.

    A plain distance sort would let one category swallow the whole list: the
    crawler's news carries a fallback coordinate for thousands of rows, so they
    all sit at distance 0. Taking the nearest item of each category in turn
    keeps every category represented — which is the whole point of "everything
    nearby".
    """
    out: list[NearbyItem] = []
    index = 0
    while True:
        added = False
        for cat in order:
            items = buckets.get(cat)
            if items and index < len(items):
                out.append(items[index])
                added = True
        if not added:
            break
        index += 1
    return out


@router.get("/categories")
async def nearby_categories() -> dict[str, list[str]]:
    """The category vocabulary the filter chips use.

    Published so the UI can stay in step with the backend instead of keeping
    its own copy of the list.
    """
    return {"categories": list(NEARBY_CATEGORIES)}


@router.get("", response_model=NearbyResponse)
async def list_nearby(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float | None = Query(None, ge=0.1, le=settings.nearby_max_radius_km),
    categories: str | None = Query(None, description="CSV of category keys; empty = all"),
    limit: int = Query(100, ge=1, le=300),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Everything near (lat, lng) — the POIs, the fuel stations, the news and
    the schools within the radius, merged into one list."""
    radius = radius_km or settings.nearby_default_radius_km
    radius = min(radius, settings.nearby_max_radius_km)
    radius_m = int(round(radius * 1000))
    cats = _requested_categories(categories)

    buckets: dict[str, list[NearbyItem]] = {}
    counts: dict[str, int] = {}
    if cats:
        include_prices = user is not None
        place_buckets, place_counts = await _nearby_places(
            db, lat, lng, radius_m, cats, PER_CATEGORY_LIMIT, include_prices)
        buckets.update(place_buckets)
        counts.update(place_counts)

        news, news_count = await _nearby_local_content(db, lat, lng, radius_m, cats, PER_SOURCE_LIMIT)
        if news:
            buckets["news"] = news
        if news_count:
            counts["news"] = news_count

        alerts, alerts_count = await _nearby_hazards(db, lat, lng, radius_m, cats, PER_SOURCE_LIMIT)
        if alerts:
            buckets["alerts"] = alerts
        if alerts_count:
            counts["alerts"] = alerts_count

        schools, school_count = await _nearby_schools(db, lat, lng, radius_m, cats, PER_SOURCE_LIMIT)
        if schools:
            buckets["school"] = schools
        if school_count:
            counts["school"] = school_count

    items = _interleave(buckets, NEARBY_CATEGORIES)[:limit]

    return NearbyResponse(
        items=items,
        counts=counts,
        total=len(items),
        radius_m=radius_m,
        center=NearbyCenter(lat=lat, lng=lng),
        categories=cats,
    )
