"""Smart multi-provider geocoding manager.

Tries configured providers in priority order (free tiers first, Google last),
skipping any that are unconfigured or over their persisted daily/monthly quota.
Results — and genuine misses — are cached in ``geocode_cache`` so repeat
lookups never consume quota. Per-provider usage is persisted in
``geocode_provider_usage`` so quotas hold across separate crawler processes.

The crawler path (``geocode``) always runs the chain in configured order, so
the paid Google provider is the last resort. The Maps service path
(``geocode_detailed``) follows the same rule; a caller that needs Google's
component quality can ask for it explicitly (``prefer_google=True``) rather
than the service silently paying for it on every request.
"""

from __future__ import annotations

import hashlib
import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.local_content import GeocodeCache, GeocodeProviderUsage
from app.services.geocoding.base import AddressComponents, GeocodeProvider, GeoResult
from app.services.geocoding.places import GooglePlacesProvider, Suggestion
from app.services.geocoding.providers import PROVIDER_CLASSES

logger = logging.getLogger(__name__)

_providers: list[GeocodeProvider] | None = None


def _provider_chain() -> list[GeocodeProvider]:
    """Build (once) the ordered provider chain from settings."""
    global _providers
    if _providers is not None:
        return _providers
    chain: list[GeocodeProvider] = []
    for name in (s.strip() for s in settings.GEOCODE_PROVIDER_ORDER.split(",")):
        if not name:
            continue
        cls = PROVIDER_CLASSES.get(name)
        if cls is None:
            logger.warning("Unknown geocoding provider in order: %r", name)
            continue
        chain.append(cls(settings))
    _providers = chain
    return chain


def _normalize(query: str) -> str:
    return " ".join(query.lower().split())


def _bias_for(country: str | None, region: str | None = None) -> str | None:
    """Resolve the country bias every provider receives.

    The ``region`` slot is a **country code / ccTLD**, not a province: it is
    Nominatim's ``countrycodes`` and Google's ``region`` parameter. It must
    therefore follow the country being looked up — a fixed ``ca`` bias would
    silently restrict a US lookup to Canadian results (and cache them under
    the Canadian key).

    An explicit ``region`` always wins; otherwise the requested country is
    used, with ``GEOCODE_REGION_BIAS`` as the last-resort fallback.
    """
    if region:
        return region.lower()
    if country:
        return country.strip().lower()
    return settings.GEOCODE_REGION_BIAS or None


def _query_hash(query: str, region: str | None) -> str:
    return hashlib.sha256(f"{_normalize(query)}|{(region or '').lower()}".encode()).hexdigest()


async def _usage_count(db: AsyncSession, provider: str, period: str) -> int:
    return (await db.execute(
        select(GeocodeProviderUsage.count)
        .where(GeocodeProviderUsage.provider == provider, GeocodeProviderUsage.period == period)
    )).scalar_one_or_none() or 0


async def _increment_usage(db: AsyncSession, provider: str, period: str, by: int = 1) -> None:
    stmt = pg_insert(GeocodeProviderUsage).values(provider=provider, period=period, count=by)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_geocode_usage",
        set_={"count": GeocodeProviderUsage.count + by, "updated_at": func.now()},
    )
    await db.execute(stmt)
    await db.commit()


async def _mark_exhausted(db: AsyncSession, provider: str, period: str, limit: int) -> None:
    """Pin usage to the quota limit (e.g. after a 429) to skip it this period."""
    stmt = pg_insert(GeocodeProviderUsage).values(provider=provider, period=period, count=limit)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_geocode_usage",
        set_={"count": limit, "updated_at": func.now()},
    )
    await db.execute(stmt)
    await db.commit()


async def geocode(db: AsyncSession, query: str, *,
                  region: str | None = None, country: str | None = None) -> GeoResult | None:
    """Geocode free text via the provider chain. Returns None if unresolved.

    ``components`` is intentionally not part of the public signature any more;
    country bias is passed explicitly so every provider can honor it.
    """
    query = (query or "").strip()
    if not query:
        return None
    country = country or settings.GEOCODE_COUNTRY
    region = _bias_for(country, region)
    qhash = _query_hash(query, region)

    # 1. cache (hit or cached miss)
    cached = (await db.execute(
        select(GeocodeCache).where(GeocodeCache.query_sha256 == qhash))).scalar_one_or_none()
    if cached is not None:
        cached.hit_count = (cached.hit_count or 0) + 1
        await db.commit()
        if cached.latitude is None or cached.longitude is None:
            return None
        return GeoResult(cached.latitude, cached.longitude, cached.formatted_address,
                         cached.confidence or 0.5, cached.provider)

    # 2. provider chain
    found: GeoResult | None = None
    answered = False  # did any provider actually complete a call?
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for p in _provider_chain():
            if not p.is_configured():
                continue
            period = p.period_key()
            used = await _usage_count(db, p.name, period)
            if used >= p.quota_limit():
                logger.debug("Skip %s: quota %d/%d for %s", p.name, used, p.quota_limit(), period)
                continue
            await p.respect_rate_limit()
            try:
                res = await p.geocode(client, query, region=region, country=country)
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    logger.warning("%s rate/quota limited (429) — marking exhausted", p.name)
                    await _mark_exhausted(db, p.name, period, p.quota_limit())
                else:
                    logger.warning("%s HTTP error for %r: %s", p.name, query, exc)
                continue
            except Exception as exc:
                logger.warning("%s failed for %r: %s", p.name, query, exc)
                continue
            await _increment_usage(db, p.name, period)
            answered = True
            if res:
                res.provider = p.name
                found = res
                logger.debug("Geocoded %r via %s -> (%.5f,%.5f)", query, p.name, res.lat, res.lng)
                break
            # zero-results → try the next provider

    # 3. cache the outcome (skip caching when nothing actually answered, so a
    #    later run can retry once quota/config allows)
    if found or answered:
        db.add(GeocodeCache(
            query_sha256=qhash, query=query,
            latitude=found.lat if found else None,
            longitude=found.lng if found else None,
            formatted_address=found.formatted_address if found else None,
            confidence=found.confidence if found else None,
            provider=found.provider if found else None,
        ))
        await db.commit()
    return found


