"""The place-card API against a **real** Postgres.

``test_place_cards.py`` next door checks the router's wiring with a faked
session. This file proves the other half: that migration ``017_place_cards``
produces a schema the ORM and the routes actually work against — real SQL,
real constraints, real cascades.

It is **opt-in**. It runs only when ``WHEREQ_TEST_DATABASE_URL`` points at a
Postgres that has already been migrated, so the default ``pytest`` run never
touches a database — and can never touch somebody's production one by
accident.

    createdb whereq_test
    DATABASE_URL=... DATABASE_URL_SYNC=... alembic upgrade head
    WHEREQ_TEST_DATABASE_URL=postgresql+asyncpg://user@127.0.0.1:5432/whereq_test \
        pytest tests/test_place_cards_db.py -v

Everything it creates, it deletes again.

**A Postgres without root.** The migrations need PostGIS, so a server and the
extension are needed. On a machine where only the client is installed and
``sudo`` is unavailable, Debian's packages can be unpacked into a writable
prefix and the server run from there — PostgreSQL resolves its share and
library paths relative to the binary, so the whole tree relocates:

    mkdir -p /tmp/pgdebs && cd /tmp/pgdebs
    apt-get download postgresql-16 postgresql-client-16 postgresql-16-postgis-3 \\
        postgresql-16-postgis-3-scripts libgeos-c1t64 libproj25 proj-data \\
        libgdal39 gdal-data libsfcgal2 libprotobuf-c1
    for d in *.deb; do dpkg-deb -x "$d" /tmp/pgsql; done
    # Debian names the control file postgis-3.control and symlinks the plain
    # name to it in its postinst; do the same by hand.
    cd /tmp/pgsql/usr/share/postgresql/16/extension
    ln -sf postgis-3.control postgis.control
    export LD_LIBRARY_PATH=/tmp/pgsql/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
    /tmp/pgsql/usr/lib/postgresql/16/bin/initdb -D /tmp/pgdata -U whereq --auth=trust
    /tmp/pgsql/usr/lib/postgresql/16/bin/pg_ctl -D /tmp/pgdata -l /tmp/pg.log \\
        -o "-p 55432 -k /tmp/pgsock -c listen_addresses=127.0.0.1" -w start
    psql -h 127.0.0.1 -p 55432 -U whereq -d postgres -c 'CREATE DATABASE whereq_test'
    psql -h 127.0.0.1 -p 55432 -U whereq -d whereq_test -c 'CREATE EXTENSION postgis;'
"""

import asyncio
import os
import uuid

import pytest


#: The opt-in. A sync ``postgresql://`` URL is accepted and rewritten.
TEST_DB_URL = os.environ.get("WHEREQ_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="set WHEREQ_TEST_DATABASE_URL to a migrated Postgres to run these",
)


