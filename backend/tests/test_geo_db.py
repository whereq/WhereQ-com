"""The geography API against a **real** Postgres.

``test_geo.py`` next door checks the wiring with a faked session. This file
proves the other half: that migration ``018_geo_places`` produces a schema the
ORM, the PostGIS queries and the routes actually work against — real SQL, real
geometry, real point-in-polygon.

It is **opt-in**. It runs only when ``WHEREQ_TEST_DATABASE_URL`` points at a
Postgres that has already been migrated, so the default ``pytest`` run never
touches a database — and can never touch somebody's production one by
accident.

    DATABASE_URL=... DATABASE_URL_SYNC=... alembic upgrade head
    WHEREQ_TEST_DATABASE_URL=postgresql+asyncpg://user@127.0.0.1:5432/whereq_test \
        pytest tests/test_geo_db.py -v

Everything it creates, it deletes again.

The recipe for a Postgres without root (no Docker, no sudo) is in the
docstring of ``tests/test_place_cards_db.py``.
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


def _client(sm):
    """The real app, with only the session replaced.

    No session is overridden: the geography endpoints are **public**, and the
    whole point of these tests is that they answer for an anonymous caller.
    """
    import httpx

    from app.core.database import get_db
    from app.main import app

    async def _db():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _clear_overrides():
    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides.pop(get_db, None)


# ── the fixtures ───────────────────────────────────────────────────────────
#: A small square around downtown Toronto, as GeoJSON.
_SQUARE = {
    "type": "Polygon",
    "coordinates": [[
        [-79.40, 43.64], [-79.38, 43.64], [-79.38, 43.66],
        [-79.40, 43.66], [-79.40, 43.64],
    ]],
}

#: A second square, further east, so two areas overlap.
_SQUARE_EAST = {
    "type": "Polygon",
    "coordinates": [[
        [-79.37, 43.64], [-79.35, 43.64], [-79.35, 43.66],
        [-79.37, 43.66], [-79.37, 43.64],
    ]],
}

#: A point inside the first square.
_INSIDE = (43.65, -79.39)
#: A point exactly on its western edge.
_ON_EDGE = (43.65, -79.40)


def _place(uid: str, kind: str, name: str, source: str, geometry: dict) -> dict:
    """A place row, as the crawl would write it.

    The feed always supplies the place's own bounding box — the viewport
    filter uses it, so a place without one would never appear in a viewport.
    """
    from app.crawler.upstream.geo_places import place_to_row

    row = place_to_row({
        "uid": uid,
        "kind": kind,
        "name": name,
        "source": source,
        "source_id": uid.split(":")[-1],
        "source_url": "https://example.com/source",
        "license": "ODbL 1.0 (OpenStreetMap contributors)",
        "centroid_lon": -79.39,
        "centroid_lat": 43.65,
        "bbox_min_lon": -79.40,
        "bbox_min_lat": 43.64,
        "bbox_max_lon": -79.38,
        "bbox_max_lat": 43.66,
        "has_boundary": True,
    })
    row["boundary_geojson"] = geometry
    return row


async def _seed(sm, rows: list[dict]):
    """Write the places and the vocabulary."""
    from app.crawler.upstream.geo_places import upsert_concepts, upsert_places

    async with sm() as s:
        await upsert_concepts(s, [
            {"kind": "neighbourhood", "name": "Neighbourhood", "rank": 10, "places": 1},
            {"kind": "ward", "name": "Ward", "rank": 9, "places": 1},
            {"kind": "city", "name": "City", "rank": 5, "places": 1},
        ])
        await upsert_places(s, rows)


async def _sweep(sm, uids: list[str]):
    """Remove the rows this test created.

    Only the places it seeded — the crawl state belongs to the installation, so
    it is left alone (the tests never write it).
    """
    from sqlalchemy import delete

    from app.models.geo import GeoPlace

    async with sm() as s:
        await s.execute(delete(GeoPlace).where(GeoPlace.uid.in_(uids)))
        await s.commit()


# ── the tests ──────────────────────────────────────────────────────────────
def test_the_endpoints_answer_for_an_anonymous_caller():
    """Open data — no session, no 401."""
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        uid = f"test:{uuid.uuid4().hex[:10]}"
        await _seed(sm, [_place(uid, "ward", "Test Ward", "osm", _SQUARE)])
        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get("/api/geo/places", params={"bbox": "-79.5,43.6,-79.3,43.7"})
                assert res.status_code == 200, res.status_code
                assert any(p["uid"] == uid for p in res.json())

                res = await ac.get("/api/geo/concepts")
                assert res.status_code == 200
                kinds = {c["kind"] for c in res.json()}
                assert {"ward", "neighbourhood", "city"} <= kinds

                res = await ac.get("/api/geo/places/" + uid)
                assert res.status_code == 200
                assert res.json()["license"].startswith("ODbL")
        finally:
            _clear_overrides()
            await _sweep(sm, [uid])
            await engine.dispose()

    asyncio.run(_run())


def test_a_point_is_contained_by_the_area_that_holds_it():
    """The containment stack, answered locally with PostGIS."""
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        uid = f"test:{uuid.uuid4().hex[:10]}"
        await _seed(sm, [_place(uid, "ward", "Test Ward", "osm", _SQUARE)])
        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get("/api/geo/at", params={"lat": _INSIDE[0], "lng": _INSIDE[1]})
                assert res.status_code == 200
                places = res.json()["places"]
                assert "Test Ward" in [p["name"] for p in places]

                # The stack is broadest first — the kinds come back in the
                # order of the vocabulary's own ranks (country, province,
                # region, …, ward, neighbourhood).
                res = await ac.get("/api/geo/concepts")
                ranks = {c["kind"]: c["rank"] for c in res.json()}
                ranks.setdefault("ward", 9)
                ranks.setdefault("neighbourhood", 10)
                ranks.setdefault("city", 5)
                seen = [ranks.get(p["kind"], 100) for p in places]
                assert seen == sorted(seen), places
        finally:
            _clear_overrides()
            await _sweep(sm, [uid])
            await engine.dispose()

    asyncio.run(_run())


def test_a_point_on_the_edge_belongs_to_the_area():
    """``ST_Covers``, not ``ST_Contains``: an edge point is inside the polygon."""
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        uid = f"test:{uuid.uuid4().hex[:10]}"
        await _seed(sm, [_place(uid, "ward", "Edge Ward", "osm", _SQUARE)])
        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get("/api/geo/at", params={"lat": _ON_EDGE[0], "lng": _ON_EDGE[1]})
                assert res.status_code == 200
                assert "Edge Ward" in [p["name"] for p in res.json()["places"]]
        finally:
            _clear_overrides()
            await _sweep(sm, [uid])
            await engine.dispose()

    asyncio.run(_run())


def test_the_boundary_comes_back_as_geojson():
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        uid = f"test:{uuid.uuid4().hex[:10]}"
        await _seed(sm, [_place(uid, "neighbourhood", "Outline", "osm", _SQUARE)])
        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get(f"/api/geo/places/{uid}/boundary")
                assert res.status_code == 200
                body = res.json()
                assert body["geometry"]["type"] in ("Polygon", "MultiPolygon")
                assert body["geometry"]["coordinates"]
                assert body["source"] == "osm"
                assert body["license"].startswith("ODbL")

                # And in bulk, for the map layer.
                res = await ac.get("/api/geo/boundaries",
                                   params={"bbox": "-79.5,43.6,-79.3,43.7"})
                assert res.status_code == 200
                body = res.json()
                assert body["total"] >= 1
                assert body["truncated"] is False
                assert any(b["uid"] == uid for b in body["items"])
        finally:
            _clear_overrides()
            await _sweep(sm, [uid])
            await engine.dispose()

    asyncio.run(_run())


def test_the_two_vocabularies_stay_apart():
    """The same area under both sources is two rows, not one merged row."""
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        tag = uuid.uuid4().hex[:10]
        osm_uid = f"test:{tag}:osm"
        gb_uid = f"test:{tag}:gb"
        await _seed(sm, [
            _place(osm_uid, "ward", "Same Ward", "osm", _SQUARE),
            _place(gb_uid, "ward", "Same Ward", "geoboundaries", _SQUARE),
        ])
        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get("/api/geo/places",
                                   params={"bbox": "-79.5,43.6,-79.3,43.7", "kind": "ward"})
                uids = {p["uid"] for p in res.json()}
                assert osm_uid in uids and gb_uid in uids
                sources = {p["source"] for p in res.json()}
                assert sources == {"osm", "geoboundaries"}
        finally:
            _clear_overrides()
            await _sweep(sm, [osm_uid, gb_uid])
            await engine.dispose()

    asyncio.run(_run())


def test_a_place_sync_does_not_wipe_an_outline_it_did_not_fetch():
    """The coalesce in the upsert: a rows-only crawl keeps the outline."""
    from app.crawler.upstream.geo_places import place_to_row, upsert_places

    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        uid = f"test:{uuid.uuid4().hex[:10]}"
        await _seed(sm, [_place(uid, "ward", "Keep Outline", "osm", _SQUARE)])

        # A rows-only crawl: the same place, but without the outline.
        row = place_to_row({
            "uid": uid, "kind": "ward", "name": "Keep Outline", "source": "osm",
            "has_boundary": True,
        })
        async with sm() as s:
            await upsert_places(s, [row])

        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get(f"/api/geo/places/{uid}/boundary")
                assert res.status_code == 200, "the outline was wiped"
                assert res.json()["geometry"]["coordinates"]
        finally:
            _clear_overrides()
            await _sweep(sm, [uid])
            await engine.dispose()

    asyncio.run(_run())


def test_a_truncated_answer_says_so():
    """A client that draws polygons must be able to tell "that is all of them"
    from "that is the first N" — or it will draw a map with holes in it."""
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        uids = [f"test:{uuid.uuid4().hex[:10]}:{i}" for i in range(3)]
        await _seed(sm, [_place(u, "ward", f"Ward {i}", "osm", _SQUARE) for i, u in enumerate(uids)])
        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get("/api/geo/boundaries",
                                   params={"bbox": "-79.5,43.6,-79.3,43.7", "limit": 2})
                assert res.status_code == 200
                body = res.json()
                assert body["total"] >= 3
                assert body["truncated"] is True
                assert len(body["items"]) == 2
        finally:
            _clear_overrides()
            await _sweep(sm, uids)
            await engine.dispose()

    asyncio.run(_run())


def test_a_failed_sync_keeps_the_last_successful_one():
    """A failure must not look like a success — and must not lose the last one."""
    from sqlalchemy import text

    from app.crawler.upstream.geo_places import GeoTarget, mark_state

    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        target = GeoTarget(kind="ward")
        query = text(
            "SELECT last_synced_at, last_error FROM geo_sync_state WHERE target_key = :k")
        async with sm() as s:
            await mark_state(s, target, places=7, boundaries=3)
            # Read it with raw SQL: a Core-level UPDATE does not refresh the
            # ORM's identity map, so an ORM read here would be stale.
            row = (await s.execute(query, {"k": target.key})).first()
            synced = row[0]
            assert synced is not None
            assert row[1] is None

            await mark_state(s, target, error="boom")
            row = (await s.execute(query, {"k": target.key})).first()
            # The last *successful* crawl is kept…
            assert row[0] == synced
            # …and the failure is recorded.
            assert row[1] == "boom"

            await s.execute(
                text("DELETE FROM geo_sync_state WHERE target_key = :k"),
                {"k": target.key})
            await s.commit()
        await engine.dispose()

    asyncio.run(_run())


def test_an_area_with_no_boundary_is_a_404():
    engine = _engine()
    sm = _sessionmaker(engine)

    async def _run():
        uid = f"test:{uuid.uuid4().hex[:10]}"
        await _seed(sm, [_place(uid, "ward", "No Outline", "osm", _SQUARE)])
        async with sm() as s:
            from sqlalchemy import update

            from app.models.geo import GeoPlace

            await s.execute(
                update(GeoPlace).where(GeoPlace.uid == uid)
                .values(boundary_geojson=None, geom=None)
            )
            await s.commit()

        client = _client(sm)
        try:
            async with client as ac:
                res = await ac.get(f"/api/geo/places/{uid}/boundary")
                assert res.status_code == 404
        finally:
            _clear_overrides()
            await _sweep(sm, [uid])
            await engine.dispose()

    asyncio.run(_run())
