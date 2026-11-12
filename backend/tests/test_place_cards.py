"""The user's own cards.

A card is a customised view of a place — the user's own, private until it is
published. These tests cover the three things that must hold:

* the router needs a session, and the list is always the caller's own;
* a card that is not yours is a **404**, not a 403 (it is private, so its
  existence is not public information);
* a card is **not** a place: it must never reach the ``places`` table, or it
  would become a map pin for everybody and inflate the category counts.
"""

import asyncio
import re


# ── the router ──────────────────────────────────────────────────────────────
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


def test_the_cards_router_is_registered():
    routes = list(_routes("/place-cards"))
    assert routes, "the place-cards router is not registered"
    paths = {r.path for r in routes}
    assert paths == {"/place-cards", "/place-cards/{card_id}"}


def test_the_cards_router_needs_a_session():
    from app.core.security import get_current_user, get_principal

    for route in _routes("/place-cards"):
        deps = _deps(route)
        assert get_current_user in deps or get_principal in deps, route.path


def test_the_cards_endpoints_require_a_session():
    """Without a token the cards are closed (401)."""
    import httpx

    from app.main import app

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            assert (await ac.get("/api/place-cards")).status_code == 401
            assert (await ac.post("/api/place-cards", json={})).status_code == 401
            assert (await ac.get("/api/place-cards/1")).status_code == 401

    asyncio.run(_run())


def test_the_list_is_always_the_callers_own():
    """There is no id in the path — the list is the caller's, by construction."""
    from app.main import app

    paths = {p for p in app.openapi()["paths"] if "place-cards" in p}
    assert paths == {"/api/place-cards", "/api/place-cards/{card_id}"}


# ── the ownership rule ──────────────────────────────────────────────────────
def test_a_card_that_is_not_yours_is_a_404():
    """A card is private until it is published: a 403 would confirm it exists."""
    from app.core.permissions import require_place_card_write_access
    from app.core.security import Principal

    class _Card:
        user_id = 7

    class _User:
        id = 9

    caller = Principal(user=_User(), claims={})
    staff = Principal(user=_User(), claims={"realm_access": {"roles": ["whereq-admin"]}})

    # Not the owner, not staff → 404, not 403.
    try:
        require_place_card_write_access(caller, _Card())
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 404, exc
    else:
        raise AssertionError("a card that is not yours must not be writable")

    # The owner may write it.
    owner = Principal(user=type("U", (), {"id": 7})(), claims={})
    require_place_card_write_access(owner, _Card())

    # Staff may override.
    require_place_card_write_access(staff, _Card())


# ── the model ───────────────────────────────────────────────────────────────
def test_a_card_is_not_a_place():
    """A card lives in its own table — a ``places`` row would become a map pin."""
    from app.models.place import Place
    from app.models.place_card import PlaceCard

    assert PlaceCard.__tablename__ == "place_cards"
    assert PlaceCard.__tablename__ != Place.__tablename__

    # The anchor is a point, but the card is not a place row.
    cols = PlaceCard.__table__.columns
    assert "latitude" in cols and "longitude" in cols
    # It has no place id: the card is anchored at an address, not at a place.
    assert "place_id" not in cols


def test_the_card_carries_the_publication_columns():
    """They are created with the table, so publishing needs no second migration."""
    from app.models.place_card import PlaceCard

    cols = PlaceCard.__table__.columns
    for name in ("status", "publish_token", "report_count", "view_count",
                 "published_at", "revoked_at"):
        assert name in cols, name


def test_the_publish_token_is_unique():
    from app.models.place_card import PlaceCard

    col = PlaceCard.__table__.columns["publish_token"]
    assert col.unique is True


def test_the_categories_are_a_list_and_the_radius_is_the_default_five():
    from app.models.place_card import PlaceCard

    cols = PlaceCard.__table__.columns
    # A card with no filter is an empty list, not a null.
    assert cols["categories"].nullable is False
    assert cols["categories"].server_default.arg == "{}"
    assert cols["radius_km"].default.arg == 5.0
    assert cols["radius_km"].nullable is False


