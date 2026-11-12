"""The whereq.cloud geography crawl — the administrative places that *contain*
the places the map draws.

The feed is a second vocabulary of place: provinces, regions, municipalities,
cities, towns, wards and neighbourhoods, with real, drawable boundaries. It is
a different thing from the POIs in ``places``: a POI is a point, this is the
**area** the point falls in.

What this module handles:

* **Two vocabularies, kept apart.** The feed ships the crowd-mapped OSM
  places *and* the formal geoBoundaries ones, and deliberately does not merge
  them — a census subdivision and an OSM city boundary describe the same town
  in two languages. Both are stored, with their own ``source``.
* **The licence travels with the row.** OSM is ODbL 1.0 and geoBoundaries is
  CC-BY 4.0; both permit redistribution **with attribution**, so the
  attribution is carried on the place and shown in the UI.
* **Boundaries are fetched once, at full resolution.** The exact outline goes
  into the PostGIS column (the point-in-polygon test must not be fooled by a
  simplified edge); the display outline is simplified when it is served.
* **A place is in several things at once.** Nothing is merged here either — a
  ward, a city and a province all contain the same point, and the API answers
  with all of them.

Coverage is expressed as *targets* — a bbox or a kind (plus an optional
country) — and crawled round-robin (see ``app.crawler.scheduler``) so a single
tick never pulls a whole continent.

Run:  python -m app.crawler.cli.geo [--target "bbox:-80.3,43.6,-79.2,44.2"] [--boundaries]
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Text, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import whereq_cloud
from whereq_cloud import WhereqError

from app.core.config import settings
from app.crawler.upstream.whereq_cloud import (
    Throttle,
    call_with_retry,
    client as _client,
    shared_throttle,
)
from app.models.geo import GeoConcept, GeoPlace, GeoSyncState

logger = logging.getLogger(__name__)

#: The feed's source names.
SOURCE_OSM = "osm"
SOURCE_GEOBOUNDARIES = "geoboundaries"

#: The API caps a page at 200 rows.
PAGE_SIZE = 200


# ── coverage targets ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GeoTarget:
    """One area to crawl: a map bbox, or a kind (optionally within a country).

    ``kind`` is one of the feed's concepts ("ward", "municipality", …).
    """

    kind: str | None = None
    country: str | None = None
    source: str | None = None
    bbox: str | None = None

    @property
    def key(self) -> str:
        """Stable identity of this target (the sync-state primary key)."""
        parts = ["places"]
        if self.bbox:
            parts.append(f"bbox:{self.bbox}")
        else:
            if self.kind:
                parts.append(f"kind:{self.kind}")
            if self.country:
                parts.append(f"country:{self.country}")
            if self.source:
                parts.append(f"source:{self.source}")
        return ":".join(parts)

    @property
    def label(self) -> str:
        if self.bbox:
            return f"bbox {self.bbox}"
        bits = [b for b in (self.kind, self.country, self.source) if b]
        return " / ".join(bits) or "all"

    def api_filters(self) -> dict[str, Any]:
        """Query parameters for the whereq.cloud geography endpoint."""
        filters: dict[str, Any] = {}
        if self.kind:
            filters["kind"] = self.kind
        if self.country:
            filters["country"] = self.country
        if self.source:
            filters["source"] = self.source
        if self.bbox:
            filters["bbox"] = self.bbox
        return filters


#: A target in the settings string.
#:
#: The settings value is comma-separated, but a **bbox target contains commas
#: itself** — ``bbox:-80.3,43.6,-79.2,44.2`` is *one* target, not four. So the
#: string cannot simply be split on commas; the targets are pulled out with
#: this pattern instead.
_TARGET_RE = re.compile(
    r"""
    (?P<bbox>   bbox:\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+ )
    | (?P<kind>   kind:\s*[A-Za-z_]+ (?: :\s*[A-Za-z]{2} )? )
    | (?P<country> country:\s*[A-Za-z]{2} )
    | (?P<source>  source:\s*[A-Za-z_]+ )
    | (?P<bare>    [A-Za-z_]+ )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_target(spec: str) -> GeoTarget | None:
    """Parse a target spec.

    ``bbox:minLon,minLat,maxLon,maxLat`` | ``kind:<kind>`` |
    ``kind:<kind>:<country>`` | ``country:<CC>`` | ``source:<name>``.

    Returns None when the spec is unusable.
    """
    spec = (spec or "").strip()
    if not spec:
        return None

    low = spec.lower()
    if low.startswith("bbox:"):
        bbox = spec[5:].strip()
        parts = bbox.split(",")
        if len(parts) != 4 or not all(p.strip() for p in parts):
            logger.warning("ignoring malformed geo target %r (bbox needs 4 numbers)", spec)
            return None
        try:
            [float(p) for p in parts]
        except ValueError:
            logger.warning("ignoring malformed geo target %r (bbox needs 4 numbers)", spec)
            return None
        return GeoTarget(bbox=bbox)

    bits = [b.strip() for b in spec.split(":")]
    head = bits[0].lower()
    if head == "kind":
        kind = bits[1] if len(bits) > 1 and bits[1] else None
        country = bits[2] if len(bits) > 2 and bits[2] else None
        if not kind:
            logger.warning("ignoring geo target %r (kind needs a name)", spec)
            return None
        return GeoTarget(kind=kind, country=country.upper() if country else None)
    if head == "country":
        country = bits[1] if len(bits) > 1 and bits[1] else None
        if not country:
            logger.warning("ignoring geo target %r (country needs a code)", spec)
            return None
        return GeoTarget(country=country.upper())
    if head == "source":
        source = bits[1] if len(bits) > 1 and bits[1] else None
        if not source:
            logger.warning("ignoring geo target %r (source needs a name)", spec)
            return None
        return GeoTarget(source=source)

    # A bare kind, e.g. "ward".
    return GeoTarget(kind=spec)