def _async_url(url: str) -> str:
    """The engine needs an async driver; accept either spelling."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# ── the plumbing ───────────────────────────────────────────────────────────
def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(_async_url(TEST_DB_URL), pool_pre_ping=True)


def _sessionmaker(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _principal(user_id: int, staff: bool = False):
    """A signed-in caller. The claims carry the realm role the staff check reads."""
    from app.core.security import Principal
    from app.models.user import User

    claims = {"realm_access": {"roles": ["whereq-admin"]}} if staff else {}
    user = User(id=user_id, username=f"u{user_id}", email=f"u{user_id}@example.com")
    return Principal(user=user, claims=claims)


def _client(sm, principal):
    """The real app, with only the session and the caller replaced."""
    import httpx

    from app.core.database import get_db
    from app.core.security import get_current_user, get_principal
    from app.main import app

    async def _db():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_principal] = lambda: principal
    # The router is mounted with the router-level `get_current_user`
    # dependency, so it has to be replaced too — otherwise every call is a
    # 401 before the route ever runs.
    app.dependency_overrides[get_current_user] = lambda: principal.user
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _clear_overrides():
    from app.core.database import get_db
    from app.core.security import get_current_user, get_principal
    from app.main import app

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_principal, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _make_user(sm):
    """A real user row, so the card's FK has something to point at."""
    from app.models.user import User

    tag = uuid.uuid4().hex[:12]
    async with sm() as s:
        user = User(
            username=f"cardtest_{tag}",
            email=f"cardtest_{tag}@example.com",
            is_active=True,
            locale="en",
            theme="dark",
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user.id


async def _drop_user(sm, user_id: int):
    from sqlalchemy import delete

    from app.models.user import User

    async with sm() as s:
        await s.execute(delete(User).where(User.id == user_id))
        await s.commit()


async def _sweep(sm):
    """Remove the accounts a previous, interrupted run may have left behind.

    The cards go with them (the FK cascades), so the table is clean too.
    """
    from sqlalchemy import delete

    from app.models.user import User

    async with sm() as s:
        await s.execute(
            delete(User).where(User.username.like("cardtest_%"))
        )
        await s.commit()


def _card_payload(**over):
    """A valid card body."""
    body = {
        "name": "Markham Pan Am Centre",
        "description": "The arena, and everything within a short walk of it.",
        "kind": "business",
        "category": "stays",
        "latitude": 43.8375,
        "longitude": -79.3168,
        "address": "16 Main St Unionville, Markham, ON L3R 0W7, Canada",
        "city": "Markham",
        "country": "Canada",
        "radius_km": 2.0,
        "categories": ["food", "coffee"],
        "logo_url": "https://example.com/logo.png",
        "accent": "#4ADE80",
    }
    body.update(over)
    return body


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _no_leaked_overrides():
    """The app object is global.

    An override left behind changes another test's answer — a request that
    should be a 401 becomes a 200 — so every test here hands the app back
    exactly as it found it.
    """
    yield
    _clear_overrides()


#: A run that was interrupted mid-test can leave an account behind; the next
#: run clears it before it starts, so the database stays as it was found.
def setup_module(module):
    if not TEST_DB_URL:
        return
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run_case():
        try:
            await _sweep(sm)
        finally:
            await engine.dispose()

    _run(_run_case())


def teardown_module(module):
    if not TEST_DB_URL:
        return
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run_case():
        try:
            await _sweep(sm)
        finally:
            await engine.dispose()

    _run(_run_case())


# ── the schema the migration produced ───────────────────────────────────────
def test_the_migrated_table_matches_the_model():
    """The columns and the constraints are the ones the ORM expects.

    This is the check that would have caught a migration that renamed a
    column, dropped an index or missed the unique token.
    """
    from sqlalchemy import text

    async def _run_case():
        engine = _engine()
        try:
            async with engine.connect() as conn:
                cols = (
                    await conn.execute(
                        text(
                            "select column_name, data_type, is_nullable, column_default "
                            "from information_schema.columns "
                            "where table_name = 'place_cards' order by column_name"
                        )
                    )
                ).all()
                by_name = {c[0]: c for c in cols}

                # every column the model declares is really there
                from app.models.place_card import PlaceCard

                model_cols = {c.name for c in PlaceCard.__table__.columns}
                assert model_cols <= set(by_name), model_cols - set(by_name)

                # and the ones that matter are shaped right
                assert by_name["categories"][1] == "ARRAY"
                assert by_name["categories"][2] == "NO"
                assert by_name["categories"][3] == "'{}'::text[]"
                # the defaults the model documents, as the server stored them
                assert "5" in (by_name["radius_km"][3] or "")
                assert "draft" in (by_name["status"][3] or "")
                assert "business" in (by_name["kind"][3] or "")
                assert by_name["report_count"][3] == "0"

                # the publication token is unique — a real index, not a hope
                idx = (
                    await conn.execute(
                        text(
                            "select indexdef from pg_indexes "
                            "where tablename = 'place_cards' "
                            "and indexname = 'ix_place_cards_publish_token'"
                        )
                    )
                ).scalar_one()
                assert "UNIQUE" in idx, idx

                # and the owner is a real foreign key with a cascade
                fk = (
                    await conn.execute(
                        text(
                            "select confdeltype::text from pg_constraint "
                            "where conname = 'fk_place_cards_user_id_users'"
                        )
                    )
                ).scalar_one()
                assert fk == "c", "the owner FK must ON DELETE CASCADE"
        finally:
            await engine.dispose()

    _run(_run_case())


# ── the round trip ─────────────────────────────────────────────────────────
def test_creating_a_card_writes_a_real_row():
    """POST → a row that is really in the table, owned by the caller."""
    from sqlalchemy import select

    from app.models.place_card import PlaceCard

    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with _client(sm, _principal(user_id)) as ac:
                res = await ac.post("/api/place-cards", json=_card_payload())
            assert res.status_code == 201, res.text
            body = res.json()
            assert body["name"] == "Markham Pan Am Centre"
            assert body["user_id"] == user_id
            assert body["status"] == "draft"
            assert body["publish_token"] is None
            assert body["categories"] == ["food", "coffee"]
            assert body["radius_km"] == 2.0

            # …and the row is really there, in the database
            async with sm() as s:
                row = (
                    await s.execute(
                        select(PlaceCard).where(PlaceCard.id == body["id"])
                    )
                ).scalar_one()
                assert row.name == "Markham Pan Am Centre"
                assert row.user_id == user_id
                assert row.status == "draft"
                assert row.publish_token is None
                assert row.categories == ["food", "coffee"]
                assert row.created_at is not None and row.updated_at is not None
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())