# ═══════════════════════════════════════════════════════════════════════════
# Maps service (/api/maps/v1) — detailed geocode / reverse / autocomplete
#
# These return normalized §4 components + place_id + location_type, cache them
# in ``geocode_cache.raw``, and run the same free-tiers-first chain as the
# crawler. Google is promoted to the front only when a caller explicitly asks
# for it (``prefer_google``) — the service does not spend paid quota on the
# consumer's behalf by default.
# ═══════════════════════════════════════════════════════════════════════════

def _ordered_chain(google_preferred: bool) -> list[GeocodeProvider]:
    """Provider chain, optionally with Google promoted to the front."""
    chain = _provider_chain()
    if not google_preferred:
        return chain
    google = [p for p in chain if p.name == "google"]
    rest = [p for p in chain if p.name != "google"]
    return google + rest


def _google_provider() -> GeocodeProvider | None:
    return next((p for p in _provider_chain() if p.name == "google"), None)


def configured_providers() -> list[str]:
    """Names of providers that currently have the config they need."""
    return [p.name for p in _provider_chain() if p.is_configured()]


def providers_available() -> bool:
    return bool(configured_providers())


def _detail_hash(query: str, region: str | None) -> str:
    return hashlib.sha256(
        f"detail|{_normalize(query)}|{(region or '').lower()}".encode()).hexdigest()


def _reverse_hash(lat: float, lng: float, lang: str) -> str:
    # Round to ~6dp (~0.1m) so near-identical pins share a cache entry.
    return hashlib.sha256(f"reverse|{lat:.6f}|{lng:.6f}|{lang}".encode()).hexdigest()


def _placeid_hash(place_id: str) -> str:
    return hashlib.sha256(f"place_id|{place_id}".encode()).hexdigest()


def _row_to_result(row: GeocodeCache) -> GeoResult | None:
    if row.latitude is None or row.longitude is None:
        return None
    raw = row.raw or {}
    return GeoResult(
        row.latitude, row.longitude, row.formatted_address,
        row.confidence or 0.5, row.provider,
        components=AddressComponents.from_dict(raw.get("components")),
        place_id=raw.get("place_id"),
        location_type=raw.get("location_type"),
    )


async def _cache_lookup(db: AsyncSession, qhash: str) -> GeocodeCache | None:
    row = (await db.execute(
        select(GeocodeCache).where(GeocodeCache.query_sha256 == qhash))).scalar_one_or_none()
    if row is not None:
        row.hit_count = (row.hit_count or 0) + 1
        await db.commit()
    return row


async def _cache_store(db: AsyncSession, qhash: str, query: str,
                       found: GeoResult | None) -> None:
    raw = None
    if found:
        raw = {
            "components": found.components.as_dict() if found.components else None,
            "place_id": found.place_id,
            "location_type": found.location_type,
        }
    db.add(GeocodeCache(
        query_sha256=qhash, query=query,
        latitude=found.lat if found else None,
        longitude=found.lng if found else None,
        formatted_address=found.formatted_address if found else None,
        confidence=found.confidence if found else None,
        provider=found.provider if found else None,
        raw=raw,
    ))
    await db.commit()


async def _attempt(db: AsyncSession, p: GeocodeProvider, client: httpx.AsyncClient, fn):
    """Run one provider call (``fn(p, client)``) with quota + rate-limit + usage
    accounting. Returns ``(result, answered)``; ``answered`` is True when the
    provider actually completed a call (so a miss can be cached)."""
    if not p.is_configured():
        return None, False
    period = p.period_key()
    used = await _usage_count(db, p.name, period)
    if used >= p.quota_limit():
        logger.debug("Skip %s: quota %d/%d for %s", p.name, used, p.quota_limit(), period)
        return None, False
    await p.respect_rate_limit()
    try:
        res = await fn(p, client)
    except NotImplementedError:
        return None, False
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            logger.warning("%s rate/quota limited (429) — marking exhausted", p.name)
            await _mark_exhausted(db, p.name, period, p.quota_limit())
        else:
            logger.warning("%s HTTP error: %s", p.name, exc)
        return None, False
    except Exception as exc:
        logger.warning("%s failed: %s", p.name, exc)
        return None, False
    await _increment_usage(db, p.name, period)
    return res, True