def parse_targets(specs: str) -> list[GeoTarget]:
    """Every target in a comma-separated settings string.

    The comma is the separator *between* targets, but a bbox target carries
    commas of its own — so the targets are matched with a pattern rather than
    split on the commas.
    """
    out: list[GeoTarget] = []
    for match in _TARGET_RE.finditer(specs or ""):
        spec = match.group(0).strip()
        target = parse_target(spec)
        if target:
            out.append(target)
    return out


def configured_targets() -> list[GeoTarget]:
    """The coverage targets from ``GEO_CRAWL_TARGETS`` (deduped, ordered)."""
    seen: dict[str, GeoTarget] = {}
    for target in parse_targets(settings.GEO_CRAWL_TARGETS):
        if target.key not in seen:
            seen[target.key] = target
    return list(seen.values())


# ── API plumbing ────────────────────────────────────────────────────────────
# The throttle, the retry policy and the client live in
# ``app/crawler/upstream/whereq_cloud.py`` — the fuel crawl and the geography
# crawl share one whereq.cloud key and therefore one 30 requests/minute
# budget, so they must share one limiter (two would 429 each other).


# ── row mapping ─────────────────────────────────────────────────────────────
def _geometry_of(boundary: Any) -> dict | None:
    """The GeoJSON *geometry* out of a boundary response.

    The API answers with a FeatureCollection; the repo's PostGIS idiom
    (``ST_GeomFromGeoJSON``) wants the geometry itself, so the feature's
    geometry is what gets stored.

    A place whose outline arrives as several features is **merged** into one
    MultiPolygon — keeping only the first feature would silently drop the
    rest of the outline.
    """
    if not isinstance(boundary, dict):
        return None
    if boundary.get("type") == "FeatureCollection":
        features = boundary.get("features") or []
        geometries = [
            f.get("geometry") for f in features
            if isinstance(f, dict) and isinstance(f.get("geometry"), dict)
        ]
        if not geometries:
            return None
        if len(geometries) == 1:
            return geometries[0]
        logger.info("geo boundary has %d feature(s) — merging them", len(geometries))
        return _merge_geometries(geometries)
    if boundary.get("type") in ("Polygon", "MultiPolygon"):
        return boundary
    return None


