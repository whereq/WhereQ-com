"""Multi-provider geocoding.

Public interface (unchanged for callers):
    from app.services.geocoding import geocode, GeoResult
    result = await geocode(db, "Highway 401, Toronto, ON", region="ca", country="CA")

Provider selection, quotas, rate limiting, and caching are handled internally;
free tiers are tried first and Google is the fallback of last resort.
"""

from app.services.geocoding.base import AddressComponents, GeoResult
from app.services.geocoding.manager import (
    autocomplete,
    geocode,
    geocode_detailed,
    reverse_geocode,
)

__all__ = [
    "geocode", "geocode_detailed", "reverse_geocode", "autocomplete",
    "GeoResult", "AddressComponents",
]
