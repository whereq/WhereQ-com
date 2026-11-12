"""The user's own settings — the nearby radius and the category selection.

The settings are account-scoped, so they need a session; and they are always
the caller's own, so there is no id in the path that could point at somebody
else's row.
"""

import asyncio


# ── the normalisation ───────────────────────────────────────────────────────
def test_the_categories_are_normalised():
    from app.api.routes.user_settings import _normalize

    assert _normalize(["Food", " coffee "]) == ["food", "coffee"]
    # Duplicates collapse, the order is kept.
    assert _normalize(["food", "food", "coffee"]) == ["food", "coffee"]
    # Blanks are dropped.
    assert _normalize(["food", "  "]) == ["food"]
    assert _normalize([]) == []


def test_the_category_list_is_capped():
    from app.api.routes.user_settings import MAX_CATEGORIES, _normalize

    many = [f"c{i}" for i in range(MAX_CATEGORIES + 20)]
    assert len(_normalize(many)) == MAX_CATEGORIES


# ── the API gate ────────────────────────────────────────────────────────────
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


def test_the_settings_router_needs_a_session():
    from app.core.security import get_current_user

    routes = list(_routes("/user-settings"))
    assert routes, "the user-settings router is not registered"
    for route in routes:
        assert get_current_user in _deps(route), route.path


def test_the_settings_endpoints_require_a_session():
    """Without a token the settings are closed (401)."""
    import httpx

    from app.main import app

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            assert (await ac.get("/api/user-settings")).status_code == 401
            assert (await ac.patch("/api/user-settings", json={"radius_km": 5})).status_code == 401

    asyncio.run(_run())


def test_the_settings_row_is_always_the_callers_own():
    """There is no id in the path — the row is the caller's, by construction."""
    from app.main import app

    paths = {p for p in app.openapi()["paths"] if "user-settings" in p}
    assert paths == {"/api/user-settings"}


def test_the_settings_schema_validates_the_radius():
    from pydantic import ValidationError

    from app.schemas.user_settings import UserSettingsUpdate

    assert UserSettingsUpdate(radius_km=5).radius_km == 5
    # Omitted fields stay omitted — a partial update must not clear them.
    assert UserSettingsUpdate().radius_km is None
    assert UserSettingsUpdate().categories is None
    for bad in (0.0, -1, 100.0):
        try:
            UserSettingsUpdate(radius_km=bad)
        except ValidationError:
            continue
        raise AssertionError(f"radius_km={bad} should have been rejected")


def test_the_settings_model_is_one_row_per_user():
    from app.models.user_settings import UserSettings

    # The primary key is the user — a user cannot have two settings rows.
    assert UserSettings.__table__.primary_key.columns.keys() == ["user_id"]
    # And it is created lazily, so there is no id of its own.
    assert "id" not in UserSettings.__table__.columns
