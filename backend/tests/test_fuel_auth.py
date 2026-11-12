"""Fuel prices are licensed whereq.cloud data — signed-in users only.

Covers the three layers that enforce it:
  • the /api/fuel router requires a session (Keycloak token);
  • the places endpoints strip the price payload for anonymous callers;
  • the map serves one "fuel" category (OSM + priced) without duplicates.
"""

import asyncio


# ── the "fuel" category ─────────────────────────────────────────────────────
def test_fuel_category_expands_to_the_priced_stations():
    from app.services.place_taxonomy import expand_categories

    assert expand_categories(["fuel"]) == ["fuel", "gas"]
    assert expand_categories(["food", "fuel"]) == ["food", "fuel", "gas"]
    # Other categories are untouched, and duplicates are collapsed.
    assert expand_categories(["coffee", "coffee"]) == ["coffee"]
    assert expand_categories([]) == []


def test_shadowed_stations_matches_the_priced_rows_only():
    from sqlalchemy.dialects import postgresql

    from app.services.place_dedup import shadowed_stations

    sql = str(shadowed_stations().compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    # The join must be spatial (the same station sits ~100 m apart in the two
    # feeds) and must keep the whereq.cloud row as the winner.
    assert "ST_DWithin" in sql
    assert "whereq_cloud" in sql
    assert "osm" in sql
    assert "ST_Expand" in sql


# ── price redaction ────────────────────────────────────────────────────────
def test_prices_are_stripped_from_anonymous_place_payloads():
    from app.api.routes.places import _without_prices

    meta = {
        "brand": "Petro-Canada",
        "prices": {"regular": {"price": 1.71}},
        "observed_at": "2026-10-25T12:00:00Z",
        "currency": "CAD",
        "unit": "CAD/L",
    }
    stripped = _without_prices(meta)
    assert "prices" not in stripped
    assert "observed_at" not in stripped
    # The station itself stays visible.
    assert stripped["brand"] == "Petro-Canada"
    assert stripped["currency"] == "CAD"


def test_redaction_leaves_other_metadata_alone():
    from app.api.routes.places import _without_prices

    meta = {"opening_hours": "24/7", "website": "https://example.com"}
    assert _without_prices(meta) == meta
    assert _without_prices(None) is None


# ── the API gate ───────────────────────────────────────────────────────────
def _routes(prefix: str):
    """The routes of the router mounted under ``prefix`` (FastAPI wraps an
    included router, so the sub-routes live one level down)."""
    from app.main import app

    for r in app.routes:
        sub = getattr(r, "original_router", None)
        if sub is None or getattr(sub, "prefix", None) != prefix:
            continue
        for sr in sub.routes:
            yield sr


def _deps(route):
    return {d.call for d in route.dependant.dependencies}


def test_fuel_router_is_registered_behind_the_auth_dependency():
    from app.core.security import get_current_user

    routes = list(_routes("/fuel"))
    assert routes, "the fuel router is not registered"
    for route in routes:
        assert get_current_user in _deps(route), route.path


def test_fuel_endpoints_require_a_session():
    """Without a token the whole /api/fuel router is closed (401)."""
    import httpx

    from app.main import app

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            assert (await ac.get("/api/fuel/stations")).status_code == 401
            # The aggregated series are licensed as well.
            assert (await ac.get("/api/fuel/prices")).status_code == 401
            assert (await ac.get("/api/fuel/averages")).status_code == 401

    asyncio.run(_run())


def test_place_reads_stay_open_to_anonymous_visitors():
    """The station is public; only its prices are behind the session — so the
    place *reads* take an optional user, never a required one."""
    from app.core.security import get_current_user, get_optional_user

    routes = list(_routes("/places"))
    assert routes, "the places router is not registered"
    for route in routes:
        if "GET" not in getattr(route, "methods", set()):
            continue  # the writes stay behind a session
        deps = _deps(route)
        assert get_current_user not in deps, route.path
        if route.path in ("/places", "/places/nearby", "/places/{place_id}"):
            assert get_optional_user in deps, route.path