def test_the_defaults_are_the_documented_ones():
    """A card created with the minimum has the documented defaults."""
    from sqlalchemy import select

    from app.models.place_card import PlaceCard

    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with _client(sm, _principal(user_id)) as ac:
                res = await ac.post(
                    "/api/place-cards",
                    json={
                        "name": "A card",
                        "latitude": 43.0,
                        "longitude": -79.0,
                    },
                )
            assert res.status_code == 201, res.text
            body = res.json()
            assert body["kind"] == "business"
            assert body["radius_km"] == 5.0
            assert body["categories"] == []
            assert body["status"] == "draft"
            assert body["report_count"] == 0 and body["view_count"] == 0

            async with sm() as s:
                row = (
                    await s.execute(
                        select(PlaceCard).where(PlaceCard.id == body["id"])
                    )
                ).scalar_one()
                # the empty category list is stored as an empty array, not NULL
                assert row.categories == []
                assert row.radius_km == 5.0
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())


def test_the_list_holds_only_the_callers_own_cards():
    """Two accounts, two lists — the list is always yours."""
    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        a = await _make_user(sm)
        b = await _make_user(sm)
        try:
            async with _client(sm, _principal(a)) as ac:
                await ac.post("/api/place-cards", json=_card_payload(name="A's card"))
            async with _client(sm, _principal(b)) as ac:
                await ac.post("/api/place-cards", json=_card_payload(name="B's card"))

            async with _client(sm, _principal(a)) as ac:
                res = await ac.get("/api/place-cards")
            assert res.status_code == 200
            names = [c["name"] for c in res.json()]
            assert names == ["A's card"], names

            async with _client(sm, _principal(b)) as ac:
                res = await ac.get("/api/place-cards")
            assert [c["name"] for c in res.json()] == ["B's card"]
        finally:
            await _drop_user(sm, a)
            await _drop_user(sm, b)
            await engine.dispose()

    _run(_run_case())


def test_another_accounts_card_is_a_404():
    """Not 403 — a read must not reveal which ids exist.

    The row is checked afterwards: a rejected write must not have touched it.
    """
    from sqlalchemy import select

    from app.models.place_card import PlaceCard

    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        owner = await _make_user(sm)
        stranger = await _make_user(sm)
        try:
            async with _client(sm, _principal(owner)) as ac:
                made = await ac.post("/api/place-cards", json=_card_payload())
            card_id = made.json()["id"]

            async with _client(sm, _principal(stranger)) as ac:
                assert (await ac.get(f"/api/place-cards/{card_id}")).status_code == 404
                res = await ac.patch(
                    f"/api/place-cards/{card_id}", json={"name": "hijacked"}
                )
                assert res.status_code == 404, res.text
                res = await ac.delete(f"/api/place-cards/{card_id}")
                assert res.status_code == 404, res.text

            # the card is untouched
            async with sm() as s:
                row = (
                    await s.execute(
                        select(PlaceCard).where(PlaceCard.id == card_id)
                    )
                ).scalar_one()
                assert row.name == "Markham Pan Am Centre"
                assert row.user_id == owner
        finally:
            await _drop_user(sm, owner)
            await _drop_user(sm, stranger)
            await engine.dispose()

    _run(_run_case())


def test_a_card_is_never_a_place():
    """The rule the whole design rests on, checked against the real tables.

    A card is a published view of a place, not a place: it must never reach
    the ``places`` table, or it would become a map pin for everybody and would
    inflate the category counts.
    """
    from sqlalchemy import func, select

    from app.models.place import Place
    from app.models.place_card import PlaceCard

    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with sm() as s:
                places_before = (await s.execute(select(func.count(Place.id)))).scalar_one()

            async with _client(sm, _principal(user_id)) as ac:
                res = await ac.post("/api/place-cards", json=_card_payload())
            assert res.status_code == 201, res.text
            card_id = res.json()["id"]

            async with sm() as s:
                places_after = (await s.execute(select(func.count(Place.id)))).scalar_one()
                assert places_after == places_before, "a card created a place row"
                # and the card is not a place by id either
                assert (
                    await s.execute(
                        select(Place).where(Place.id == card_id)
                    )
                ).scalar_one_or_none() is None
                # it is a card
                assert (
                    await s.execute(
                        select(PlaceCard).where(PlaceCard.id == card_id)
                    )
                ).scalar_one() is not None
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())


