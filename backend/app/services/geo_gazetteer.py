"""Lightweight gazetteer of GTA / Ontario municipalities + Toronto districts.

Two jobs in the crawler pipeline:
  1. **detect_city** — figure out which municipality a story is actually about
     (the title is the strongest signal), so the geocoding query resolves in the
     right city instead of a same-named street elsewhere (e.g. a *Markham*
     intersection landing on Toronto's Carlton St downtown).
  2. **city_center / haversine_km** — the reference point for the cross-city
     guard: a geocode that lands implausibly far from the detected city is
     rejected rather than used. It is **not** a place to pin an item — the
     crawler never places an item at a city centre (see
     ``app/crawler/pipeline.py::_resolve_position``); the city is kept on the
     row as metadata instead.

Dependency-free and rule-based so it runs cheaply in the crawler.
"""

from __future__ import annotations

import math
import re

# Canonical city / municipality / Toronto-district -> approximate centre.
CITY_CENTROIDS: dict[str, tuple[float, float]] = {
    # Toronto + former municipalities / districts
    "Toronto": (43.6532, -79.3832),
    "Scarborough": (43.7731, -79.2578),
    "North York": (43.7615, -79.4111),
    "Etobicoke": (43.6205, -79.5132),
    "East York": (43.6906, -79.3279),
    "York": (43.6896, -79.4783),
    # York Region
    "Markham": (43.8561, -79.3370),
    "Vaughan": (43.8361, -79.4983),
    "Richmond Hill": (43.8828, -79.4403),
    "Newmarket": (44.0592, -79.4613),
    "Aurora": (44.0065, -79.4504),
    "King City": (43.9270, -79.5288),
    "Whitchurch-Stouffville": (43.9710, -79.2441),
    "Stouffville": (43.9710, -79.2441),
    "Georgina": (44.2960, -79.4290),
    # Peel Region
    "Mississauga": (43.5890, -79.6441),
    "Brampton": (43.7315, -79.7624),
    "Caledon": (43.8668, -79.8662),
    # Durham Region
    "Pickering": (43.8384, -79.0868),
    "Ajax": (43.8509, -79.0204),
    "Whitby": (43.8975, -78.9428),
    "Oshawa": (43.8971, -78.8658),
    "Clarington": (43.9351, -78.6058),
    "Bowmanville": (43.9123, -78.6882),
    "Uxbridge": (44.1090, -79.1190),
    # Halton Region
    "Oakville": (43.4675, -79.6877),
    "Burlington": (43.3255, -79.7990),
    "Milton": (43.5183, -79.8774),
    "Halton Hills": (43.6303, -79.9426),
    # Wider Ontario (coarse fallback for non-GTA mentions)
    "Hamilton": (43.2557, -79.8711),
    "Ottawa": (45.4215, -75.6972),
    "London": (42.9849, -81.2453),
    "Kitchener": (43.4516, -80.4925),
    "Waterloo": (43.4643, -80.5204),
    "Cambridge": (43.3601, -80.3127),
    "Guelph": (43.5448, -80.2482),
    "Barrie": (44.3894, -79.6903),
    "Kingston": (44.2312, -76.4860),
    "Windsor": (42.3149, -83.0364),
    "Niagara Falls": (43.0896, -79.0849),
    "St. Catharines": (43.1594, -79.2469),
    "Brantford": (43.1394, -80.2644),
    "Peterborough": (44.3091, -78.3197),
    "Sudbury": (46.4917, -80.9930),
    "Thunder Bay": (48.3809, -89.2477),
    "Sault Ste. Marie": (46.5136, -84.3350),
    "Timmins": (48.0987, -79.6300),
    "North Bay": (46.3097, -79.4692),
    "Sarnia": (42.9744, -82.4069),
    "Chatham": (42.3898, -82.1881),
    "Woodstock": (43.1207, -80.7467),
    "Stratford": (43.4841, -80.9430),
    "Orillia": (44.6037, -79.4290),
    "Owen Sound": (44.5674, -80.9409),
    "Collingwood": (44.5008, -80.2152),
    "Belleville": (44.1628, -77.3877),
    "Cornwall": (45.0211, -74.7301),
    # Québec
    "Montreal": (45.5019, -73.5674),
    "Quebec City": (46.8139, -71.2080),
    "Laval": (45.6066, -73.7124),
    "Gatineau": (45.4275, -75.6975),
    "Sherbrooke": (45.4042, -71.8929),
    "Trois-Rivieres": (46.3436, -72.5508),
    "Saguenay": (48.4284, -71.0685),
    "Drummondville": (45.8833, -72.4833),
    "Saint-Jerome": (45.8809, -74.1536),
    # The rest of Canada — the crawler only claims content it can place, but a
    # story *about* a Canadian city should carry that city, and the guard
    # needs a centre to measure plausibility from.
    "Winnipeg": (49.8951, -97.1384),
    "Vancouver": (49.2827, -123.1207),
    "Victoria": (48.4284, -123.3656),
    "Burnaby": (49.2485, -122.9106),
    "Calgary": (51.0447, -114.0719),
    "Edmonton": (53.5461, -113.4938),
    "Halifax": (44.6488, -63.5752),
    "St. John's": (47.5615, -52.7126),
    "Charlottetown": (46.2382, -63.1311),
    "Fredericton": (45.9731, -66.6179),
    "Moncton": (46.0878, -64.7782),
    "Saskatoon": (52.1332, -106.6700),
    "Regina": (50.4452, -104.6189),
    "Whitehorse": (60.7212, -135.0568),
    "Yellowknife": (62.4540, -114.3718),
    "Iqaluit": (63.7467, -68.5170),
}

# Match longest names first so "Richmond Hill" wins over "Richmond", and
# "North York" / "East York" win over a bare "York".
_CITY_NAMES = sorted(CITY_CENTROIDS, key=len, reverse=True)
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _CITY_NAMES) + r")\b",
    re.IGNORECASE,
)
_CANON = {n.lower(): n for n in CITY_CENTROIDS}


def detect_city(title: str | None, body: str | None = None) -> str | None:
    """Return the canonical municipality a story is about, preferring the title.

    Returns None when no known city is mentioned (caller falls back to the
    source's default city).
    """
    for text in (title or "", body or ""):
        m = _CITY_RE.search(text)
        if m:
            return _CANON.get(m.group(1).lower())
    return None


def city_center(city: str | None) -> tuple[float, float] | None:
    """(lat, lng) centre of a known city, or None."""
    if not city:
        return None
    return CITY_CENTROIDS.get(city) or CITY_CENTROIDS.get(_CANON.get(city.lower(), ""))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) points, in kilometres."""
    (lat1, lon1), (lat2, lon2) = a, b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))
