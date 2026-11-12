"""Geocoding provider abstraction.

Each provider exposes a single ``geocode`` coroutine returning a normalized
``GeoResult`` (or None for zero-results). The manager handles ordering, quota
checks, rate limiting, and caching — providers only know how to call their API.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass
class AddressComponents:
    """Normalized address parts (see Maps service spec §4).

    ``region`` is the 2-letter province/territory / state code (e.g. ``ON``);
    ``region_name`` carries the full name. ``country`` is alpha-2.
    """
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    region_name: str | None = None
    postal_code: str | None = None
    country: str | None = None

    def as_dict(self) -> dict:
        return {
            "line1": self.line1, "line2": self.line2, "city": self.city,
            "region": self.region, "region_name": self.region_name,
            "postal_code": self.postal_code, "country": self.country,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "AddressComponents | None":
        if not d:
            return None
        return cls(**{k: d.get(k) for k in (
            "line1", "line2", "city", "region", "region_name",
            "postal_code", "country")})


@dataclass
class GeoResult:
    lat: float
    lng: float
    formatted_address: str | None
    confidence: float
    provider: str | None = None
    # Extended fields (populated by the Maps service; the crawler ignores them).
    components: AddressComponents | None = None
    place_id: str | None = None
    location_type: str | None = None


class GeocodeProvider(ABC):
    """Base class for a geocoding provider."""

    name: str = "base"
    quota_period: str = "day"   # "day" | "month"
    min_interval: float = 0.0    # seconds between successive calls (rate limit)

    # in-process timestamp of the last call (per provider instance)
    _last_call: float = 0.0

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    def is_configured(self) -> bool:
        """True when this provider has the config (e.g. API key) it needs."""

    @abstractmethod
    def quota_limit(self) -> int:
        """Max requests allowed in the current quota window."""

    @abstractmethod
    async def geocode(self, client: httpx.AsyncClient, query: str, *,
                      region: str, country: str) -> GeoResult | None:
        """Call the provider API. Return GeoResult, or None for zero-results.

        Raise on transient/quota errors so the manager moves to the next
        provider without caching a permanent miss.
        """

    # ── optional reverse geocoding (coords → address) ──────────────────────
    def supports_reverse(self) -> bool:
        """True when this provider implements :meth:`reverse`."""
        return False

    async def reverse(self, client: httpx.AsyncClient, lat: float, lng: float, *,
                      lang: str = "en") -> GeoResult | None:
        """Reverse geocode a coordinate. Override in providers that support it."""
        raise NotImplementedError

    # ── helpers ──────────────────────────────────────────────────────────
    def period_key(self) -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m") if self.quota_period == "month" else now.strftime("%Y-%m-%d")

    async def respect_rate_limit(self) -> None:
        import asyncio
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()