def _merge_geometries(geometries: list[dict]) -> dict | None:
    """Several outlines → one MultiPolygon."""
    coordinates: list = []
    for geom in geometries:
        if geom.get("type") == "Polygon":
            coordinates.append(geom.get("coordinates") or [])
        elif geom.get("type") == "MultiPolygon":
            coordinates.extend(geom.get("coordinates") or [])
    if not coordinates:
        return None
    return {"type": "MultiPolygon", "coordinates": coordinates}


def place_to_row(place: dict) -> dict | None:
    """Map a whereq.cloud place to a ``geo_places`` row, or None if unusable."""
    uid = (place.get("uid") or "").strip()
    name = (place.get("name") or "").strip()
    kind = (place.get("kind") or "").strip()
    source = (place.get("source") or "").strip()
    if not uid or not name or not kind or not source:
        return None

    return {
        "uid": uid[:64],
        "kind": kind[:24],
        "kind_source": _clip(place.get("kind_source"), 24),
        "name": name[:255],
        "name_en": _clip(place.get("name_en"), 255),
        "name_zh": _clip(place.get("name_zh"), 255),
        "name_local": _clip(place.get("name_local"), 255),
        "official_name": _clip(place.get("official_name"), 255),
        "source": source[:24],
        "source_id": _clip(place.get("source_id"), 96),
        "source_url": _clip(place.get("source_url"), 512),
        "license": _clip(place.get("license"), 160),
        "raw_admin_level": _int_or_none(place.get("raw_admin_level")),
        "raw_place": _clip(place.get("raw_place"), 48),
        "raw_boundary": _clip(place.get("raw_boundary"), 48),
        "country_code": _clip(place.get("country_code"), 2),
        "province_code": _clip(place.get("province_code"), 8),
        "iso_code": _clip(place.get("iso_code"), 16),
        "ref": _clip(place.get("ref"), 48),
        "population": _int_or_none(place.get("population")),
        "population_date": _clip(place.get("population_date"), 16),
        "wikidata": _clip(place.get("wikidata"), 32),
        "wikipedia": _clip(place.get("wikipedia"), 255),
        "website": _clip(place.get("website"), 255),
        "capital": _clip(place.get("capital"), 160),
        "centroid_lon": _float_or_none(place.get("centroid_lon")),
        "centroid_lat": _float_or_none(place.get("centroid_lat")),
        "bbox_min_lon": _float_or_none(place.get("bbox_min_lon")),
        "bbox_min_lat": _float_or_none(place.get("bbox_min_lat")),
        "bbox_max_lon": _float_or_none(place.get("bbox_max_lon")),
        "bbox_max_lat": _float_or_none(place.get("bbox_max_lat")),
        "area_km2": _float_or_none(place.get("area_km2")),
        "has_boundary": bool(place.get("has_boundary")),
        "boundary_geojson": None,
        "geom": None,
    }


