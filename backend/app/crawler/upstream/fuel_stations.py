"""The whereq.cloud fuel-station crawl — into the ``places`` table.

Crawls North American fuel stations (with live per-product prices) from the
whereq.cloud data API (the official ``whereq_cloud`` Python SDK) and upserts
them as POIs (``kind='poi'``, ``category='gas'``, ``source='whereq_cloud'``)
so they appear on the map as a dedicated "Gas Prices" quick-category alongside
the OSM essentials.

Coverage is expressed as *targets* — a country, a state/province, a city or a
map bbox — and crawled round-robin (see ``app.crawler.scheduler``) so a single
tick never pulls the whole continent.

Whereq Cloud specifics this module handles:

* **The key never leaves the backend.** ``WHEREQ_CLOUD_API_KEY`` is read from
  the server environment and sent as an ``X-API-Key`` header by the SDK; the
  browser only ever talks to our own ``/api/places`` endpoints.
* **Rate limits.** The fuel endpoints allow 30 requests/minute per key and
  answer ``429`` with ``Retry in Ns``. Requests are self-throttled and retried
  with backoff.
* **Paging.** ``limit`` is capped at 500 rows, so a coverage target is fetched
  page by page until the reported ``total`` is reached.
* **Money.** Prices are quoted in *local currency per litre* (CAD/L, USD/L,
  MXN/L) — the currency travels with the row so the UI can render a US price
  as USD and a Canadian one as CAD.
* **Demo mode.** Without a key the API returns a 100-row preview of the oldest
  rows and ignores paging; that preview is rejected unless explicitly allowed.

Run:  python -m app.crawler.cli.fuel [--target "CA:Ontario"] [--prices]
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from geoalchemy2 import Geography
from sqlalchemy import Float, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import whereq_cloud
from whereq_cloud import FUEL_COUNTRIES, FUEL_CURRENCIES

from app.core.config import settings
from app.crawler.upstream.whereq_cloud import (
    Throttle as _Throttle,
    call_with_retry,
    client as _client,
    has_api_key,
    retry_delay,
    shared_throttle,
)
from app.models.fuel import FuelSyncState
from app.models.place import Place

logger = logging.getLogger(__name__)

FUEL_CATEGORY = "gas"
FUEL_SOURCE = "whereq_cloud"

#: Whereq Cloud quotes fuel in local currency per litre.
UNIT_BY_COUNTRY: dict[str, str] = dict(FUEL_CURRENCIES)
CURRENCY_BY_COUNTRY: dict[str, str] = {
    cc: unit.split("/")[0] for cc, unit in FUEL_CURRENCIES.items()
}

#: ``places.external_id`` is a String(64) — the column the upsert keys on.
_MAX_EXTERNAL_ID = 64


# ── coverage targets ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FuelTarget:
    """One area to crawl: a country, a state/province, a city, or a map bbox.

    ``state`` is a full name or an ISO code — whereq.cloud accepts both
    ("Ontario" and "ON" resolve to the same rows).
    """

    country: str | None = None
    state: str | None = None
    municipality: str | None = None
    bbox: str | None = None

    @property
    def key(self) -> str:
        """Stable identity of this target (used as the sync-state primary key)."""
        if self.bbox:
            return f"bbox:{self.bbox}"
        parts = [p for p in (self.country, self.state, self.municipality) if p]
        return ":".join(p.lower() for p in parts)

    @property
    def label(self) -> str:
        if self.bbox:
            return f"bbox {self.bbox}"
        return " / ".join(p for p in (self.country, self.state, self.municipality) if p) or "all"

    def api_filters(self) -> dict[str, str]:
        """Query parameters for the whereq.cloud fuel endpoints."""
        filters: dict[str, str] = {}
        if self.country:
            filters["country"] = self.country
        if self.state:
            filters["state"] = self.state
        if self.municipality:
            filters["municipality"] = self.municipality
        if self.bbox:
            filters["bbox"] = self.bbox
        return filters


def parse_target(spec: str) -> FuelTarget | None:
    """Parse a target spec: ``CC`` | ``CC:State`` | ``CC:State:Municipality``
    | ``bbox:minLon,minLat,maxLon,maxLat``. Returns None when unusable."""
    spec = (spec or "").strip()
    if not spec:
        return None
    if spec.lower().startswith("bbox:"):
        bbox = spec[5:].strip()
        parts = bbox.split(",")
        if len(parts) != 4 or not all(p.strip() for p in parts):
            logger.warning("ignoring malformed fuel target %r (bbox needs 4 numbers)", spec)
            return None
        return FuelTarget(bbox=bbox)
    bits = [b.strip() for b in spec.split(":")]
    country = bits[0].upper() if bits and bits[0] else None
    if country and country not in FUEL_COUNTRIES:
        logger.warning("ignoring fuel target %r (unknown country; expected one of %s)",
                       spec, ", ".join(FUEL_COUNTRIES))
        return None
    return FuelTarget(
        country=country or None,
        state=bits[1] if len(bits) > 1 and bits[1] else None,
        municipality=bits[2] if len(bits) > 2 and bits[2] else None,
    )


def configured_targets() -> list[FuelTarget]:
    """The coverage targets from ``FUEL_CRAWL_TARGETS`` (deduped, ordered)."""
    seen: dict[str, FuelTarget] = {}
    for spec in settings.FUEL_CRAWL_TARGETS.split(","):
        target = parse_target(spec)
        if target and target.key not in seen:
            seen[target.key] = target
    return list(seen.values())


# ── API plumbing ────────────────────────────────────────────────────────────
# The throttle, the retry policy and the client live in
# ``app/crawler/upstream/whereq_cloud.py`` — the fuel crawl and the geography
# crawl share one whereq.cloud key and therefore one 30 requests/minute
# budget, so they must share one limiter (two would 429 each other).


# ── row mapping ─────────────────────────────────────────────────────────────
def external_id_for(source: str, ext_id: Any) -> str:
    """Stable id within ``places.external_id`` (String(64)).

    Whereq Cloud ids are short for the Canadian feeds but can be long for the
    US ones; truncating would map two different stations onto the same key and
    silently merge them, so anything that doesn't fit is hashed instead.
    """
    raw = f"{source}/{ext_id}"
    if len(raw) <= _MAX_EXTERNAL_ID:
        return raw
    digest = hashlib.sha256(str(ext_id).encode()).hexdigest()[:40]
    return f"{source[:16]}/{digest}"


def station_to_row(station: dict, *, country_hint: str | None = None) -> dict | None:
    """Map a whereq.cloud station to a ``places`` row, or None if unusable."""
    lat, lon = station.get("lat"), station.get("lon")
    if lat is None or lon is None:
        return None
    ext_id = station.get("ext_id") or station.get("id")
    if ext_id is None:
        return None

    country = (station.get("country") or country_hint or "").upper() or None
    source = station.get("source") or "wq"
    prices = station.get("prices") or None

    observed_at = None
    if isinstance(prices, dict):
        stamps = [p.get("observed_at") for p in prices.values()
                  if isinstance(p, dict) and p.get("observed_at")]
        observed_at = max(stamps) if stamps else None

    meta: dict[str, Any] = {
        "brand": station.get("brand"),
        "state": station.get("state"),
        "state_iso": station.get("state_iso"),
        "municipality": station.get("municipality"),
        "prices": prices,
        "observed_at": observed_at,
        # The currency the numbers are quoted in — CAD/L, USD/L, MXN/L.
        "currency": CURRENCY_BY_COUNTRY.get(country),
        "unit": UNIT_BY_COUNTRY.get(country),
        # Provenance: which upstream feed the row came from.
        "data_source": source,
        "station_id": station.get("id"),
    }
    name = (station.get("name") or station.get("brand") or "Fuel station").strip()
    return {
        "name": (name or "Fuel station")[:255],
        "description": None,
        "latitude": float(lat),
        "longitude": float(lon),
        "address": None,
        "city": station.get("municipality"),
        "country": country,
        "category": FUEL_CATEGORY,
        "kind": "poi",
        "sub": station.get("brand"),
        "metadata_json": {k: v for k, v in meta.items() if v is not None},
        "source": FUEL_SOURCE,
        "external_id": external_id_for(source, ext_id),
    }


# ── persistence ─────────────────────────────────────────────────────────────
async def upsert_places(db: AsyncSession, rows: list[dict], batch: int = 500) -> int:
    """Idempotent upsert by ``(source, external_id)``. Returns rows written.

    The PostGIS point is computed in the same statement, so a crawl never needs
    a second pass over the table to rebuild geometry.
    """
    written = 0
    for i in range(0, len(rows), batch):
        values = []
        for row in rows[i:i + batch]:
            item = dict(row)
            item["geom"] = func.ST_SetSRID(
                func.ST_MakePoint(item["longitude"], item["latitude"]), 4326)
            values.append(item)
        stmt = pg_insert(Place).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Place.source, Place.external_id],
            index_where=Place.external_id.isnot(None),
            set_={
                "name": stmt.excluded.name,
                "latitude": stmt.excluded.latitude,
                "longitude": stmt.excluded.longitude,
                "city": stmt.excluded.city,
                "country": stmt.excluded.country,
                "category": stmt.excluded.category,
                "kind": stmt.excluded.kind,
                "sub": stmt.excluded.sub,
                "metadata_json": stmt.excluded.metadata_json,
                "geom": stmt.excluded.geom,
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
        written += len(values)
    return written


def _iter_stations(client: whereq_cloud.Client, *, target: FuelTarget,
                   throttle: _Throttle, max_stations: int,
                   allow_demo: bool = False) -> Iterator[dict]:
    """Yield every station of a target, page by page (SDK + backoff).

    The unentitled preview returns the same oldest rows for every page and
    ignores paging, so it is yielded at most once — and only when the caller
    explicitly asked for the demo rows.
    """
    filters = target.api_filters()
    page_size = max(1, min(settings.FUEL_CRAWL_PAGE_SIZE, 500))
    offset = 0
    fetched = 0

    while True:
        throttle.wait()
        page = call_with_retry(
            client.fuel_stations,
            attempts=settings.FUEL_CRAWL_MAX_RETRIES,
            limit=page_size, offset=offset, **filters)
        stations = page.get("stations") or []
        if not stations:
            return
        if page.get("demo"):
            # Unentitled preview: the same oldest rows on every page.
            logger.warning("whereq.cloud returned the DEMO preview for %s "
                           "(set WHEREQ_CLOUD_API_KEY for live data)", target.label)
            if allow_demo:
                yield from stations
            return
        yield from stations
        fetched += len(stations)
        if fetched >= max_stations:
            logger.warning("fuel crawl for %s stopped at the %d-station cap",
                           target.label, max_stations)
            return
        offset += len(stations)
        total = page.get("total")
        if total is not None and offset >= total:
            return


def _collect_rows(target: FuelTarget, throttle: _Throttle, cap: int,
                  allow_demo: bool) -> dict[str, dict]:
    """Fetch every station of a target. Blocking — run it in a worker thread."""
    rows: dict[str, dict] = {}
    with _client() as client:
        for station in _iter_stations(client, target=target, throttle=throttle,
                                      max_stations=cap, allow_demo=allow_demo):
            row = station_to_row(station, country_hint=target.country)
            if row is None:
                continue
            rows[row["external_id"]] = row
            if len(rows) >= cap:
                break
    return rows


async def crawl_target(db: AsyncSession, target: FuelTarget, *,
                      allow_demo: bool = False,
                      max_stations: int | None = None) -> int:
    """Crawl one coverage target. Returns the number of stations written."""
    cap = max_stations if max_stations is not None else settings.FUEL_CRAWL_MAX_STATIONS
    throttle = shared_throttle

    # The SDK is synchronous (and the throttle sleeps), so the fetch runs in a
    # worker thread — the crawler's other ticks must keep flowing meanwhile.
    rows = await asyncio.to_thread(_collect_rows, target, throttle, cap, allow_demo)

    if not rows:
        logger.info("fuel crawl %s: no stations returned", target.label)
        return 0

    written = await upsert_places(db, list(rows.values()))
    await db.commit()
    logger.info("fuel crawl %s: %d stations", target.label, written)
    return written


async def crawl_fuel_stations(db: AsyncSession, *,
                               targets: list[FuelTarget] | None = None,
                               allow_demo: bool = False,
                               max_stations: int | None = None) -> dict[str, int]:
    """Crawl every given target (default: the configured ones).

    Returns ``{target label: stations written}``.
    """
    targets = targets if targets is not None else configured_targets()
    results: dict[str, int] = {}
    for target in targets:
        try:
            results[target.label] = await crawl_target(
                db, target, allow_demo=allow_demo, max_stations=max_stations)
        except whereq_cloud.WhereqError as exc:
            logger.warning("fuel crawl %s failed: %s", target.label, exc)
            results[target.label] = 0
    return results


# ── finding stations ────────────────────────────────────────────────────────
def _radius_condition(lng: float, lat: float, radius_km: float):
    """A "within N km" condition.

    ``ST_DWithin`` on a 4326 *geometry* measures in degrees, so a radius in
    metres would silently match the whole planet. The geography cast is what
    makes the third argument metres.
    """
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    return func.ST_DWithin(
        Place.geom.cast(Geography), point.cast(Geography), radius_km * 1_000)


def _price_column(product: str):
    """SQL for a product's price inside ``metadata_json.prices``.

    ``metadata_json -> 'prices' -> :product ->> 'price'`` — NULL when the
    station doesn't quote that product.
    """
    return Place.metadata_json["prices"][product]["price"].astext.cast(Float)


async def find_stations(db: AsyncSession, *, q: str | None = None,
                        lat: float | None = None, lng: float | None = None,
                        radius_km: float | None = None, bbox: str | None = None,
                        product: str = "regular", sort: str = "distance",
                        limit: int = 20) -> list[dict]:
    """Gas stations with their prices — nearest first, or cheapest first.

    This reads the rows we already crawled from whereq.cloud, so it costs
    nothing metered and never touches the upstream API.
    """
    conds = [Place.source == FUEL_SOURCE]
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(
            Place.name.ilike(like),
            Place.sub.ilike(like),      # the brand ("Esso", "Pioneer")
            Place.city.ilike(like),
        ))

    distance = None
    if lat is not None and lng is not None:
        point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
        if radius_km:
            conds.append(_radius_condition(lng, lat, radius_km))
        distance = func.ST_DistanceSphere(Place.geom, point)

    if bbox:
        parts = [p.strip() for p in bbox.split(",")]
        if len(parts) == 4:
            mn_lng, mn_lat, mx_lng, mx_lat = (float(v) for v in parts)
            conds.append(func.ST_Intersects(
                Place.geom,
                func.ST_MakeEnvelope(mn_lng, mn_lat, mx_lng, mx_lat, 4326),
            ))

    price = _price_column(product) if product else None
    stmt = select(
        Place.id, Place.name, Place.sub, Place.city, Place.country,
        Place.latitude, Place.longitude, Place.metadata_json,
    ).where(*conds)

    if distance is not None:
        stmt = stmt.add_columns(distance.label("distance_m"))
    if price is not None:
        stmt = stmt.add_columns(price.label("product_price"))

    if sort == "price" and price is not None:
        # Cheapest first; stations without that product sort last.
        stmt = stmt.order_by(price.asc().nullslast())
    elif distance is not None:
        stmt = stmt.order_by(distance.asc())
    else:
        stmt = stmt.order_by(Place.name.asc())
    stmt = stmt.limit(limit)

    rows = (await db.execute(stmt)).all()
    out: list[dict] = []
    for row in rows:
        meta = row.metadata_json or {}
        prices = meta.get("prices") or {}
        chosen = prices.get(product) if product else None
        out.append({
            "id": row.id,
            "name": row.name,
            "brand": row.sub,
            "city": row.city,
            "country": row.country,
            "lat": row.latitude,
            "lng": row.longitude,
            "prices": prices,
            "currency": meta.get("currency"),
            "unit": meta.get("unit"),
            "observed_at": meta.get("observed_at"),
            "product": product,
            "price": (chosen or {}).get("price"),
            "distance_km": (round(row.distance_m / 1000, 2)
                            if distance is not None and row.distance_m is not None else None),
        })
    return out


# ── crawl bookkeeping ────────────────────────────────────────────────────────
async def sync_states(db: AsyncSession) -> dict[str, FuelSyncState]:
    """All recorded target states, keyed by target key.

    Tolerates a missing table: the crawler can start before the migration has
    run, and losing the bookkeeping is better than losing the crawl itself.
    """
    try:
        rows = (await db.execute(select(FuelSyncState))).scalars().all()
    except SQLAlchemyError as exc:
        logger.warning("fuel crawl state unavailable (%s) — continuing without it", exc)
        return {}
    return {r.target_key: r for r in rows}


def is_due(state: FuelSyncState | None, interval_hours: int) -> bool:
    """A target is due when it has never crawled or its last crawl is stale."""
    if state is None or state.last_synced_at is None:
        return True
    if state.last_error:
        # A failed crawl should not wait a full interval before being retried.
        return True
    age = datetime.now(timezone.utc) - state.last_synced_at
    return age >= timedelta(hours=interval_hours)


async def record_crawl(db: AsyncSession, target: FuelTarget, *,
                      station_count: int, error: str | None = None) -> None:
    """Persist the outcome of a target crawl."""
    now = datetime.now(timezone.utc)
    try:
        state = await db.get(FuelSyncState, target.key)
        if state is None:
            state = FuelSyncState(target_key=target.key)
            db.add(state)
        state.country = target.country
        state.state = target.state
        state.municipality = target.municipality
        state.bbox = target.bbox
        state.last_attempt_at = now
        if error is None:
            state.last_synced_at = now
            state.station_count = station_count
            state.last_error = None
        else:
            state.last_error = error[:500]
        await db.commit()
    except SQLAlchemyError as exc:
        # Bookkeeping must never lose a completed crawl.
        await db.rollback()
        logger.warning("could not record the fuel crawl state for %s: %s", target.key, exc)


async def due_targets(db: AsyncSession, targets: list[FuelTarget] | None = None,
                       interval_hours: int | None = None) -> list[FuelTarget]:
    """Targets whose refresh is due, oldest crawl first."""
    targets = targets if targets is not None else configured_targets()
    interval = interval_hours if interval_hours is not None else settings.FUEL_CRAWL_INTERVAL_HOURS
    states = await sync_states(db)
    due = [t for t in targets if is_due(states.get(t.key), interval)]
    due.sort(key=lambda t: (states[t.key].last_synced_at if t.key in states and
                             states[t.key].last_synced_at else datetime.min.replace(tzinfo=timezone.utc)))
    return due
