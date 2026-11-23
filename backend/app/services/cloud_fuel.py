"""Read the **fuel** feeds from whereq.cloud instead of from the local mirror.

THE MIRROR
----------
whereq.com used to keep two copies of whereq.cloud's fuel data: the stations
as ``places`` rows with ``source='whereq_cloud'`` and ``category='gas'`` (73 348
of them on PROD), and the aggregated price series in ``fuel_price_series``. Both
were refreshed on a schedule by the consumer. This module is the other side of
that: it reads the original, live, over the SDK.

WHY THE READ IS **RE-SHAPED**, NOT PROXIED
------------------------------------------
whereq.cloud's station row is not whereq.com's station row. The upstream
carries ``id``, ``ext_id``, ``source``, ``brand``, ``state``, ``state_iso`` and
``municipality``; this app's reader answers with a *place* shape — a name, a
brand, a city, a country, a position, a currency and a unit. The upstream's
prices are quoted in the same local currency per litre, but the currency has to
be looked up from the country, not read off the row.

So the payload is **re-shaped** into whereq.com's own shape and served as
whereq.com's own data. It is never passed through verbatim.

THE DEMO GATE
-------------
whereq.cloud answers an unentitled key with a 100-row preview of the oldest
rows, and — this is the part that matters — **the preview carries prices too**.
Serving it would mean serving a frozen slice as though it were the live feed.

So every read here asserts ``demo is False``. A preview is a failure, not a
fallback: the caller gets an error rather than a plausible-looking lie.

THE PRICES ARE LICENSED
------------------------
The station prices are licensed whereq.cloud data. The licence is enforced on
the **whereq.com** side, not here: ``/api/fuel/*`` requires a session, and the
place payload strips ``prices``/``observed_at`` for anonymous callers. This
module fetches the whole row; what the caller is allowed to see is decided
further out.

THE THROTTLE
-------------
The client-side limiter lives in ``app.services.whereq_cloud_client`` and is
shared with the other whereq.cloud readers. Its interval follows the key's
tier — the whereq.com service key is ``unlimited`` (1 200 requests/minute,
measured), and the shared floor is what keeps a free-tier key safe.
"""

from __future__ import annotations

import logging
from typing import Any

import whereq_cloud

from app.core.config import settings
from app.services.fuel_prices import normalize_per_litre, product_key
from app.services.fuel_stations import CURRENCY_BY_COUNTRY, FUEL_SOURCE, UNIT_BY_COUNTRY
from app.services.whereq_cloud_client import (
    call_with_retry,
    client as _client,
    shared_throttle,
)

logger = logging.getLogger(__name__)

#: The upstream's own page ceiling for stations.
STATION_PAGE_SIZE = 500

#: The upstream's own page ceiling for price series.
SERIES_PAGE_SIZE = 100

#: The most station rows one read may pull — ten pages, about 1.3 s of upstream
#: time at the measured latencies. It is the ceiling on a *complete* read: a
#: bigger area is read as far as this allows and the answer says so.
MAX_STATION_ROWS = 5_000


class CloudFuelError(RuntimeError):
    """The upstream could not be read, or answered with a preview."""


def _assert_live(payload: dict, what: str) -> dict:
    """Refuse a demo preview.

    whereq.cloud's demo gate limits *which* stations and *how many* rows come
    back — it does not remove the prices. A preview served as live data is the
    one failure mode this reader must never have, so it is an error, not a
    degraded answer.
    """
    if payload.get("demo"):
        raise CloudFuelError(
            f"whereq.cloud returned the demo preview for {what} — "
            "the key is not entitled to live fuel data")
    return payload