# ── the schema ──────────────────────────────────────────────────────────────
def test_the_schema_cleans_the_input():
    from app.schemas.place_card import PlaceCardCreate

    card = PlaceCardCreate(
        name="  Markham Pan Am Centre  ",
        latitude=43.8, longitude=-79.3,
        categories=["Food", " coffee ", "food"],
        logo_url="https://example.com/logo.png",
        accent="#4ADE80",
    )
    assert card.name == "Markham Pan Am Centre"
    assert card.categories == ["food", "coffee"]
    assert card.radius_km == 5.0
    assert card.kind == "business"


def test_the_schema_rejects_a_bad_logo_or_accent():
    from pydantic import ValidationError

    from app.schemas.place_card import PlaceCardCreate

    def _bad(**kw):
        payload = {"name": "x", "latitude": 1.0, "longitude": 1.0, **kw}
        try:
            PlaceCardCreate(**payload)
        except ValidationError:
            return
        raise AssertionError(f"{kw} should have been rejected")

    _bad(logo_url="javascript:alert(1)")
    _bad(logo_url="/local/path.png")
    _bad(accent="green")
    _bad(accent="#12345")
    _bad(kind="something-else")
    _bad(name="   ")


def test_the_partial_update_leaves_the_rest_alone():
    from app.schemas.place_card import PlaceCardUpdate

    upd = PlaceCardUpdate()
    assert upd.name is None
    assert upd.radius_km is None
    assert upd.categories is None
    # An explicit null clears a field; an omitted one does not.
    assert PlaceCardUpdate(description=None).description is None


# ── the migration and the model must agree ─────────────────────────────────
def test_the_migration_carries_every_column_of_the_model():
    """A migration that drifts from its model is the classic silent bug: the
    column exists in the database and not in the code, or the other way."""
    from pathlib import Path

    from app.models.place_card import PlaceCard

    migration = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "017_place_cards.py"
    ).read_text(encoding="utf-8")

    created = set(re.findall(r'sa\.Column\("([a-z_]+)"', migration))
    modelled = set(PlaceCard.__table__.columns.keys())

    assert modelled - created == set(), "the migration is missing a column"
    assert created - modelled == set(), "the migration has a column the model does not"


def test_the_migration_is_the_head_of_the_chain():
    from pathlib import Path

    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    heads = {}
    for f in versions.glob("0*.py"):
        text = f.read_text(encoding="utf-8")
        rev = re.search(r'^revision = "([^"]+)"', text, re.M)
        down = re.search(r'^down_revision = "([^"]+)"', text, re.M)
        if rev and down:
            heads[rev.group(1)] = down.group(1)
        elif rev:
            heads[rev.group(1)] = None

    # 017 is in the chain — the geography migration (018) follows it, so it is
    # no longer the tip, but it must not be orphaned either.
    assert heads["017_place_cards"] == "016_reset_legacy_geocode_status"
    assert [r for r, d in heads.items() if d == "017_place_cards"] == ["018_geo_places"]


# ── the routes ─────────────────────────────────────────────────────────────
def test_a_new_card_belongs_to_its_creator_and_starts_as_a_draft():
    """The creator owns it, and it is not published until it is."""
    import asyncio

    from app.api.routes.place_cards import create_card
    from app.core.security import Principal
    from app.models.place_card import PlaceCard
    from app.schemas.place_card import PlaceCardCreate

    class _User:
        id = 42

    principal = Principal(user=_User(), claims={})

    class _Session:
        """Just enough of a session to watch what the route does."""

        def __init__(self):
            self.added = None

        async def execute(self, _stmt):
            class _R:
                def scalars(self_inner):
                    return self_inner

                def all(self_inner):
                    return []

            return _R()

        def add(self, obj):
            self.added = obj

        async def commit(self):
            return None

        async def refresh(self, obj):
            return obj

    db = _Session()
    payload = PlaceCardCreate(
        name="Markham Pan Am Centre", latitude=43.837, longitude=-79.316,
    )

    card = asyncio.run(create_card(payload, principal=principal, db=db))

    assert isinstance(card, PlaceCard)
    assert card.user_id == 42, "the creator must own the card"
    assert card.status == "draft", "a card is not published until it is"
    assert card.publish_token is None
    assert card.categories == []
    assert card.radius_km == 5.0