def _clip(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ── persistence ─────────────────────────────────────────────────────────────
async def upsert_places(db: AsyncSession, rows: list[dict], batch: int = 200) -> int:
    """Idempotent upsert by ``uid``. Returns rows written.

    The PostGIS geometry is computed in the same statement, so a crawl never
    needs a second pass over the table to rebuild it: the outline arrives as
    GeoJSON and ``ST_GeomFromGeoJSON`` turns it into geometry on the way in.

    The outline columns are **not** overwritten by a row that has no outline.
    A place crawl that only fetches the rows (no boundaries) must not destroy
    an outline another target already fetched — so the existing outline is
    kept (``coalesce``) unless the new row carries one.
    """
    written = 0
    for i in range(0, len(rows), batch):
        chunk = [dict(r) for r in rows[i:i + batch]]
        for item in chunk:
            item["geom"] = _geometry_expression(item.get("boundary_geojson"))
        stmt = pg_insert(GeoPlace).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GeoPlace.uid],
            set_={
                "kind": stmt.excluded.kind,
                "kind_source": stmt.excluded.kind_source,
                "name": stmt.excluded.name,
                "name_en": stmt.excluded.name_en,
                "name_zh": stmt.excluded.name_zh,
                "name_local": stmt.excluded.name_local,
                "official_name": stmt.excluded.official_name,
                "source": stmt.excluded.source,
                "source_id": stmt.excluded.source_id,
                "source_url": stmt.excluded.source_url,
                "license": stmt.excluded.license,
                "raw_admin_level": stmt.excluded.raw_admin_level,
                "raw_place": stmt.excluded.raw_place,
                "raw_boundary": stmt.excluded.raw_boundary,
                "country_code": stmt.excluded.country_code,
                "province_code": stmt.excluded.province_code,
                "iso_code": stmt.excluded.iso_code,
                "ref": stmt.excluded.ref,
                "population": stmt.excluded.population,
                "population_date": stmt.excluded.population_date,
                "wikidata": stmt.excluded.wikidata,
                "wikipedia": stmt.excluded.wikipedia,
                "website": stmt.excluded.website,
                "capital": stmt.excluded.capital,
                "centroid_lon": stmt.excluded.centroid_lon,
                "centroid_lat": stmt.excluded.centroid_lat,
                "bbox_min_lon": stmt.excluded.bbox_min_lon,
                "bbox_min_lat": stmt.excluded.bbox_min_lat,
                "bbox_max_lon": stmt.excluded.bbox_max_lon,
                "bbox_max_lat": stmt.excluded.bbox_max_lat,
                "area_km2": stmt.excluded.area_km2,
                "has_boundary": or_(
                    stmt.excluded.has_boundary,
                    # The flag must never contradict the geometry we hold: an
                    # outline we already have is an outline we have, whatever
                    # the feed says today.
                    func.coalesce(stmt.excluded.geom, GeoPlace.__table__.c.geom).is_not(None),
                ),
                # Keep the outline we already have unless this row brings one.
                "boundary_geojson": func.coalesce(
                    stmt.excluded.boundary_geojson, GeoPlace.__table__.c.boundary_geojson),
                "geom": func.coalesce(stmt.excluded.geom, GeoPlace.__table__.c.geom),
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
        written += len(chunk)
    await db.commit()
    return written


def _geometry_expression(geometry: dict | None):
    """The SQL that turns a GeoJSON geometry into a PostGIS MultiPolygon.

    ``ST_Multi`` normalises a Polygon into a MultiPolygon, so one shape fits
    the column whatever the source sent. The repo's idiom — ``ST_GeomFromGeoJSON``
    — is the same one the school catchments use.
    """
    if not geometry:
        return None
    return func.ST_Multi(
        func.ST_SetSRID(
            func.ST_GeomFromGeoJSON(cast(literal(json.dumps(geometry)), Text)), 4326)
    )


async def upsert_concepts(db: AsyncSession, concepts: list[dict]) -> int:
    """Store the vocabulary — one row per kind of place."""
    if not concepts:
        return 0
    values = [
        {
            "kind": str(c.get("kind"))[:24],
            "name": str(c.get("name") or c.get("kind"))[:64],
            "name_cn": _clip(c.get("name_cn"), 64),
            "description": _clip(c.get("description"), 2000),
            "description_cn": _clip(c.get("description_cn"), 2000),
            "rank": _int_or_none(c.get("rank")) or 0,
            "upstream_places": _int_or_none(c.get("places")) or 0,
        }
        for c in concepts
        if c.get("kind")
    ]
    if not values:
        return 0
    stmt = pg_insert(GeoConcept).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[GeoConcept.kind],
        set_={
            "name": stmt.excluded.name,
            "name_cn": stmt.excluded.name_cn,
            "description": stmt.excluded.description,
            "description_cn": stmt.excluded.description_cn,
            "rank": stmt.excluded.rank,
            "upstream_places": stmt.excluded.upstream_places,
        },
    )
    await db.execute(stmt)
    await db.commit()
    return len(values)


