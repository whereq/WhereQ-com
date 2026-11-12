"""Concrete geocoding providers.

Free-tier providers first; Google is the paid fallback of last resort. Each
provider raises on transient/quota HTTP errors (so the manager advances to the
next provider) and returns None only for a genuine zero-results response.

Providers also populate normalized :class:`AddressComponents` (Maps service
spec §4) when the upstream response carries structured address data. Google
parses them fully (best quality, reliable 2-letter ``region``); the free
providers fill them best-effort.
"""

from __future__ import annotations

import httpx

from app.services.geocoding.base import AddressComponents, GeocodeProvider, GeoResult


def _clamp(x: float, lo: float = 0.3, hi: float = 0.95) -> float:
    return max(lo, min(hi, x))


# ── component parsing helpers ───────────────────────────────────────────────
def _google_components(result: dict) -> AddressComponents:
    """Map a Google geocode result's ``address_components`` to §4 fields."""
    parts = {t: c for c in result.get("address_components", []) for t in c.get("types", [])}

    def short(t):
        return parts[t]["short_name"] if t in parts else None

    def long(t):
        return parts[t]["long_name"] if t in parts else None

    number = long("street_number")
    route = long("route")
    line1 = " ".join(p for p in (number, route) if p) or None
    city = long("locality") or long("postal_town") or long("sublocality") \
        or long("sublocality_level_1")
    return AddressComponents(
        line1=line1,
        city=city,
        region=short("administrative_area_level_1"),
        region_name=long("administrative_area_level_1"),
        postal_code=long("postal_code"),
        country=short("country"),
    )


def _places_new_components(components: list[dict]) -> AddressComponents:
    """Map Places API (New) ``addressComponents`` (longText/shortText) to §4.

    Same semantics as :func:`_google_components` but for the New Places schema
    where each component has ``longText``/``shortText`` instead of
    ``long_name``/``short_name``.
    """
    parts = {t: c for c in (components or []) for t in c.get("types", [])}

    def short(t):
        return parts[t].get("shortText") if t in parts else None

    def long(t):
        return parts[t].get("longText") if t in parts else None

    number = long("street_number")
    route = long("route")
    line1 = " ".join(p for p in (number, route) if p) or None
    city = long("locality") or long("postal_town") or long("sublocality") \
        or long("sublocality_level_1")
    return AddressComponents(
        line1=line1,
        city=city,
        region=short("administrative_area_level_1"),
        region_name=long("administrative_area_level_1"),
        postal_code=long("postal_code"),
        country=short("country"),
    )


def _osm_components(addr: dict) -> AddressComponents:
    """Map a Nominatim/LocationIQ ``address`` object to §4 fields.

    Region code comes from ``ISO3166-2-lvl4`` (e.g. ``CA-ON`` → ``ON``) when
    present; otherwise the full ``state`` name is returned as ``region_name``.
    """
    house = addr.get("house_number")
    road = addr.get("road") or addr.get("pedestrian") or addr.get("footway")
    line1 = " ".join(p for p in (house, road) if p) or road or None
    city = (addr.get("city") or addr.get("town") or addr.get("village")
            or addr.get("municipality") or addr.get("suburb"))
    iso = addr.get("ISO3166-2-lvl4") or ""
    region = iso.split("-", 1)[1] if "-" in iso else None
    country = addr.get("country_code")
    return AddressComponents(
        line1=line1,
        city=city,
        region=region,
        region_name=addr.get("state"),
        postal_code=addr.get("postcode"),
        country=country.upper() if country else None,
    )


