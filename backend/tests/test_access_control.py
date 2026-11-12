"""Access control on user-authored content.

Places, neighborhoods and routes used to be editable and deletable by *any*
signed-in user, and a private route was readable by anyone who knew its id.
These tests pin the ownership rules that replaced that.

The tests are DB-free: the handlers are exercised through the ASGI app with
the database and the auth dependencies overridden, and the SQL the handlers
build is inspected (compiled) rather than executed.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    MANAGED_PLACE_SOURCES,
    can_read_route,
    require_neighborhood_write_access,
    require_place_write_access,
    require_route_write_access,
)
from app.core.security import Principal


# ── helpers ──────────────────────────────────────────────────────────────────
def _principal(user_id: int, staff: bool = False) -> Principal:
    """A real Principal, so the staff-role detection is exercised too."""
    roles = ["whereq-admin"] if staff else []
    return Principal(
        user=SimpleNamespace(id=user_id),
        claims={"realm_access": {"roles": roles}},
    )


def _place(user_id=None, source="manual"):
    return SimpleNamespace(id=1, user_id=user_id, source=source, is_public=False)


def _route(user_id=None, is_public=False):
    return SimpleNamespace(id=1, user_id=user_id, is_public=is_public)


def _neighborhood(user_id=None):
    return SimpleNamespace(id=1, user_id=user_id)


# ── places ───────────────────────────────────────────────────────────────────
def test_owner_may_modify_their_own_place():
    require_place_write_access(_principal(7), _place(user_id=7))


def test_a_stranger_may_not_modify_someone_elses_place():
    with pytest.raises(HTTPException) as exc:
        require_place_write_access(_principal(8), _place(user_id=7))
    assert exc.value.status_code == 403


def test_an_unowned_place_is_not_writable_by_anyone():
    """Rows that predate ownership tracking have no owner — nobody may claim
    them by guessing an id."""
    with pytest.raises(HTTPException) as exc:
        require_place_write_access(_principal(7), _place(user_id=None))
    assert exc.value.status_code == 403


def test_pipeline_managed_places_are_staff_only():
    """An OSM / whereq.cloud row is reference data: the crawl pipeline
    rewrites it on the next run, so a user edit would be lost anyway."""
    for source in sorted(MANAGED_PLACE_SOURCES):
        with pytest.raises(HTTPException) as exc:
            require_place_write_access(_principal(7), _place(user_id=7, source=source))
        assert exc.value.status_code == 403


def test_staff_may_modify_anything():
    staff = _principal(999, staff=True)
    require_place_write_access(staff, _place(user_id=7))
    require_place_write_access(staff, _place(user_id=None, source="osm"))


# ── neighborhoods ────────────────────────────────────────────────────────────
def test_neighborhood_writes_require_ownership():
    require_neighborhood_write_access(_principal(7), _neighborhood(user_id=7))
    with pytest.raises(HTTPException) as exc:
        require_neighborhood_write_access(_principal(8), _neighborhood(user_id=7))
    assert exc.value.status_code == 403
    require_neighborhood_write_access(_principal(999, staff=True), _neighborhood(user_id=7))


# ── routes ───────────────────────────────────────────────────────────────────
def test_route_writes_require_ownership():
    """A route is private by default, so a stranger gets 404 (not 403) — a
    write attempt must not confirm that the id exists either."""
    require_route_write_access(_principal(7), _route(user_id=7))
    with pytest.raises(HTTPException) as exc:
        require_route_write_access(_principal(8), _route(user_id=7))
    assert exc.value.status_code == 404
    require_route_write_access(_principal(999, staff=True), _route(user_id=7))


def test_private_routes_are_hidden_from_everyone_but_their_owner():
    owner = _principal(7)
    stranger = _principal(8)
    staff = _principal(999, staff=True)
    private = _route(user_id=7, is_public=False)

    assert can_read_route(owner, private) is True
    assert can_read_route(staff, private) is True
    assert can_read_route(stranger, private) is False
    assert can_read_route(None, private) is False


def test_published_routes_are_visible_to_everyone():
    public = _route(user_id=7, is_public=True)
    assert can_read_route(None, public) is True
    assert can_read_route(_principal(8), public) is True


# ── the routes themselves ────────────────────────────────────────────────────
class _FakeResult:
    def __init__(self, scalars=()):
        self._scalars = list(scalars)

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._scalars[0] if self._scalars else None

    def all(self):
        return self._scalars


class _FakeSession:
    """Minimal async session: serves rows from a dict, records the queries."""

    def __init__(self, routes=None, listed=()):
        self.routes = routes or {}
        self.listed = list(listed)
        self.queries = []

    async def get(self, model, pk):
        from app.models.route import Route

        if model is Route:
            return self.routes.get(pk)
        return None

    async def execute(self, stmt):
        self.queries.append(stmt)
        return _FakeResult(self.listed)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        pass

    async def rollback(self):
        pass


def _run(coro):
    return asyncio.run(coro)


def _client(session, principal):
    import httpx

    from app.core.database import get_db
    from app.core.security import get_optional_principal, get_principal
    from app.main import app

    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_optional_principal] = lambda: principal
    app.dependency_overrides[get_principal] = lambda: principal
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _clear_overrides():
    from app.core.database import get_db
    from app.core.security import get_optional_principal, get_principal
    from app.main import app

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_optional_principal, None)
    app.dependency_overrides.pop(get_principal, None)


def _route_row(route_id: int, user_id: int, is_public: bool):
    """A complete Route row (the response model validates every field)."""
    from datetime import datetime, timezone

    from app.models.route import Route

    return Route(
        id=route_id,
        user_id=user_id,
        name="a route",
        description=None,
        waypoints=[],
        total_distance_km=None,
        duration_minutes=None,
        is_public=is_public,
        created_at=datetime.now(timezone.utc),
    )


def _where_clause(stmt) -> str:
    """The WHERE criteria of a statement — the columns it selects are not
    interesting, only what it filters on."""
    return str(stmt.whereclause)


def test_getting_a_private_route_as_a_stranger_is_a_404():
    """404, not 403 — an id sweep must not be able to tell a private route
    apart from one that does not exist."""
    route = _route_row(5, user_id=7, is_public=False)
    session = _FakeSession(routes={5: route})

    async def _run_case():
        async with _client(session, _principal(8)) as ac:
            return await ac.get("/api/routes/5")

    try:
        response = _run(_run_case())
    finally:
        _clear_overrides()

    assert response.status_code == 404


def test_getting_a_private_route_as_its_owner_works():
    route = _route_row(5, user_id=7, is_public=False)
    session = _FakeSession(routes={5: route})

    async def _run_case():
        async with _client(session, _principal(7)) as ac:
            return await ac.get("/api/routes/5")

    try:
        response = _run(_run_case())
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()["id"] == 5


def test_writing_to_a_private_route_as_a_stranger_is_also_a_404():
    """The write path must not confirm the id exists either."""
    route = _route_row(5, user_id=7, is_public=False)
    session = _FakeSession(routes={5: route})

    async def _run_case():
        async with _client(session, _principal(8)) as ac:
            return await ac.patch("/api/routes/5", json={"name": "hijacked"})

    try:
        response = _run(_run_case())
    finally:
        _clear_overrides()

    assert response.status_code == 404


def test_deleting_a_private_route_as_a_stranger_is_also_a_404():
    route = _route_row(5, user_id=7, is_public=False)
    session = _FakeSession(routes={5: route})

    async def _run_case():
        async with _client(session, _principal(8)) as ac:
            return await ac.delete("/api/routes/5")

    try:
        response = _run(_run_case())
    finally:
        _clear_overrides()

    assert response.status_code == 404


def test_listing_a_users_routes_only_returns_published_ones_to_a_stranger():
    session = _FakeSession(listed=[])

    async def _run_case():
        async with _client(session, _principal(8)) as ac:
            return await ac.get("/api/routes/user/7")

    try:
        response = _run(_run_case())
    finally:
        _clear_overrides()

    assert response.status_code == 200
    # The query the handler built must be restricted to published routes.
    assert "is_public" in _where_clause(session.queries[0])


def test_listing_your_own_routes_is_not_restricted_to_published_ones():
    session = _FakeSession(listed=[])

    async def _run_case():
        async with _client(session, _principal(7)) as ac:
            return await ac.get("/api/routes/user/7")

    try:
        response = _run(_run_case())
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert "is_public" not in _where_clause(session.queries[0])