def test_the_publish_token_is_unique_in_the_database():
    """The uniqueness is the database's job, and the database does it."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models.place_card import PlaceCard

    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with sm() as s:
                first = PlaceCard(
                    user_id=user_id,
                    name="First",
                    latitude=43.0,
                    longitude=-79.0,
                    publish_token="the-same-token",
                )
                second = PlaceCard(
                    user_id=user_id,
                    name="Second",
                    latitude=43.0,
                    longitude=-79.0,
                    publish_token="the-same-token",
                )
                s.add(first)
                await s.commit()
                s.add(second)
                with pytest.raises(IntegrityError):
                    await s.commit()
                await s.rollback()

                rows = (
                    await s.execute(
                        select(PlaceCard).where(
                            PlaceCard.publish_token == "the-same-token"
                        )
                    )
                ).scalars().all()
                assert len(rows) == 1
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())


def test_deleting_the_account_deletes_the_card():
    """The card dies with its owner — the FK cascades, in the database."""
    from sqlalchemy import func, select

    from app.models.place_card import PlaceCard

    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with _client(sm, _principal(user_id)) as ac:
                res = await ac.post("/api/place-cards", json=_card_payload())
            card_id = res.json()["id"]

            async with sm() as s:
                assert (
                    await s.execute(
                        select(func.count(PlaceCard.id)).where(
                            PlaceCard.user_id == user_id
                        )
                    )
                ).scalar_one() == 1

            await _drop_user(sm, user_id)

            async with sm() as s:
                assert (
                    await s.execute(
                        select(func.count(PlaceCard.id)).where(
                            PlaceCard.user_id == user_id
                        )
                    )
                ).scalar_one() == 0
                assert (
                    await s.execute(
                        select(PlaceCard).where(PlaceCard.id == card_id)
                    )
                ).scalar_one_or_none() is None
        finally:
            await engine.dispose()

    _run(_run_case())


def test_updating_a_card_writes_through():
    """A partial update touches only what it names."""
    from sqlalchemy import select

    from app.models.place_card import PlaceCard

    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with _client(sm, _principal(user_id)) as ac:
                made = await ac.post("/api/place-cards", json=_card_payload())
                card_id = made.json()["id"]
                res = await ac.patch(
                    f"/api/place-cards/{card_id}",
                    json={"radius_km": 10.0, "categories": ["parking"]},
                )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["radius_km"] == 10.0
            assert body["categories"] == ["parking"]
            # untouched
            assert body["name"] == "Markham Pan Am Centre"
            assert body["address"].startswith("16 Main St")

            async with sm() as s:
                row = (
                    await s.execute(
                        select(PlaceCard).where(PlaceCard.id == card_id)
                    )
                ).scalar_one()
                assert row.radius_km == 10.0
                assert row.categories == ["parking"]
                assert row.name == "Markham Pan Am Centre"
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())


def test_deleting_a_card_removes_the_row():
    async def _run_case():
        from sqlalchemy import func, select

        from app.models.place_card import PlaceCard

        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with _client(sm, _principal(user_id)) as ac:
                made = await ac.post("/api/place-cards", json=_card_payload())
                card_id = made.json()["id"]
                res = await ac.delete(f"/api/place-cards/{card_id}")
            assert res.status_code == 204, res.text

            async with sm() as s:
                assert (
                    await s.execute(
                        select(func.count(PlaceCard.id)).where(
                            PlaceCard.id == card_id
                        )
                    )
                ).scalar_one() == 0
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())


def test_the_card_cap_is_enforced():
    """``MAX_CARDS_PER_USER`` is a real limit, not a comment."""
    async def _run_case():
        from app.api.routes.place_cards import MAX_CARDS_PER_USER

        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with _client(sm, _principal(user_id)) as ac:
                for i in range(MAX_CARDS_PER_USER):
                    res = await ac.post(
                        "/api/place-cards", json=_card_payload(name=f"Card {i}")
                    )
                    assert res.status_code == 201, res.text
                res = await ac.post(
                    "/api/place-cards", json=_card_payload(name="One too many")
                )
            assert res.status_code == 400, res.text
            assert str(MAX_CARDS_PER_USER) in res.text
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())


def test_a_bad_card_is_rejected_by_the_schema():
    """The validators hold on the way in — a blank name, a non-URL logo."""
    async def _run_case():
        engine = _engine()
        sm = _sessionmaker(engine)
        user_id = await _make_user(sm)
        try:
            async with _client(sm, _principal(user_id)) as ac:
                assert (
                    await ac.post(
                        "/api/place-cards",
                        json=_card_payload(name="   "),
                    )
                ).status_code == 422
                assert (
                    await ac.post(
                        "/api/place-cards",
                        json=_card_payload(logo_url="javascript:alert(1)"),
                    )
                ).status_code == 422
                assert (
                    await ac.post(
                        "/api/place-cards",
                        json=_card_payload(accent="red"),
                    )
                ).status_code == 422
                assert (
                    await ac.post(
                        "/api/place-cards",
                        json=_card_payload(kind="spaceship"),
                    )
                ).status_code == 422
        finally:
            await _drop_user(sm, user_id)
            await engine.dispose()

    _run(_run_case())
