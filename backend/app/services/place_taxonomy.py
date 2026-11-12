"""The place-category vocabulary — shared by the map, the search and the nearby list.

A category can live on two different columns of ``places``:

* ``places.kind``    — the local essentials (pharmacy, clinic, library, plaza)
  and the memorials.
* ``places.category`` — the POI rows (food, coffee, fuel, parking, stays) and
  the priced whereq.cloud stations, which are stored under their own category
  (``gas``) so they stay distinguishable from the generic OSM fuel POIs.

The map serves **one** "Fuel" category for both fuel feeds, so ``"fuel"``
expands to ``("fuel", "gas")`` — and a station present in both feeds is only
drawn once (the priced row wins; see ``app.services.place_dedup``).

This lives in a service rather than in the places route because the nearby
search filters the same vocabulary and must not reach into another route.
"""

from app.crawler.upstream.fuel_stations import FUEL_CATEGORY

#: The quick-category aliases. "fuel" also covers the priced whereq.cloud
#: stations stored as category 'gas'.
CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {"fuel": ("fuel", FUEL_CATEGORY)}

#: Categories that live on ``places.kind``.
PLACE_KIND_CATEGORIES: tuple[str, ...] = (
    "pharmacy", "clinic", "library", "plaza", "memorial",
)

#: Categories that live on ``places.category`` (the POI rows).
PLACE_POI_CATEGORIES: tuple[str, ...] = (
    "food", "coffee", "fuel", "gas", "parking", "stays",
)


def expand_categories(cats: list[str]) -> list[str]:
    """Expand the quick-category aliases ("fuel" also covers the priced
    whereq.cloud stations stored as category 'gas')."""
    out: list[str] = []
    for c in cats:
        for name in CATEGORY_ALIASES.get(c, (c,)):
            if name not in out:
                out.append(name)
    return out
