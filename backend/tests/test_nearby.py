"""The nearby search — the "everything around me" list.

Covers the parts that are easy to get wrong and expensive to debug:
  • the category vocabulary is the one the map already uses;
  • a category is matched on `places.kind` *and* on `places.category`;
  • the radius is a true PostGIS radius in metres, not a bounding box;
  • the live fuel prices stay behind the session;
  • the route itself stays open to anonymous visitors.
"""

from sqlalchemy.dialects import postgresql

import pytest


def _sql(statement) -> str:
    return str(statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# ── the category vocabulary ─────────────────────────────────────────────────
def test_the_vocabulary_covers_every_source():
    from app.api.routes.nearby import NEARBY_CATEGORIES

    # The place categories (POIs + essentials), then the other three tables.
    for c in ("food", "coffee", "fuel", "parking", "stays",
              "pharmacy", "clinic", "library", "plaza", "memorial"):
        assert c in NEARBY_CATEGORIES
    for c in ("school", "news", "alerts"):
        assert c in NEARBY_CATEGORIES
    # "gas" is not a chip of its own — "fuel" covers both fuel feeds.
    assert "gas" not in NEARBY_CATEGORIES


def test_no_categories_means_every_category():
    from app.api.routes.nearby import NEARBY_CATEGORIES, _requested_categories

    assert _requested_categories(None) == list(NEARBY_CATEGORIES)
    assert _requested_categories("") == list(NEARBY_CATEGORIES)
    assert _requested_categories("   ") == list(NEARBY_CATEGORIES)


def test_requested_categories_are_filtered_and_normalised():
    from app.api.routes.nearby import _requested_categories

    assert _requested_categories("food,coffee") == ["food", "coffee"]
    # Case and padding do not matter.
    assert _requested_categories(" Food , COFFEE ") == ["food", "coffee"]
    # An unknown category is dropped rather than silently matching everything.
    assert _requested_categories("food,bogus") == ["food"]
    assert _requested_categories("bogus") == []


# ── how a place row is categorised ──────────────────────────────────────────
def test_a_place_row_maps_to_its_filter_key():
    from app.api.routes.nearby import _place_category

    # The POI rows are keyed by their category.
    assert _place_category("poi", "food") == "food"
    assert _place_category("poi", "coffee") == "coffee"
    assert _place_category("poi", "parking") == "parking"
    # Both fuel feeds collapse into the single "fuel" chip.
    assert _place_category("poi", "fuel") == "fuel"
    assert _place_category("poi", "gas") == "fuel"
    # The essentials are keyed by their kind.
    assert _place_category("pharmacy", "pharmacy") == "pharmacy"
    assert _place_category("clinic", "clinic") == "clinic"
    # A memorial is a place with a story attached.
    assert _place_category("memorial", "memorial") == "memorial"


def test_the_category_clause_matches_kind_and_category():
    """A category can live on `kind` (the essentials) or on `category` (the
    POIs) — filtering on only one of them would silently drop half the map."""
    from app.api.routes.nearby import _place_conditions

    conds = _place_conditions(["food", "pharmacy"])
    sql = _sql(conds[0])
    assert "kind IN" in sql            # the essentials
    assert "category IN" in sql         # the POI rows
    assert "OR" in sql


def test_the_fuel_chip_covers_both_fuel_feeds():
    from app.api.routes.nearby import _place_conditions

    sql = _sql(_place_conditions(["fuel"])[0])
    # 'fuel' (OSM) and 'gas' (the priced whereq.cloud rows) are one chip.
    assert "'fuel'" in sql and "'gas'" in sql


def test_no_requested_category_means_no_clause():
    from app.api.routes.nearby import _place_conditions

    assert _place_conditions([]) == []


# ── the geometry ────────────────────────────────────────────────────────────
def test_the_radius_is_a_true_postgis_radius_in_metres():
    """ST_DWithin on a 4326 *geometry* measures in degrees — the geography
    cast is what makes the third argument metres."""
    from app.api.routes.nearby import _places_stmt

    sql = _sql(_places_stmt(43.65, -79.38, 2000, ["food"], 50))
    assert "ST_DWithin" in sql
    assert "geography" in sql.lower()
    assert "ST_DistanceSphere" in sql          # the distance in metres
    assert "geom IS NOT NULL" in sql


def test_the_fuel_rows_are_de_duplicated():
    from app.api.routes.nearby import _places_stmt

    sql = _sql(_places_stmt(43.65, -79.38, 2000, ["fuel"], 50))
    assert "NOT IN" in sql
    assert "whereq_cloud" in sql


def test_every_category_is_fetched_and_counted_on_its_own():
    """A single "nearest N" query per table would let one category swallow the
    list, and would report a category as zero when it is not."""
    from app.api.routes.nearby import _places_stmt

    sql = _sql(_places_stmt(43.65, -79.38, 2000, ["food", "fuel"], 50))
    # The window functions partition by the category key.
    assert "row_number" in sql.lower()
    assert "count" in sql.lower()
    assert "PARTITION BY" in sql.upper()


def test_the_bounding_box_covers_the_radius():
    from app.api.routes.nearby import _bbox

    min_lng, min_lat, max_lng, max_lat = _bbox(43.65, -79.38, 2.0)
    assert max_lat - min_lat == pytest.approx(2000 * 2 / 111_320)
    assert min_lat < 43.65 < max_lat
    assert min_lng < -79.38 < max_lng


def test_the_great_circle_distance_is_accurate():
    """The schools have no geometry, so their distance is computed here."""
    from app.api.routes.nearby import _haversine_m

    # Toronto → Montréal is ~503 km.
    d = _haversine_m(43.6532, -79.3832, 45.5019, -73.5674)
    assert 500_000 < d < 507_000
    assert _haversine_m(43.65, -79.38, 43.65, -79.38) == 0


# ── the licensed fuel prices ────────────────────────────────────────────────
def test_the_fuel_price_is_only_included_for_a_signed_in_caller():
    from app.api.routes.nearby import _price_fields

    meta = {
        "prices": {"regular": {"price": 1.71, "observed_at": "2026-11-01T12:00:00Z"}},
        "currency": "CAD",
        "unit": "CAD/L",
        "observed_at": "2026-11-01T12:00:00Z",
    }
    # Anonymous: the station is visible, the price is not.
    assert _price_fields(meta, include_prices=False) == (None, None, None)
    # Signed in: the price comes with its currency.
    price, currency, observed_at = _price_fields(meta, include_prices=True)
    assert price == 1.71
    assert currency == "CAD"
    assert observed_at == "2026-11-01T12:00:00Z"


def test_a_station_without_a_price_is_handled():
    from app.api.routes.nearby import _price_fields

    assert _price_fields({}, include_prices=True) == (None, None, None)
    assert _price_fields({"prices": {}}, include_prices=True) == (None, None, None)


# ── the merge ───────────────────────────────────────────────────────────────
def _item(name: str, distance: int):
    from app.schemas.nearby import NearbyItem

    return NearbyItem(id=name, type="place", category="food", name=name,
                      lat=0.0, lng=0.0, distance_m=distance)


def test_the_categories_are_interleaved():
    """One large, poorly-located category must not crowd out the others.

    The crawler's news carries a fallback coordinate for thousands of rows, so
    they all sit at distance 0 — a plain distance sort would fill the whole
    list with news and hide every POI, school and fuel station.
    """
    from app.api.routes.nearby import NEARBY_CATEGORIES, _interleave

    buckets = {
        "food": [_item(f"p{i}", i) for i in range(3)],
        "news": [_item(f"n{i}", 0) for i in range(10)],   # every one at distance 0
    }
    merged = _interleave(buckets, NEARBY_CATEGORIES)
    # The nearest of each category, in turn.
    assert [i.name for i in merged[:4]] == ["p0", "n0", "p1", "n1"]
    # Nothing is dropped.
    assert len(merged) == 13


def test_an_empty_category_is_skipped():
    from app.api.routes.nearby import NEARBY_CATEGORIES, _interleave

    buckets = {"food": [_item("p0", 0)]}
    assert [i.id for i in _interleave(buckets, NEARBY_CATEGORIES)] == ["p0"]
    assert _interleave({}, NEARBY_CATEGORIES) == []


# ── the routes ──────────────────────────────────────────────────────────────
def _routes(prefix: str):
    """The routes of the router mounted under ``prefix``."""
    from app.main import app

    for r in app.routes:
        sub = getattr(r, "original_router", None)
        if sub is None or getattr(sub, "prefix", None) != prefix:
            continue
        for sr in sub.routes:
            yield sr


def _deps(route):
    return {d.call for d in route.dependant.dependencies}


def test_the_nearby_route_stays_open_to_anonymous_visitors():
    """Browsing is public — only the prices inside it are gated."""
    from app.core.security import get_current_user, get_optional_user

    routes = list(_routes("/nearby"))
    assert routes, "the nearby router is not registered"
    for route in routes:
        assert get_current_user not in _deps(route), route.path
    # It takes an *optional* user so it can tell who may see the prices.
    assert any(get_optional_user in _deps(r) for r in routes)


def test_the_nearby_route_is_registered():
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/nearby" in paths
    assert "/api/nearby/categories" in paths


def test_the_radius_is_capped():
    """A caller cannot ask for the whole province."""
    from app.core.config import settings

    assert settings.nearby_max_radius_km <= 50
    assert 0 < settings.nearby_default_radius_km <= settings.nearby_max_radius_km