async def mark_state(
    db: AsyncSession,
    target: GeoTarget,
    *,
    places: int = 0,
    boundaries: int = 0,
    error: str | None = None,
) -> None:
    """Record the outcome of a target crawl."""
    now = datetime.now(timezone.utc)
    stmt = pg_insert(GeoSyncState).values(
        target_key=target.key,
        kind=target.kind,
        source=target.source,
        country=target.country,
        bbox=target.bbox,
        last_attempt_at=now,
        last_synced_at=now if error is None else None,
        place_count=places,
        boundary_count=boundaries,
        last_error=error,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[GeoSyncState.target_key],
        set_={
            "last_attempt_at": now,
            # A failed attempt keeps the last *successful* crawl — the old value
            # is the one in the table, not the one we tried to insert.
            "last_synced_at": (
                now if error is None else GeoSyncState.__table__.c.last_synced_at
            ),
            # A failed attempt keeps the counts of the last *successful*
            # crawl too — the row must not read "crawled, 0 places".
            "place_count": (
                places if error is None else GeoSyncState.__table__.c.place_count
            ),
            "boundary_count": (
                boundaries if error is None else GeoSyncState.__table__.c.boundary_count
            ),
            "last_error": error,
        },
    )
    await db.execute(stmt)
    await db.commit()


# ── the crawl itself ─────────────────────────────────────────────────────────
def fetch_places(
    client: whereq_cloud.Client, target: GeoTarget, throttle: Throttle | None = None
) -> list[dict]:
    """Every place matching the target, paging through the API.

    The API caps a page at 200 rows; the total comes back on the first page.
    """
    out: list[dict] = []
    offset = 0
    limit = min(PAGE_SIZE, settings.GEO_CRAWL_PAGE_SIZE)
    while True:
        if throttle:
            throttle.wait()
        page = call_with_retry(
            client.geo_places,
            attempts=settings.GEO_CRAWL_MAX_RETRIES,
            limit=limit, offset=offset, **target.api_filters())
        rows = page.get("data") or []
        if not rows:
            break
        out.extend(rows)
        if settings.GEO_CRAWL_MAX_PLACES and len(out) >= settings.GEO_CRAWL_MAX_PLACES:
            return out[:settings.GEO_CRAWL_MAX_PLACES]
        offset += len(rows)
        if page.get("count") is not None and offset >= page["count"]:
            break
    return out


def fetch_boundary(client: whereq_cloud.Client, uid: str) -> dict | None:
    """One place's outline, at full resolution."""
    try:
        boundary = call_with_retry(
            client.geo_boundary,
            attempts=settings.GEO_CRAWL_MAX_RETRIES,
            uid=uid)
    except WhereqError as exc:
        logger.warning("geo boundary %s failed: %s", uid, exc.message)
        return None
    return _geometry_of(boundary)


def fetch_concepts(client: whereq_cloud.Client) -> list[dict]:
    """The vocabulary — every concept, with the feed's own counts."""
    data = call_with_retry(
        client.geo_concepts, attempts=settings.GEO_CRAWL_MAX_RETRIES)
    return data.get("concepts") or []


async def crawl_target(
    db: AsyncSession,
    client: whereq_cloud.Client,
    target: GeoTarget,
    *,
    with_boundaries: bool = False,
) -> tuple[int, int]:
    """Crawl one target. Returns ``(places, boundaries)``.

    The place rows go up first, so a boundary is never attached to a place
    that is not there yet.

    The SDK calls are blocking, so they run in a thread — the crawler's event
    loop must keep ticking while a target is being pulled.
    """
    throttle = shared_throttle

    places = await asyncio.to_thread(fetch_places, client, target, throttle)
    rows = [r for r in (place_to_row(p) for p in places) if r]
    written = await upsert_places(db, rows)

    boundary_count = 0
    if with_boundaries:
        geometries = await asyncio.to_thread(
            _fetch_boundaries, client, rows, throttle)
        for row, geometry in geometries:
            row["boundary_geojson"] = geometry
            boundary_count += 1
        if boundary_count:
            await upsert_places(db, rows)

    await mark_state(db, target, places=written, boundaries=boundary_count)
    return written, boundary_count