# ── stations ─────────────────────────────────────────────────────────────────
def fetch_stations(*, bbox: str | None = None, q: str | None = None,
                   country: str | None = None, state: str | None = None,
                   municipality: str | None = None, product: str | None = None,
                   limit: int = 100, offset: int = 0) -> dict:
    """One page of stations, as whereq.cloud's own payload.

    Blocking — the SDK is synchronous. Call it from a thread.
    """
    filters: dict[str, Any] = {}
    if bbox:
        filters["bbox"] = bbox
    if q:
        filters["q"] = q
    if country:
        filters["country"] = country
    if state:
        filters["state"] = state
    if municipality:
        filters["municipality"] = municipality
    if product:
        filters["product"] = product

    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(
            client.fuel_stations,
            attempts=settings.FUEL_INGEST_MAX_RETRIES,
            limit=max(1, min(limit, STATION_PAGE_SIZE)), offset=offset, **filters)
    finally:
        client.close()
    return _assert_live(payload or {}, "stations")


def fetch_stations_paged(*, max_rows: int = MAX_STATION_ROWS,
                         bbox: str | None = None, q: str | None = None,
                         country: str | None = None, state: str | None = None,
                         municipality: str | None = None,
                         product: str | None = None) -> dict:
    """Every station of a filter, read page by page.

    The upstream pages by ``offset`` and reports the **total** of the filtered
    set with every page, so the whole set is readable — but only page by page:
    one request returns at most 500 rows.

    The whole set is what makes the answer right. The upstream orders the rows
    by its own station id, so a single page is an arbitrary slice of the area:
    sorting that slice by distance gives the wrong "nearest" station. Measured
    on PROD for a 25 km box around downtown Toronto, the nearest station of
    the first page was 16 km away while the real one was 685 m away.

    Returns ``{"stations": [...], "total": int | None, "complete": bool}``.
    ``complete`` is False when the upstream holds more rows than ``max_rows``
    — the answer is then the best effort over the rows read, not the whole
    area, and the caller is expected to say so.

    Blocking — the SDK is synchronous. Call it from a thread.
    """
    max_rows = max(1, int(max_rows))
    rows: list[dict] = []
    total: int | None = None
    offset = 0
    while len(rows) < max_rows:
        page_size = min(STATION_PAGE_SIZE, max_rows - len(rows))
        payload = fetch_stations(
            bbox=bbox, q=q, country=country, state=state,
            municipality=municipality, product=product,
            limit=page_size, offset=offset)
        if total is None:
            raw = payload.get("total")
            total = int(raw) if isinstance(raw, (int, float)) else None
        page = payload.get("stations") or []
        rows.extend(page)
        if len(page) < page_size:
            break  # the upstream is exhausted
        offset += len(page)
    complete = total is None or len(rows) >= total
    return {"stations": rows[:max_rows], "total": total, "complete": complete}


def fetch_station(station_id: int) -> dict | None:
    """One station, with its price timeline. ``None`` if upstream has none."""
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(
            client.fuel_station, station_id=station_id)
    finally:
        client.close()
    payload = payload or {}
    return _assert_live(payload, "station")


def station_to_read(station: dict, *, product: str | None = None) -> dict:
    """An upstream station as whereq.com's station shape.

    The currency and the unit are **looked up from the country**, because the
    upstream quotes in local currency per litre but does not name the currency
    on the row.
    """
    country = (station.get("country") or "").upper() or None
    prices = station.get("prices") or {}
    observed_at = None
    stamps = [p.get("observed_at") for p in prices.values()
              if isinstance(p, dict) and p.get("observed_at")]
    if stamps:
        observed_at = max(stamps)
    chosen = prices.get(product) if product else None
    name = (station.get("name") or station.get("brand") or "Fuel station").strip()
    return {
        "id": station.get("id"),
        "name": name or "Fuel station",
        "brand": station.get("brand"),
        "city": station.get("municipality"),
        "country": country,
        "lat": station.get("lat"),
        "lng": station.get("lon"),
        "prices": prices,
        "currency": CURRENCY_BY_COUNTRY.get(country),
        "unit": UNIT_BY_COUNTRY.get(country),
        "observed_at": observed_at,
        "product": product,
        "price": (chosen or {}).get("price") if isinstance(chosen, dict) else None,
    }


