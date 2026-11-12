"""Normalization pipeline: RawItem -> persisted LocalContent.

Per item:  dedup -> classify -> extract location -> geocode -> retention -> upsert.
Each item is processed in isolation so one bad article never aborts a run.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.base import RawItem
from app.models.local_content import LocalContent, LocalContentTag, NewsSource
from app.services.classify import classify
from app.services.datetime_extract import extract_event_datetime
from app.services.geo_gazetteer import city_center, detect_city, haversine_km
from app.services.geocoding import geocode
from app.services.location_extract import (
    extract_locations,
    geocode_plans,
    is_self_locating,
)

logger = logging.getLogger(__name__)

# A precise geocode further than these from the city centre is treated as a
# cross-city mismatch (e.g. a same-named street in another municipality) and
# **rejected** — it is not a location for this item, so the item is left
# unplaced rather than pinned somewhere it is not. Strict when the city was
# explicitly named in the text (strong signal); lenient when we only have the
# source's default region, so a legitimately far-but-correct result is kept.
_CITY_GUARD_KM = 20.0
_REGION_GUARD_KM = 60.0

# Incident categories are short-lived; retention windows (days) by bucket.
_INCIDENT_CATS = {"accident", "crime", "fire", "weather", "transportation"}
_RETENTION_DAYS = {
    "incident": 2,
    "event": 2,       # after the event ends
    "story": 90,
    "topic": 30,
    "default": 7,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _content_hash(title: str, summary: str | None, url: str | None) -> str:
    return hashlib.sha256(f"{title}\n{summary or ''}\n{url or ''}".encode("utf-8")).hexdigest()


def _dedup_key(title: str, publish: datetime | None) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    day = (publish or _now()).strftime("%Y%m%d")
    return hashlib.sha256(f"{norm}|{day}".encode("utf-8")).hexdigest()[:32]


def compute_expiry(content_type: str, category: str, publish: datetime | None,
                   event_time: datetime | None, event_end_time: datetime | None) -> datetime:
    base = publish or _now()
    if content_type == "event":
        end = event_end_time or event_time or base
        return end + timedelta(days=_RETENTION_DAYS["event"])
    if category in _INCIDENT_CATS:
        return base + timedelta(days=_RETENTION_DAYS["incident"])
    if content_type == "story":
        return base + timedelta(days=_RETENTION_DAYS["story"])
    if content_type == "topic":
        return base + timedelta(days=_RETENTION_DAYS["topic"])
    return base + timedelta(days=_RETENTION_DAYS["default"])


async def _find_existing(db: AsyncSession, source: NewsSource, raw: RawItem) -> LocalContent | None:
    conds = []
    if raw.external_id:
        conds.append((LocalContent.source_id == source.id) & (LocalContent.external_id == raw.external_id))
    if raw.url:
        conds.append(LocalContent.source_url == raw.url)
    if not conds:
        return None
    return (await db.execute(select(LocalContent).where(or_(*conds)).limit(1))).scalar_one_or_none()


def _resolve_position(geo, center: tuple[float, float] | None, guard_km: float,
                      base_conf: float, cls_confidence: float):
    """Decide where an item goes from its geocode result.

    Returns ``(lat, lng, status, source, confidence)``.

    An item whose location could not be resolved gets **no** position. It used
    to be dropped at the detected city centre so it would still appear on the
    map, but a pin there claims a specific place the item is not at — and
    thousands of them stacked on one point made the map lie about where
    things happened. The city stays on the row as ``city``: the item is known
    to be about that city, just not to be at a known spot inside it.

    A geocode that lands implausibly far from the detected city (the
    same-named street in another municipality) is **rejected**, not snapped
    to the centre — it is not a location for this item either.
    """
    if geo is None:
        # No provider answered with a result.
        return None, None, "failed", None, round(cls_confidence, 3)
    if center and haversine_km(center, (geo.lat, geo.lng)) > guard_km:
        # Cross-city mismatch: the result is not a location for this item.
        return (None, None, "rejected", None,
                round(min(0.5, 0.3 + 0.2 * cls_confidence), 3))
    return (geo.lat, geo.lng, "ok", geo.provider,
            round(min(0.99, base_conf * geo.confidence + 0.1 * cls_confidence), 3))


def _guard_for(plan, *, detected: bool, story_city: str | None):
    """The reference point and radius a geocode must satisfy.

    The guard is measured from the **story's** city, not from the place's own
    municipality: the question the guard answers is "is this where the story
    is?", not "where does this place sit?".  A story about Canada that
    happens to mention a Toronto university is not a Toronto story.

    A curated place gets the wider regional allowance, because it names a
    specific, unambiguous venue — a Brampton mall 34 km from downtown Toronto
    is still the right answer for a GTA story, while a London (Ontario)
    university is not the answer for a Toronto one.
    """
    center = city_center(story_city)
    if plan.place_city:
        return center, _REGION_GUARD_KM
    return center, (_CITY_GUARD_KM if detected else _REGION_GUARD_KM)


def _location_plans(title: str, summary: str | None, description: str | None, *,
                    city: str | None, province: str | None,
                    country: str | None = "Canada") -> list:
    """The geocoding plans for one item, best first.

    The extractor reads the **whole article** — a street address or a venue
    usually appears deep in the text, never in the headline — while the city
    detection (done by the caller) reads the title and the summary only,
    because the dateline at the top of a wire story is the strongest signal
    there is and the rest of the article is full of places merely *mentioned*.
    """
    body = "\n".join(t for t in (summary, description) if t)
    return geocode_plans(
        extract_locations(title, body),
        city=city, province=province, country=country,
    )


async def process_item(db: AsyncSession, source: NewsSource, raw: RawItem,
                       *, dry_run: bool = False) -> str:
    """Process one RawItem. Returns: created | updated | duplicate | skipped."""
    title = raw.title.strip()
    if not title:
        return "skipped"

    chash = _content_hash(title, raw.summary, raw.url)

    # 1. exact dedup (same source+external_id or same url)
    existing = await _find_existing(db, source, raw)
    if existing is not None:
        if existing.content_sha256 == chash:
            return "duplicate"
        # content changed → refresh mutable display fields (keep geocode result)
        existing.title = title
        existing.summary = raw.summary
        existing.description = raw.content
        existing.image_url = raw.image_url or existing.image_url
        existing.publish_time = raw.published or existing.publish_time
        existing.content_sha256 = chash
        existing.updated_at = _now()
        if not dry_run:
            await db.commit()
        return "updated"

    # 2. classify
    cls = classify(title, raw.summary or raw.content, default_type=source.default_type or "news")
    category = cls.category if cls.category != "other" else (source.default_category or "other")
    content_type = (source.default_type if source.default_type and source.default_type != "news"
                    else cls.content_type)

    # 3. location extraction + geocoding
    #
    # Detect the municipality the story is actually about (title preferred) so
    # the geocode query resolves in the right city — and so we display that
    # city, not the source's blanket default. Falls back to the source default.
    # City detection reads the title and the summary only: the dateline at the
    # top of a wire story is the strongest signal there is, and the rest of the
    # article is full of places merely *mentioned*.
    detect_text = raw.summary or raw.content
    detected = detect_city(title, detect_text)
    detected_city = detected or source.default_city

    lat = lng = None
    geocode_status, geocode_source = "none", None
    confidence = cls.confidence
    plans = _location_plans(
        title, raw.summary, raw.content,
        city=detected_city, province=source.default_province, country="Canada",
    )
    for plan in plans:
        # With no city detected the story's location is unknown, so only
        # evidence that stands on its own may place it: an address, an
        # intersection, a highway, or a curated place with its own
        # municipality.  A bare street name could be the same-named street
        # in another province entirely.
        if not detected and not is_self_locating(plan):
            continue

        # The guard is measured from the story's city.
        center, guard_km = _guard_for(
            plan, detected=detected, story_city=detected_city)

        if not dry_run:
            geo = await geocode(
                db, plan.query,
                region=(source.default_country or "ca").lower(),
                country=source.default_country or "CA",
            )
            lat, lng, geocode_status, geocode_source, confidence = _resolve_position(
                geo, center, guard_km, plan.confidence, cls.confidence)
            if lat is not None:
                # The first candidate that survives the guard wins; the rest
                # are fallbacks for when it does not.
                break

    # No fallback to the city centre: an item we could not place gets no
    # position at all (see _resolve_position). It keeps its city as metadata
    # and stays searchable — it just does not get a pin it does not deserve.

    publish = raw.published
    # For events, parse an explicit start/end from the text; fall back to the
    # publish time. News/stories/topics use publish time as the "when".
    event_time, event_end_time = publish, None
    if content_type == "event":
        ev = extract_event_datetime(title, raw.summary or raw.content,
                                    base_year=publish.year if publish else None)
        if ev:
            event_time, event_end_time = ev.start, ev.end
            confidence = round(max(confidence, ev.confidence), 3)
    expires_at = compute_expiry(content_type, category, publish, event_time, event_end_time)

    # 4. near-duplicate guard (same story across sources / re-published)
    dkey = _dedup_key(title, publish)
    near = (await db.execute(
        select(LocalContent.id).where(
            LocalContent.dedup_key == dkey, LocalContent.status == "active").limit(1)
    )).scalar_one_or_none()
    if near is not None:
        return "duplicate"

    if dry_run:
        return "created"

    # 5. insert
    lc = LocalContent(
        source_id=source.id,
        type=content_type, category=category,
        title=title, summary=raw.summary, description=raw.content,
        source_name=source.name, source_url=raw.url, external_id=raw.external_id,
        event_time=event_time, event_end_time=event_end_time, publish_time=publish,
        latitude=lat, longitude=lng,
        address=None, city=detected_city,
        province=source.default_province, country=source.default_country,
        geocode_status=geocode_status, geocode_source=geocode_source,
        confidence_score=confidence, status="active",
        image_url=raw.image_url, expires_at=expires_at,
        content_sha256=chash, dedup_key=dkey, raw=raw.raw or None,
    )
    if lat is not None and lng is not None:
        lc.geom = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    db.add(lc)
    await db.flush()
    for tag in cls.tags:
        db.add(LocalContentTag(content_id=lc.id, tag=tag))
    await db.commit()
    return "created"


async def retention_expiry(db: AsyncSession) -> int:
    """Flip expired active rows to status='expired'. Returns rows affected."""
    from sqlalchemy import update
    res = await db.execute(
        update(LocalContent)
        .where(LocalContent.status == "active", LocalContent.expires_at < _now())
        .values(status="expired")
    )
    await db.commit()
    return res.rowcount or 0