def _fetch_boundaries(
    client: whereq_cloud.Client, rows: list[dict], throttle: Throttle
) -> list[tuple[dict, dict]]:
    """Fetch every place's outline — one API request per place, throttled."""
    out: list[tuple[dict, dict]] = []
    for row in rows:
        if not row["has_boundary"]:
            continue
        throttle.wait()
        geometry = fetch_boundary(client, row["uid"])
        if not geometry:
            continue
        out.append((row, geometry))
    return out


async def crawl_concepts(db: AsyncSession, client: whereq_cloud.Client) -> int:
    """Refresh the vocabulary."""
    concepts = await asyncio.to_thread(fetch_concepts, client)
    return await upsert_concepts(db, concepts)


# ── due-ness ────────────────────────────────────────────────────────────────
async def targets_due(db: AsyncSession) -> list[GeoTarget]:
    """The targets whose refresh interval has elapsed.

    A target with no state row is due (a fresh database crawls everything on
    the first pass).
    """
    now = datetime.now(timezone.utc)
    interval = settings.GEO_CRAWL_INTERVAL_HOURS
    due: list[GeoTarget] = []
    for target in configured_targets():
        row = (
            await db.execute(
                select(GeoSyncState).where(GeoSyncState.target_key == target.key)
            )
        ).scalar_one_or_none()
        if row is None or row.last_synced_at is None:
            due.append(target)
            continue
        age_h = (now - row.last_synced_at).total_seconds() / 3600
        if age_h >= interval:
            due.append(target)
    return due


async def count_places_async(db: AsyncSession) -> int:
    """How many places we hold."""
    return (await db.execute(select(func.count()).select_from(GeoPlace))).scalar_one()

async def concepts_with_counts(db: AsyncSession) -> list[dict]:
    """The vocabulary with *our* counts beside the feed's own.

    The feed's counts describe the whole dataset; ours describe what this
    installation actually holds, which is what the UI can draw.
    """
    ours = dict(
        (await db.execute(
            select(GeoPlace.kind, func.count(GeoPlace.uid)).group_by(GeoPlace.kind)
        )).all()
    )
    rows = (await db.execute(select(GeoConcept).order_by(GeoConcept.rank))).scalars().all()
    out = []
    for c in rows:
        out.append({
            "kind": c.kind,
            "name": c.name,
            "name_cn": c.name_cn,
            "description": c.description,
            "description_cn": c.description_cn,
            "rank": c.rank,
            "places": ours.get(c.kind, 0),
            "upstream_places": c.upstream_places,
        })
    return out


async def run_crawl(db: AsyncSession, targets: list[GeoTarget], *, with_boundaries: bool = False) -> dict:
    """Crawl a list of targets with one client, reporting what happened."""
    client = _client()
    report = {"places": 0, "boundaries": 0, "targets": [], "concepts": 0, "errors": []}
    try:
        report["concepts"] = await crawl_concepts(db, client)
        for target in targets:
            try:
                places, boundaries = await crawl_target(
                    db, client, target, with_boundaries=with_boundaries)
                report["places"] += places
                report["boundaries"] += boundaries
                report["targets"].append({
                    "target": target.label, "key": target.key,
                    "places": places, "boundaries": boundaries,
                })
                logger.info("geo crawl %s — %d place(s), %d boundary(ies)",
                            target.label, places, boundaries)
            except Exception as exc:  # noqa: BLE001 - one bad target must not stop the rest
                logger.exception("geo crawl %s failed", target.label)
                # The session is in a failed transaction — without a rollback
                # the mark below would raise too, and the remaining targets
                # would be skipped.
                await db.rollback()
                await mark_state(db, target, error=str(exc)[:500])
                report["errors"].append({"target": target.label, "error": str(exc)[:300]})
    finally:
        client.close()
    return report
