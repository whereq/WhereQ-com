"""The OpenStreetMap (Overpass) POI crawl — into the ``places`` table.

Free, storable, owned data for the map's Local Essentials (pharmacies, walk-in
clinics, libraries, plazas) and Quick Categories (food, coffee, fuel, parking,
stays). Each category maps to one or more OSM tag selectors; results are
upserted idempotently by ``(source='osm', external_id='node/123')`` so re-runs
refresh rather than duplicate. Schools have their own dedicated pipeline and are
intentionally not crawled here.

Run:  python -m app.crawler.cli.places [--bbox minLng,minLat,maxLng,maxLat] [--only food,coffee]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.place import Place

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_HEADERS = {"User-Agent": "whereq.com POI crawler (osm-contact@whereq.com)"}

# Default area: the Greater Toronto Area, as minLng,minLat,maxLng,maxLat.
DEFAULT_BBOX: tuple[float, float, float, float] = (-80.0, 43.4, -78.9, 44.1)


@dataclass
class OsmCategory:
    key: str                 # selector for --only and logging
    kind: str                # Place.kind
    category: str            # Place.category
    selectors: list[str]     # Overpass tag filters, e.g. '["amenity"="cafe"]'
    require_name: bool = True
    # Fallback display name for inherently-unnamed features (parking, fuel).
    fallback_name: str = ""
    sub_tag: str | None = None  # tag copied into Place.sub when present


# Local Essentials (kind != "poi") + Quick Categories (kind == "poi").
OSM_CATEGORIES: list[OsmCategory] = [
    # --- Local Essentials ---
    OsmCategory("pharmacy", "pharmacy", "pharmacy", ['["amenity"="pharmacy"]']),
    OsmCategory("clinic", "clinic", "clinic",
                ['["amenity"="clinic"]', '["amenity"="doctors"]', '["healthcare"="clinic"]']),
    OsmCategory("library", "library", "library", ['["amenity"="library"]']),
    OsmCategory("plaza", "plaza", "plaza",
                ['["place"="square"]', '["amenity"="marketplace"]', '["shop"="mall"]']),
    # --- Quick Categories (POIs) ---
    OsmCategory("food", "poi", "food", ['["amenity"="restaurant"]'], sub_tag="cuisine"),
    OsmCategory("coffee", "poi", "coffee", ['["amenity"="cafe"]'], sub_tag="cuisine"),
    OsmCategory("fuel", "poi", "fuel", ['["amenity"="fuel"]'],
                require_name=False, fallback_name="Gas station", sub_tag="brand"),
    OsmCategory("parking", "poi", "parking", ['["amenity"="parking"]'],
                require_name=False, fallback_name="Parking"),
    OsmCategory("stays", "poi", "stays",
                ['["tourism"="hotel"]', '["tourism"="motel"]',
                 '["tourism"="hostel"]', '["tourism"="guest_house"]']),
    # --- Scoring-only data (not shown as map toggles; feeds neighborhood
    #     insights: transit / bike / greenery). ---
    OsmCategory("transit", "transit", "transit",
                ['["highway"="bus_stop"]', '["railway"="station"]', '["railway"="tram_stop"]',
                 '["railway"="subway_entrance"]', '["public_transport"="station"]'],
                require_name=False, fallback_name="Transit stop"),
    OsmCategory("park", "park", "park",
                ['["leisure"="park"]', '["leisure"="garden"]'],
                require_name=False, fallback_name="Park"),
    OsmCategory("bike", "bike", "bike",
                ['["amenity"="bicycle_rental"]', '["amenity"="bicycle_parking"]'],
                require_name=False, fallback_name="Bike"),
]

_BY_KEY = {c.key: c for c in OSM_CATEGORIES}


def build_query(bbox: tuple[float, float, float, float], selectors: list[str], timeout: int = 180) -> str:
    """Overpass QL for the given tag selectors within bbox (minLng,minLat,maxLng,maxLat)."""
    mnlng, mnlat, mxlng, mxlat = bbox
    # Overpass bbox order is south,west,north,east (lat,lng).
    bb = f"{mnlat},{mnlng},{mxlat},{mxlng}"
    body = "".join(
        f'node{sel}({bb});way{sel}({bb});relation{sel}({bb});' for sel in selectors
    )
    return f"[out:json][timeout:{timeout}];({body});out center tags;"


async def _fetch(client: httpx.AsyncClient, query: str) -> list[dict]:
    resp = await client.post(OVERPASS_URL, data={"data": query}, headers=_HEADERS)
    resp.raise_for_status()
    return resp.json().get("elements", [])


def _coords(el: dict) -> tuple[float, float] | None:
    if el.get("type") == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        c = el.get("center") or {}
        lat, lon = c.get("lat"), c.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _element_to_row(el: dict, cat: OsmCategory) -> dict | None:
    coords = _coords(el)
    if not coords:
        return None
    lat, lng = coords
    tags = el.get("tags", {}) or {}
    name = (tags.get("name") or tags.get("brand") or "").strip()
    if not name:
        if cat.require_name:
            return None
        name = cat.fallback_name or cat.category.title()

    street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p).strip()
    meta = {k: tags[k] for k in ("brand", "website", "phone", "opening_hours", "cuisine", "operator")
            if tags.get(k)}
    return {
        "name": name[:255],
        "description": None,
        "latitude": lat,
        "longitude": lng,
        "address": (street or None),
        "city": tags.get("addr:city"),
        "country": "Canada",
        "category": cat.category,
        "kind": cat.kind,
        "sub": (tags.get(cat.sub_tag) if cat.sub_tag else None),
        "metadata_json": meta or None,
        "source": "osm",
        "external_id": f"{el.get('type')}/{el.get('id')}",
    }


async def _upsert(db: AsyncSession, rows: list[dict], batch: int = 500) -> int:
    """Idempotent upsert by (source, external_id). Returns rows written."""
    written = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        stmt = pg_insert(Place).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Place.source, Place.external_id],
            index_where=Place.external_id.isnot(None),
            set_={
                "name": stmt.excluded.name,
                "latitude": stmt.excluded.latitude,
                "longitude": stmt.excluded.longitude,
                "address": stmt.excluded.address,
                "city": stmt.excluded.city,
                "category": stmt.excluded.category,
                "kind": stmt.excluded.kind,
                "sub": stmt.excluded.sub,
                "metadata_json": stmt.excluded.metadata_json,
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
        written += len(chunk)
    return written


async def crawl_places(
    db: AsyncSession,
    bbox: tuple[float, float, float, float] = DEFAULT_BBOX,
    *,
    only: list[str] | None = None,
) -> dict[str, int]:
    """Crawl the configured OSM categories within bbox. Returns {category_key: count}."""
    cats = [_BY_KEY[k] for k in only if k in _BY_KEY] if only else OSM_CATEGORIES
    results: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=200.0) as client:
        for cat in cats:
            try:
                elements = await _fetch(client, build_query(bbox, cat.selectors))
            except Exception as exc:  # noqa: BLE001 — one category failing must not abort the rest
                logger.warning("Overpass fetch failed for %s: %s", cat.key, exc)
                results[cat.key] = 0
                continue
            # De-dup by external_id within the category (a feature can match >1 selector).
            rows = {}
            for el in elements:
                row = _element_to_row(el, cat)
                if row:
                    rows[row["external_id"]] = row
            written = await _upsert(db, list(rows.values()))
            results[cat.key] = written
            logger.info("OSM %s: %d features", cat.key, written)

    # Recompute geom from lat/lng for crawled rows (per-row SQL funcs can't be
    # bulk-set in the upsert above).
    await db.execute(text(
        "UPDATE places SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
        "WHERE source = 'osm' AND (geom IS NULL OR "
        "NOT ST_Equals(geom, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)))"
    ))
    await db.commit()
    return results