class NominatimProvider(GeocodeProvider):
    name = "nominatim"
    quota_period = "day"

    def __init__(self, settings):
        super().__init__(settings)
        self.min_interval = 1.0 / max(0.1, settings.NOMINATIM_RPS)

    def is_configured(self) -> bool:
        return bool(self.settings.NOMINATIM_BASE_URL)

    def quota_limit(self) -> int:
        return self.settings.NOMINATIM_DAILY_QUOTA

    def _ua(self) -> str:
        email = self.settings.NOMINATIM_EMAIL
        return f"WhereQMaps/1.0 (+https://whereq.com{('; ' + email) if email else ''})"

    async def geocode(self, client, query, *, region, country):
        params = {"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1}
        if region:
            params["countrycodes"] = region.lower()
        if self.settings.NOMINATIM_EMAIL:
            params["email"] = self.settings.NOMINATIM_EMAIL
        resp = await client.get(f"{self.settings.NOMINATIM_BASE_URL}/search",
                                params=params, headers={"User-Agent": self._ua()})
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        top = data[0]
        imp = float(top.get("importance") or 0)
        return GeoResult(
            float(top["lat"]), float(top["lon"]), top.get("display_name"),
            _clamp(0.3 + imp),
            components=_osm_components(top.get("address") or {}),
            place_id=(f"osm:{top['osm_type']}:{top['osm_id']}"
                      if top.get("osm_id") else None),
        )

    def supports_reverse(self) -> bool:
        return True

    async def reverse(self, client, lat, lng, *, lang="en"):
        params = {"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1}
        if self.settings.NOMINATIM_EMAIL:
            params["email"] = self.settings.NOMINATIM_EMAIL
        resp = await client.get(f"{self.settings.NOMINATIM_BASE_URL}/reverse",
                                params=params,
                                headers={"User-Agent": self._ua(),
                                         "Accept-Language": lang})
        resp.raise_for_status()
        top = resp.json()
        if not top or "lat" not in top:
            return None
        return GeoResult(
            float(top["lat"]), float(top["lon"]), top.get("display_name"), 0.6,
            components=_osm_components(top.get("address") or {}),
            place_id=(f"osm:{top['osm_type']}:{top['osm_id']}"
                      if top.get("osm_id") else None),
        )


class GeocodeMapsCoProvider(GeocodeProvider):
    name = "geocode_maps_co"
    quota_period = "day"
    min_interval = 1.0

    def is_configured(self) -> bool:
        return bool(self.settings.GEOCODE_MAPS_CO_API_KEY)

    def quota_limit(self) -> int:
        return self.settings.GEOCODE_MAPS_CO_DAILY_QUOTA

    async def geocode(self, client, query, *, region, country):
        params = {"q": query, "api_key": self.settings.GEOCODE_MAPS_CO_API_KEY}
        resp = await client.get("https://geocode.maps.co/search", params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        top = data[0]
        imp = float(top.get("importance") or 0)
        return GeoResult(float(top["lat"]), float(top["lon"]),
                         top.get("display_name"), _clamp(0.3 + imp))


class LocationIQProvider(GeocodeProvider):
    name = "locationiq"
    quota_period = "day"
    min_interval = 0.5  # free tier ~2 req/sec

    def is_configured(self) -> bool:
        return bool(self.settings.LOCATIONIQ_API_KEY)

    def quota_limit(self) -> int:
        return self.settings.LOCATIONIQ_DAILY_QUOTA

    async def geocode(self, client, query, *, region, country):
        params = {"key": self.settings.LOCATIONIQ_API_KEY, "q": query,
                  "format": "json", "limit": 1, "addressdetails": 1}
        if region:
            params["countrycodes"] = region.lower()
        resp = await client.get("https://us1.locationiq.com/v1/search", params=params)
        if resp.status_code == 404:   # LocationIQ uses 404 for zero-results
            return None
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        top = data[0]
        imp = float(top.get("importance") or 0)
        return GeoResult(
            float(top["lat"]), float(top["lon"]), top.get("display_name"),
            _clamp(0.35 + imp),
            components=_osm_components(top.get("address") or {}))

    def supports_reverse(self) -> bool:
        return True

    async def reverse(self, client, lat, lng, *, lang="en"):
        params = {"key": self.settings.LOCATIONIQ_API_KEY, "lat": lat, "lon": lng,
                  "format": "json", "addressdetails": 1}
        resp = await client.get("https://us1.locationiq.com/v1/reverse", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        top = resp.json()
        if not top or "lat" not in top:
            return None
        return GeoResult(
            float(top["lat"]), float(top["lon"]), top.get("display_name"), 0.6,
            components=_osm_components(top.get("address") or {}))


class GeocodioProvider(GeocodeProvider):
    name = "geocodio"
    quota_period = "day"

    def is_configured(self) -> bool:
        return bool(self.settings.GEOCODIO_API_KEY)

    def quota_limit(self) -> int:
        return self.settings.GEOCODIO_DAILY_QUOTA

    @staticmethod
    def _components(fields: dict) -> AddressComponents:
        return AddressComponents(
            line1=" ".join(p for p in (fields.get("number"), fields.get("formatted_street"))
                           if p) or fields.get("formatted_street"),
            city=fields.get("city"),
            region=fields.get("state"),
            postal_code=fields.get("zip"),
            country=fields.get("country"),
        )

    async def geocode(self, client, query, *, region, country):
        params = {"q": query, "api_key": self.settings.GEOCODIO_API_KEY, "limit": 1}
        if country:
            params["country"] = country
        resp = await client.get("https://api.geocod.io/v1.7/geocode", params=params)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return None
        top = results[0]
        loc = top["location"]
        acc = float(top.get("accuracy") or 0.6)
        return GeoResult(loc["lat"], loc["lng"], top.get("formatted_address"),
                         _clamp(acc),
                         components=self._components(top.get("address_components") or {}))


class PositionstackProvider(GeocodeProvider):
    name = "positionstack"
    quota_period = "month"

    def is_configured(self) -> bool:
        return bool(self.settings.POSITIONSTACK_API_KEY)

    def quota_limit(self) -> int:
        return self.settings.POSITIONSTACK_MONTHLY_QUOTA

    async def geocode(self, client, query, *, region, country):
        params = {"access_key": self.settings.POSITIONSTACK_API_KEY, "query": query, "limit": 1}
        if country:
            params["country"] = country
        resp = await client.get("http://api.positionstack.com/v1/forward", params=params)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise httpx.HTTPError(f"positionstack error: {payload['error']}")
        data = (payload.get("data") if isinstance(payload, dict) else None) or []
        if not data:
            return None
        top = data[0]
        conf = float(top.get("confidence") or 0.6)
        return GeoResult(top["latitude"], top["longitude"], top.get("label"), _clamp(conf))


class GoogleProvider(GeocodeProvider):
    name = "google"
    quota_period = "day"

    _LOCATION_TYPE_CONFIDENCE = {
        "ROOFTOP": 0.95, "RANGE_INTERPOLATED": 0.8,
        "GEOMETRIC_CENTER": 0.6, "APPROXIMATE": 0.45,
    }

    def is_configured(self) -> bool:
        return bool(self.settings.maps_google_key)

    def quota_limit(self) -> int:
        return self.settings.GOOGLE_GEOCODE_DAILY_QUOTA

    def _result(self, top: dict) -> GeoResult:
        loc = top["geometry"]["location"]
        ltype = top["geometry"].get("location_type", "APPROXIMATE")
        return GeoResult(
            loc["lat"], loc["lng"], top.get("formatted_address"),
            _clamp(self._LOCATION_TYPE_CONFIDENCE.get(ltype, 0.45)),
            components=_google_components(top),
            place_id=top.get("place_id"),
            location_type=ltype)

    async def geocode(self, client, query, *, region, country):
        params = {"address": query, "key": self.settings.maps_google_key}
        if region:
            params["region"] = region
        if country:
            params["components"] = f"country:{country}"
        resp = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
        resp.raise_for_status()
        body = resp.json()
        status = body.get("status")
        if status == "ZERO_RESULTS":
            return None
        if status != "OK" or not body.get("results"):
            raise httpx.HTTPError(f"google geocode status={status}")
        return self._result(body["results"][0])

    def supports_reverse(self) -> bool:
        return True

    async def reverse(self, client, lat, lng, *, lang="en"):
        params = {"latlng": f"{lat},{lng}", "key": self.settings.maps_google_key,
                  "language": lang}
        resp = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
        resp.raise_for_status()
        body = resp.json()
        status = body.get("status")
        if status == "ZERO_RESULTS":
            return None
        if status != "OK" or not body.get("results"):
            raise httpx.HTTPError(f"google reverse status={status}")
        return self._result(body["results"][0])

    async def place_details(self, client, place_id, *, lang="en", session=None) -> GeoResult | None:
        """Resolve a Places API (New) place id to coordinates + §4 components.

        Uses ``GET https://places.googleapis.com/v1/places/{id}`` with a required
        ``X-Goog-FieldMask`` header; the session token (from /autocomplete) is
        passed so the lookup shares the same billable session.
        """
        params = {"languageCode": lang}
        if session:
            params["sessionToken"] = session
        headers = {
            "X-Goog-Api-Key": self.settings.maps_google_key,
            "X-Goog-FieldMask": "id,location,formattedAddress,addressComponents",
        }
        resp = await client.get(f"https://places.googleapis.com/v1/places/{place_id}",
                                params=params, headers=headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        r = resp.json()
        loc = r.get("location") or {}
        if "latitude" not in loc or "longitude" not in loc:
            return None
        return GeoResult(
            loc["latitude"], loc["longitude"], r.get("formattedAddress"),
            0.9,   # a resolved place id is high-confidence (rooftop-class)
            components=_places_new_components(r.get("addressComponents") or []),
            place_id=r.get("id") or place_id,
            location_type=None)


# slug -> provider class
PROVIDER_CLASSES: dict[str, type[GeocodeProvider]] = {
    "nominatim": NominatimProvider,
    "geocode_maps_co": GeocodeMapsCoProvider,
    "locationiq": LocationIQProvider,
    "geocodio": GeocodioProvider,
    "positionstack": PositionstackProvider,
    "google": GoogleProvider,
}