def station_external_id(station: dict) -> str:
    """The stable id a station has in whereq.com's own place table.

    Same construction as the mirror used, so a station that is materialised
    (a user saved it) keeps the same key.
    """
    from app.services.fuel_stations import external_id_for

    source = station.get("source") or "wq"
    ext_id = station.get("ext_id") or station.get("id")
    return external_id_for(source, ext_id)


async def materialised_ids(db, stations: list[dict]) -> dict[str, int]:
    """Whereq.com's own row ids for the given stations, keyed by external id.

    A station the user has **saved** has a row of whereq.com's own — it was
    materialised when it was saved — and the map and the nearby list carry
    that row's id, so the saved state and the pins agree. A station nobody
    saved has no row, and its id is the negative of the upstream's.

    Only the **materialised** rows count. The rows the mirror wrote before
    the cut carry the same key and would match, and a pin pointing at one of
    those would open the *stale* card instead of the live one — so the
    marker the materialisation writes is what distinguishes them.
    """
    from sqlalchemy import select

    from app.models.place import Place

    external_ids = [station_external_id(s) for s in stations]
    if not external_ids:
        return {}
    found: dict[str, int] = {}
    for i in range(0, len(external_ids), 200):
        chunk = external_ids[i:i + 200]
        rows = (await db.execute(
            select(Place.external_id, Place.id)
            .where(
                Place.source == FUEL_SOURCE,
                Place.external_id.in_(chunk),
                Place.metadata_json["saved_from_cloud"].astext == "true",
            )
        )).all()
        found.update({r[0]: r[1] for r in rows})
    return found


# ── price series ────────────────────────────────────────────────────────────
def fetch_series(*, region: str | None = None, geo: str | None = None,
                 q: str | None = None, limit: int = 100,
                 offset: int = 0) -> dict:
    """One page of aggregated price series, as whereq.cloud's own payload."""
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(
            client.fuel_prices, region=region, geo=geo, q=q,
            limit=max(1, min(limit, SERIES_PAGE_SIZE)), offset=offset)
    finally:
        client.close()
    return payload or {}


def fetch_all_series(*, region: str | None = None, geo: str | None = None,
                     q: str | None = None, max_rows: int = 2000) -> list[dict]:
    """Every series matching the filters, paged to the end.

    The series are few (122 for Canada on 2026-11-21) but the upstream's page
    is 100 rows, so a whole region is two requests.
    """
    rows: list[dict] = []
    offset = 0
    while len(rows) < max_rows:
        payload = fetch_series(region=region, geo=geo, q=q,
                               limit=SERIES_PAGE_SIZE, offset=offset)
        data = payload.get("data") or []
        if not data:
            break
        rows.extend(data)
        offset += len(data)
        total = payload.get("count")
        if total is not None and offset >= total:
            break
    return rows


def series_to_read(series: dict) -> dict:
    """An upstream series as whereq.com's series shape.

    The litre normalisation is whereq.com's own rule — the upstream quotes
    "Cents per litre" and "$/GAL", and the UI puts a regional average next to
    a station price, so the two must be in the same unit.
    """
    value_per_litre, currency = normalize_per_litre(
        series.get("unit"), series.get("latest_value"))
    return {
        "id": series.get("id"),
        "domain": series.get("domain") or "fuel",
        "source": series.get("source"),
        "region": (series.get("region") or "").lower() or None,
        "geo": series.get("geo"),
        "item": series.get("item") or "",
        "product": product_key(series.get("item")),
        "unit": series.get("unit"),
        "currency": currency,
        "value_per_litre": value_per_litre,
        "frequency": series.get("frequency"),
        "latest_period": series.get("latest_period"),
        "latest_value": series.get("latest_value"),
        "prev_value": series.get("prev_value"),
        "points": series.get("points"),
        "spark": series.get("spark") or None,
        "updated_at": None,
    }


__all__ = [
    "CloudFuelError",
    "fetch_all_series",
    "fetch_series",
    "fetch_station",
    "fetch_stations",
    "series_to_read",
    "station_external_id",
    "station_to_read",
]