async def geocode_detailed(
    db: AsyncSession, *,
    q: str | None = None,
    place_id: str | None = None,
    region: str | None = None,
    country: str | None = None,
    lang: str = "en",
    session: str | None = None,
    google_preferred: bool | None = None,
) -> tuple[GeoResult | None, bool]:
    """Resolve a full address / place to coordinates + §4 components.

    Returns ``(result, cached)``; ``result.provider`` names the source provider.
    Pass ``place_id`` (from /autocomplete) or free-text ``q``.
    """
    google_preferred = (settings.MAPS_GEOCODE_GOOGLE_PREFERRED
                        if google_preferred is None else google_preferred)
    country = country or settings.GEOCODE_COUNTRY
    region = _bias_for(country, region)

    if place_id:
        return await _resolve_place_id(db, place_id, lang=lang, session=session)

    q = (q or "").strip()
    if not q:
        return None, False
    qhash = _detail_hash(q, region)

    cached = await _cache_lookup(db, qhash)
    if cached is not None:
        return _row_to_result(cached), True

    found: GeoResult | None = None
    answered = False
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for p in _ordered_chain(google_preferred):
            res, ok = await _attempt(
                db, p, client,
                lambda pr, c: pr.geocode(c, q, region=region, country=country))
            answered = answered or ok
            if res:
                res.provider = p.name
                found = res
                break

    if found or answered:
        await _cache_store(db, qhash, q, found)
    return found, False


async def _resolve_place_id(
    db: AsyncSession, place_id: str, *, lang: str, session: str | None,
) -> tuple[GeoResult | None, bool]:
    """Resolve a place ref from /autocomplete to full coordinates + components.

    v1 resolves Google place_ids via Place Details; non-Google refs (e.g. the
    ``osm:`` refs from free providers) are not resolvable here yet.
    """
    qhash = _placeid_hash(place_id)
    cached = await _cache_lookup(db, qhash)
    if cached is not None:
        return _row_to_result(cached), True

    google = _google_provider()
    if place_id.startswith("osm:") or google is None:
        return None, False

    found: GeoResult | None = None
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        res, _ = await _attempt(
            db, google, client,
            lambda pr, c: pr.place_details(c, place_id, lang=lang, session=session))
        if res:
            res.provider = google.name
            found = res

    if found:
        await _cache_store(db, qhash, place_id, found)
    return found, False


async def reverse_geocode(
    db: AsyncSession, lat: float, lng: float, *,
    lang: str = "en", google_preferred: bool | None = None,
) -> tuple[GeoResult | None, bool]:
    """Reverse geocode a coordinate to the nearest address (§4 components)."""
    google_preferred = (settings.MAPS_GEOCODE_GOOGLE_PREFERRED
                        if google_preferred is None else google_preferred)
    qhash = _reverse_hash(lat, lng, lang)

    cached = await _cache_lookup(db, qhash)
    if cached is not None:
        return _row_to_result(cached), True

    found: GeoResult | None = None
    answered = False
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for p in _ordered_chain(google_preferred):
            if not p.supports_reverse():
                continue
            res, ok = await _attempt(
                db, p, client,
                lambda pr, c: pr.reverse(c, lat, lng, lang=lang))
            answered = answered or ok
            if res:
                res.provider = p.name
                found = res
                break

    if found or answered:
        await _cache_store(db, qhash, f"{lat:.6f},{lng:.6f}", found)
    return found, False


async def autocomplete(
    db: AsyncSession, q: str, *,
    country: str | None = None,
    limit: int = 5,
    proximity: tuple[float, float] | None = None,
    session: str | None = None,
    lang: str = "en",
) -> tuple[list[Suggestion], str | None]:
    """Address autocomplete (Google Places). Predictions are NOT cached (ToS).

    Returns ``(suggestions, provider)``; provider is None when unconfigured
    (caller should surface 503).
    """
    provider = GooglePlacesProvider(settings)
    if not provider.is_configured():
        return [], None

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        try:
            suggestions = await provider.autocomplete(
                client, q, country=country, limit=limit,
                proximity=proximity, session=session, lang=lang)
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                raise
            logger.warning("places autocomplete HTTP error: %s", exc)
            raise
    # Track usage for observability under a distinct bucket (separate billing
    # from Geocoding); no hard global cap here — per-key quota governs cost.
    await _increment_usage(db, "google_places", provider_period_month())
    return suggestions, provider.name


def provider_period_month() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m")
