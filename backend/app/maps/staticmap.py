"""Google Static Maps proxy for the Maps service (spec §11).

Server-renders a PNG (markers + polyline) for emails / no-JS fallbacks so the
Google key never reaches the consumer. Results are cached in-process by param
hash (TTL + entry cap) to cut cost on repeated renders — e.g. the same booking
confirmation email opened many times. (In-process is fine for the single api
container; move to a shared store if the API is ever scaled out.)
"""

from __future__ import annotations

import hashlib
import time

import httpx

from app.core.config import settings

_STATIC_URL = "https://maps.googleapis.com/maps/api/staticmap"

# cache_key -> (bytes, content_type, monotonic_ts)
_cache: dict[str, tuple[bytes, str, float]] = {}


def is_configured() -> bool:
    return bool(settings.maps_google_key)


def _cache_key(params: list[tuple[str, str]]) -> str:
    raw = "&".join(f"{k}={v}" for k, v in sorted(params))
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> tuple[bytes, str] | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    data, ct, ts = hit
    if time.monotonic() - ts > settings.MAPS_STATICMAP_CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return data, ct


def _cache_put(key: str, data: bytes, ct: str) -> None:
    if len(_cache) >= settings.MAPS_STATICMAP_CACHE_MAX and key not in _cache:
        oldest = min(_cache.items(), key=lambda kv: kv[1][2])[0]
        _cache.pop(oldest, None)
    _cache[key] = (data, ct, time.monotonic())


async def fetch(params: list[tuple[str, str]]) -> tuple[bytes, str, bool]:
    """Return ``(image_bytes, content_type, cached)``.

    ``params`` is a list of (key, value) tuples (supports repeated ``markers`` /
    ``path``), WITHOUT the API key. Raises ``httpx.HTTPError`` on upstream
    failure (non-200 or non-image response).
    """
    key = _cache_key(params)
    cached = _cache_get(key)
    if cached is not None:
        return cached[0], cached[1], True

    query = list(params) + [("key", settings.maps_google_key)]
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(_STATIC_URL, params=query)

    ct = resp.headers.get("content-type", "")
    if resp.status_code != 200 or not ct.startswith("image/"):
        raise httpx.HTTPError(f"google staticmap status={resp.status_code} ct={ct}")

    _cache_put(key, resp.content, ct)
    return resp.content, ct, False
