"""WhereQ Maps service API — /api/maps/v1 (spec §3).

A keyed data API consumed server-to-server by other whereq-family apps. Auth is
an opaque per-consumer key (Bearer wq_…); see ``app/maps/auth.py``. Phase 0
(keys/quota/usage/healthz) + Phase 1 (autocomplete/geocode/reverse) are live
here; /route + /matrix land in later phases.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_staff
from app.maps import staticmap as sm
from app.maps.auth import require_maps_key
from app.maps.errors import MapsError
from app.maps.keys import create_consumer, list_consumers, revoke_consumer
from app.maps.usage import usage_tracker
from app.models.maps import MAPS_SCOPES, MapsApiConsumer, MapsApiUsage
from app.schemas.maps import MatrixRequest, RouteRequest
from app.services import routing
from app.services.geocoding import manager
from app.services.geocoding.base import GeoResult

router = APIRouter(prefix="/maps/v1", tags=["maps"])

_ATTR = settings.MAPS_ATTRIBUTION


# ── serialization ────────────────────────────────────────────────────────────
def _result_json(r: GeoResult) -> dict:
    return {
        "formatted": r.formatted_address,
        "lat": r.lat,
        "lng": r.lng,
        "components": r.components.as_dict() if r.components else None,
        "place_id": r.place_id,
        "confidence": round(r.confidence, 2) if r.confidence is not None else None,
        "location_type": r.location_type,
    }


def _parse_proximity(proximity: str | None) -> tuple[float, float] | None:
    if not proximity:
        return None
    try:
        lat_s, lng_s = proximity.split(",")
        return float(lat_s), float(lng_s)
    except (ValueError, AttributeError):
        raise MapsError(400, "invalid_request", "proximity must be 'lat,lng'")


def _resolve_country(country: str | None) -> tuple[str, str]:
    """Resolve the requested country and the provider bias that goes with it.

    Returns ``(country, bias)`` where *country* is the ISO code and *bias* is
    the ccTLD every provider receives (Nominatim's ``countrycodes``, Google's
    ``region``). The bias follows the country the caller asked for — a fixed
    ``ca`` bias would restrict a US lookup to Canadian results.
    """
    if country and country.strip():
        c = country.strip().lower()
        return c, c
    return settings.GEOCODE_COUNTRY, (settings.GEOCODE_REGION_BIAS or settings.GEOCODE_COUNTRY).lower()


# ── health ───────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "providers": manager.configured_providers(), "version": "maps/v1"}


# ── autocomplete ─────────────────────────────────────────────────────────────
@router.get("/autocomplete")
async def autocomplete(
    request: Request,
    q: str = Query(..., min_length=3),
    country: str | None = Query("ca"),
    limit: int = Query(5, ge=1, le=10),
    proximity: str | None = Query(None),
    session: str | None = Query(None),
    lang: str = Query("en"),
    db: AsyncSession = Depends(get_db),
    consumer: MapsApiConsumer = Depends(require_maps_key("autocomplete")),
) -> dict:
    prox = _parse_proximity(proximity)
    async with usage_tracker(db, consumer.id, "autocomplete") as usage:
        try:
            suggestions, provider = await manager.autocomplete(
                db, q, country=country, limit=limit, proximity=prox, session=session, lang=lang)
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                raise MapsError(429, "rate_limited", "Upstream provider rate-limited",
                                retry_after=60)
            raise MapsError(502, "upstream_error", "Autocomplete provider request failed")
        except httpx.HTTPError:
            # e.g. Google returns HTTP 200 with status=REQUEST_DENIED (Places API not
            # enabled / key restricted) — surface as a clean upstream error, not 500.
            raise MapsError(502, "upstream_error", "Autocomplete provider request failed")
        if provider is None:
            raise MapsError(503, "unavailable", "Autocomplete provider is not configured")

        usage.provider = provider or "google_places"
        return {
            "results": [
                {
                    "id": s.id,
                    "primary": s.primary,
                    "secondary": s.secondary,
                    "formatted": s.formatted,
                    "lat": None, "lng": None, "components": None,
                }
                for s in suggestions
            ],
            "session": session,
            "provider": provider,
            "attribution": _ATTR,
        }


# ── geocode ──────────────────────────────────────────────────────────────────
@router.get("/geocode")
async def geocode(
    request: Request,
    q: str | None = Query(None),
    place_id: str | None = Query(None),
    country: str | None = Query(None),
    session: str | None = Query(None),
    lang: str = Query("en"),
    prefer_google: bool = Query(
        False, description="Use Google first for the cleanest §4 components "
                           "(paid; the default chain is free-tiers-first)"),
    db: AsyncSession = Depends(get_db),
    consumer: MapsApiConsumer = Depends(require_maps_key("geocode")),
) -> dict:
    if not q and not place_id:
        raise MapsError(400, "invalid_request", "One of 'q' or 'place_id' is required")

    resolved_country, bias = _resolve_country(country)
    async with usage_tracker(db, consumer.id, "geocode") as usage:
        result, cached = await manager.geocode_detailed(
            db, q=q, place_id=place_id, country=resolved_country, region=bias,
            lang=lang, session=session, google_preferred=prefer_google)

        if result is None:
            if not manager.providers_available():
                raise MapsError(503, "unavailable", "No geocoding provider is available")
            usage.provider = "miss"
            raise MapsError(404, "not_found", "No match for the given address")

        usage.provider = "cache" if cached else (result.provider or "unknown")
        return {
            "result": _result_json(result),
            "provider": result.provider,
            "cached": cached,
            "attribution": _ATTR,
        }


# ── reverse ──────────────────────────────────────────────────────────────────
@router.get("/reverse")
async def reverse(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    lang: str = Query("en"),
    prefer_google: bool = Query(
        False, description="Use Google first for the cleanest §4 components "
                           "(paid; the default chain is free-tiers-first)"),
    db: AsyncSession = Depends(get_db),
    consumer: MapsApiConsumer = Depends(require_maps_key("reverse")),
) -> dict:
    async with usage_tracker(db, consumer.id, "reverse") as usage:
        result, cached = await manager.reverse_geocode(
            db, lat, lng, lang=lang, google_preferred=prefer_google)

        if result is None:
            if not manager.providers_available():
                raise MapsError(503, "unavailable", "No reverse-geocoding provider is available")
            usage.provider = "miss"
            raise MapsError(404, "not_found", "No address for the given coordinate")

        usage.provider = "cache" if cached else (result.provider or "unknown")
        return {
            "result": _result_json(result),
            "provider": result.provider,
            "cached": cached,
            "attribution": _ATTR,
        }


# ── route (Phase 2) ──────────────────────────────────────────────────────────
@router.post("/route")
async def route(
    payload: RouteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    consumer: MapsApiConsumer = Depends(require_maps_key("route")),
) -> dict:
    mode = (payload.mode or "driving").lower()
    if mode not in routing.VALID_MODES:
        raise MapsError(400, "invalid_request", "mode must be driving | walking | cycling")

    async with usage_tracker(db, consumer.id, "route") as usage:
        try:
            result, cached = await routing.route(
                db,
                origin=(payload.origin.lat, payload.origin.lng),
                destination=(payload.destination.lat, payload.destination.lng),
                mode=mode,
                departure_time=payload.departure_time,
                alternatives=payload.alternatives,
            )
        except httpx.HTTPError:
            raise MapsError(502, "upstream_error", "Routing provider request failed")

        if result is None:
            if not routing.is_configured():
                raise MapsError(503, "unavailable", "Routing provider is not configured")
            usage.provider = "miss"
            raise MapsError(404, "not_found", "No route found between origin and destination")

        usage.provider = "cache" if cached else "google"
        return {"route": result, "provider": "google", "cached": cached, "attribution": _ATTR}


# ── matrix (Phase 3) ─────────────────────────────────────────────────────────
@router.post("/matrix")
async def matrix(
    payload: MatrixRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    consumer: MapsApiConsumer = Depends(require_maps_key("matrix")),
) -> dict:
    mode = (payload.mode or "driving").lower()
    if mode not in routing.VALID_MODES:
        raise MapsError(400, "invalid_request", "mode must be driving | walking | cycling")

    total = len(payload.origins) * len(payload.destinations)
    if total > settings.MAPS_MATRIX_MAX_ELEMENTS:
        raise MapsError(400, "invalid_request",
                        f"matrix exceeds max {settings.MAPS_MATRIX_MAX_ELEMENTS} elements "
                        f"(got {total})")

    async with usage_tracker(db, consumer.id, "matrix") as usage:
        try:
            result, provider = await routing.matrix(
                db,
                origins=[(o.lat, o.lng) for o in payload.origins],
                destinations=[(d.lat, d.lng) for d in payload.destinations],
                mode=mode,
            )
        except httpx.HTTPError:
            raise MapsError(502, "upstream_error", "Matrix provider request failed")

        if provider is None:
            raise MapsError(503, "unavailable", "Matrix provider is not configured")

        usage.provider = provider
        return {**result, "provider": provider, "attribution": _ATTR}


# ── staticmap (Phase 3, optional) ────────────────────────────────────────────
@router.get("/staticmap")
async def staticmap(
    request: Request,
    size: str = Query("600x400"),
    center: str | None = Query(None),
    zoom: int | None = Query(None, ge=0, le=21),
    maptype: str | None = Query(None),
    scale: int | None = Query(None, ge=1, le=4),
    format: str = Query("png"),
    markers: list[str] = Query(default=[]),
    path: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
    consumer: MapsApiConsumer = Depends(require_maps_key("static")),
) -> Response:
    if not sm.is_configured():
        raise MapsError(503, "unavailable", "Static map provider is not configured")

    params: list[tuple[str, str]] = [("size", size), ("format", format)]
    if center:
        params.append(("center", center))
    if zoom is not None:
        params.append(("zoom", str(zoom)))
    if maptype:
        params.append(("maptype", maptype))
    if scale is not None:
        params.append(("scale", str(scale)))
    params += [("markers", m) for m in markers]
    params += [("path", p) for p in path]

    async with usage_tracker(db, consumer.id, "static") as usage:
        try:
            data, content_type, cached = await sm.fetch(params)
        except httpx.HTTPError:
            raise MapsError(502, "upstream_error", "Static map request failed")

        usage.provider = "cache" if cached else "google"
        return Response(
            content=data,
            media_type=content_type,
            headers={"X-Request-Id": request.state.request_id,
                     "X-Cache": "HIT" if cached else "MISS"},
        )


# ═══════════════════════════════════════════════════════════════════════════
# Admin (Keycloak staff role) — key management + usage view
# ═══════════════════════════════════════════════════════════════════════════
admin = APIRouter(prefix="/maps/v1/admin", tags=["maps-admin"])


@admin.post("/keys")
async def admin_mint_key(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _staff=Depends(require_staff),
) -> dict:
    name = (payload.get("name") or "").strip()
    scopes = payload.get("scopes") or []
    if not name:
        raise MapsError(400, "invalid_request", "'name' is required")
    if not isinstance(scopes, list) or not scopes:
        raise MapsError(400, "invalid_request", "'scopes' must be a non-empty list")
    bad = [s for s in scopes if s not in MAPS_SCOPES]
    if bad:
        raise MapsError(400, "invalid_request", f"Unknown scope(s): {', '.join(bad)}")

    consumer, plaintext = await create_consumer(
        db, name=name, scopes=scopes,
        rate_limit_per_min=payload.get("rate_limit_per_min"),
        monthly_quota=payload.get("monthly_quota"),
        env=payload.get("env", "live"))
    # Plaintext is returned exactly once — the caller must store it now.
    return {
        "id": str(consumer.id),
        "name": consumer.name,
        "key_prefix": consumer.key_prefix,
        "scopes": consumer.scopes,
        "rate_limit_per_min": consumer.rate_limit_per_min,
        "monthly_quota": consumer.monthly_quota,
        "key": plaintext,
    }


@admin.get("/keys")
async def admin_list_keys(
    db: AsyncSession = Depends(get_db),
    _staff=Depends(require_staff),
) -> dict:
    consumers = await list_consumers(db)
    return {
        "consumers": [
            {
                "id": str(c.id),
                "name": c.name,
                "key_prefix": c.key_prefix,
                "scopes": c.scopes,
                "rate_limit_per_min": c.rate_limit_per_min,
                "monthly_quota": c.monthly_quota,
                "active": c.active,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in consumers
        ]
    }


@admin.delete("/keys/{consumer_id}")
async def admin_revoke_key(
    consumer_id: str,
    db: AsyncSession = Depends(get_db),
    _staff=Depends(require_staff),
) -> dict:
    try:
        uuid.UUID(consumer_id)
    except ValueError:
        raise MapsError(400, "invalid_request", "consumer_id must be a UUID")
    n = await revoke_consumer(db, consumer_id=consumer_id)
    return {"revoked": n}


@admin.get("/usage")
async def admin_usage(
    consumer_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _staff=Depends(require_staff),
) -> dict:
    q = select(
        MapsApiUsage.consumer_id, MapsApiUsage.day,
        MapsApiUsage.endpoint, MapsApiUsage.provider, MapsApiUsage.count,
    ).order_by(MapsApiUsage.day.desc())
    if consumer_id:
        try:
            q = q.where(MapsApiUsage.consumer_id == uuid.UUID(consumer_id))
        except ValueError:
            raise MapsError(400, "invalid_request", "consumer_id must be a UUID")
    rows = (await db.execute(q.limit(1000))).all()
    return {
        "usage": [
            {
                "consumer_id": str(r.consumer_id), "day": r.day.isoformat(),
                "endpoint": r.endpoint, "provider": r.provider, "count": r.count,
            }
            for r in rows
        ]
    }
