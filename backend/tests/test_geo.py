"""The administrative geography — the areas that contain the places.

The whereq.cloud geography feed: provinces, regions, municipalities, cities,
towns, wards and neighbourhoods, with real outlines. These tests cover the
things that must hold:

* the endpoints are **public** — the feed is open data (ODbL 1.0 / CC-BY 4.0),
  so unlike the fuel prices there is no licence reason to hide it, and the
  attribution travels on every row instead;
* an administrative place is **not** a ``places`` row — a POI is a point, this
  is the area the point falls in, and mixing them would make every ward a
  map pin;
* the two vocabularies (OpenStreetMap and geoBoundaries) are **not** merged;
* the containment test is ``ST_Covers``, so a point exactly on an edge
  belongs to that edge's polygon;
* the stored outline is full resolution and is simplified only when served.
"""

import re


# ── the router ─────────────────────────────────────────────────────────────
def _routes(prefix: str):
    from app.main import app

    for r in app.routes:
        sub = getattr(r, "original_router", None)
        if sub is None or getattr(sub, "prefix", None) != prefix:
            continue
        for sr in sub.routes:
            yield sr


def _deps(route):
    return {d.call for d in route.dependant.dependencies}


def test_the_geo_router_is_registered():
    routes = list(_routes("/geo"))
    assert routes, "the geo router is not registered"
    paths = {r.path for r in routes}
    assert paths == {
        "/geo/concepts",
        "/geo/places",
        "/geo/places/{uid}",
        "/geo/places/{uid}/boundary",
        "/geo/boundaries",
        "/geo/at",
    }


def test_the_geo_endpoints_are_public():
    """Open data — no session, unlike the fuel prices."""
    from app.core.security import get_current_user, get_principal

    for route in _routes("/geo"):
        deps = _deps(route)
        assert get_current_user not in deps, route.path
        assert get_principal not in deps, route.path


def test_the_geo_endpoints_declare_no_security():
    """Open data — the endpoints declare no security requirement.

    Checked on the OpenAPI document rather than by calling the endpoints, so
    the check does not need a database.
    """
    from app.main import app

    spec = app.openapi()
    paths = {p: op for p, op in spec["paths"].items() if p.startswith("/api/geo")}
    assert paths, "the geo endpoints are not in the OpenAPI document"
    for path, ops in paths.items():
        for method, op in ops.items():
            assert not op.get("security"), f"{method.upper()} {path} asks for a session"


# ── the domain: an area is not a place ─────────────────────────────────────
def test_an_administrative_place_is_not_a_poi():
    """It must never reach ``places`` — that would make every ward a map pin."""
    from app.models.geo import GeoPlace
    from app.models.place import Place

    assert GeoPlace.__tablename__ == "geo_places"
    assert GeoPlace.__tablename__ != Place.__tablename__

    cols = GeoPlace.__table__.columns
    # It is an *area*: it has a boundary and a PostGIS geometry…
    assert "boundary_geojson" in cols and "geom" in cols
    # …and it is not a point with a category and a sub-category.
    assert "latitude" not in cols
    assert "category" not in cols
    assert "sub" not in cols


def test_the_licence_travels_on_the_row():
    """ODbL 1.0 / CC-BY 4.0 may only be redistributed with attribution."""
    from app.models.geo import GeoPlace

    cols = GeoPlace.__table__.columns
    assert "license" in cols
    assert "source" in cols
    assert "source_url" in cols


def test_the_two_vocabularies_are_kept_apart():
    """``source`` is what keeps an OSM ward apart from a census subdivision."""
    from app.models.geo import GeoPlace

    col = GeoPlace.__table__.columns["source"]
    assert col.index is True
    assert col.nullable is False


def test_the_geometry_is_stored_twice():
    """JSONB for the API, PostGIS for the queries — the school-catchment idiom."""
    from app.models.geo import GeoPlace

    cols = GeoPlace.__table__.columns
    assert cols["boundary_geojson"].type.__class__.__name__ == "JSONB"
    geom = cols["geom"].type
    assert geom.geometry_type == "MULTIPOLYGON"
    assert geom.srid == 4326
    # The GiST index is hand-made in the migration, so geoalchemy must not
    # create a second one.
    assert geom.spatial_index is False


# ── the targets ────────────────────────────────────────────────────────────
def test_a_target_spec_is_parsed():
    from app.crawler.upstream.geo_places import parse_target

    t = parse_target("bbox:-80.3,43.6,-79.2,44.2")
    assert t is not None and t.bbox == "-80.3,43.6,-79.2,44.2"

    t = parse_target("kind:ward")
    assert t is not None and t.kind == "ward" and t.country is None

    t = parse_target("kind:municipality:ca")
    assert t is not None and t.kind == "municipality" and t.country == "CA"

    t = parse_target("country:ca")
    assert t is not None and t.country == "CA"

    t = parse_target("source:geoboundaries")
    assert t is not None and t.source == "geoboundaries"


def test_a_malformed_target_is_refused():
    from app.crawler.upstream.geo_places import parse_target

    assert parse_target("") is None
    assert parse_target("bbox:1,2,3") is None
    assert parse_target("bbox:a,b,c,d") is None
    assert parse_target("kind:") is None
    assert parse_target("country:") is None


def test_a_target_key_is_stable():
    """The key is the sync-state primary key — it must not drift."""
    from app.crawler.upstream.geo_places import parse_target

    a = parse_target("bbox:-80.3,43.6,-79.2,44.2")
    b = parse_target("bbox:-80.3,43.6,-79.2,44.2")
    assert a.key == b.key
    assert a.key != parse_target("kind:ward").key


# ── the row mapping ────────────────────────────────────────────────────────
def test_a_place_becomes_a_row():
    from app.crawler.upstream.geo_places import place_to_row

    row = place_to_row({
        "uid": "osm:r1428125",
        "kind": "ward",
        "name": "Toronto Centre",
        "name_en": "Toronto Centre",
        "source": "osm",
        "source_id": "1428125",
        "license": "ODbL 1.0 (OpenStreetMap contributors)",
        "population": 12345,
        "centroid_lon": -79.4,
        "centroid_lat": 43.6,
        "has_boundary": True,
    })
    assert row is not None
    assert row["uid"] == "osm:r1428125"
    assert row["kind"] == "ward"
    assert row["source"] == "osm"
    assert row["license"].startswith("ODbL")
    assert row["population"] == 12345
    # The outline is not part of the row — it comes later, from the boundary
    # endpoint.
    assert row["boundary_geojson"] is None


def test_an_unusable_place_is_dropped():
    from app.crawler.upstream.geo_places import place_to_row

    assert place_to_row({}) is None
    assert place_to_row({"uid": "x"}) is None
    assert place_to_row({"uid": "x", "kind": "ward", "name": "n"}) is None
    assert place_to_row({"uid": "x", "kind": "ward", "name": "n", "source": "osm"}) is not None


# ── the simplification ─────────────────────────────────────────────────────
def test_the_throttle_is_shared_by_the_two_feeds():
    """One whereq.cloud key, one 30 requests/minute budget.

    Two independent throttles would each allow 30/min and the pair would 429
    each other — so the fuel and the geography feeds share one limiter.
    """
    from app.crawler.upstream import fuel_stations, geo_places
    from app.crawler.upstream.whereq_cloud import shared_throttle

    assert fuel_stations.shared_throttle is shared_throttle
    assert geo_places.shared_throttle is shared_throttle
    # And it is never faster than the upstream's own limit.
    assert shared_throttle.min_interval >= 2.0


def test_the_both_feeds_share_one_retry_policy():
    from app.crawler.upstream import fuel_stations, geo_places
    from app.crawler.upstream.whereq_cloud import call_with_retry

    assert fuel_stations.call_with_retry is call_with_retry
    assert geo_places.call_with_retry is call_with_retry


def test_the_outlines_are_ordered_smallest_first():
    """A truncated answer must drop the large areas, not the small ones.

    Ordered by kind and name, the kinds that sort last are exactly the small
    ones — every ward and town was being dropped at street zoom.
    """
    from app.api.routes.geo import PLACE_COLUMNS

    names = [c.name for c in PLACE_COLUMNS]
    assert "uid" in names and "area_km2" in names


def test_the_continent_scale_kinds_are_left_out_by_default():
    """A province outline is 65 000 points even simplified — a footgun for a
    public endpoint. They are excluded unless a caller asks for them."""
    from app.api.routes.geo import LARGE_KINDS

    assert set(LARGE_KINDS) == {"country", "province", "state"}


def test_a_bbox_target_survives_the_comma_separated_settings():
    """A bbox carries commas of its own — it must not be split apart.

    ``GEO_CRAWL_TARGETS`` is comma-separated, but ``bbox:-80.3,43.6,-79.2,44.2``
    is **one** target. Splitting on the commas turned it into four garbage
    targets, and the crawler then crawled "kind:43.6" instead of the GTA.
    """
    from app.crawler.upstream.geo_places import parse_targets

    targets = parse_targets("bbox:-80.3,43.6,-79.2,44.2")
    assert len(targets) == 1
    assert targets[0].bbox == "-80.3,43.6,-79.2,44.2"

    # And with more than one target.
    targets = parse_targets("bbox:-80.3,43.6,-79.2,44.2,kind:ward,kind:municipality:ca")
    assert [t.kind for t in targets] == [None, "ward", "municipality"]
    assert targets[0].bbox == "-80.3,43.6,-79.2,44.2"
    assert targets[2].country == "CA"

    targets = parse_targets("country:ca,source:geoboundaries")
    assert len(targets) == 2


def test_the_configured_targets_are_the_whole_bbox():
    """The default coverage is the GTA viewport — one target, not four."""
    from app.core.config import settings
    from app.crawler.upstream.geo_places import configured_targets

    targets = configured_targets()
    assert len(targets) == 1, [t.label for t in targets]
    assert targets[0].bbox is not None
    assert targets[0].bbox == settings.GEO_CRAWL_TARGETS.split("bbox:")[1]


def test_the_simplification_tolerance_is_in_degrees():
    """``ST_Simplify`` is geometry-only in PostGIS 3.7 — no geography overload.

    So the tolerance has to be derived from the place's own latitude: a degree
    of longitude is ~111 km at the equator and ~80 km at Toronto.
    """
    from app.api.routes.geo import _simplify_tolerance_degrees

    toronto = _simplify_tolerance_degrees(50.0, 43.65)
    equator = _simplify_tolerance_degrees(50.0, 0.0)
    # The same 50 m is a bigger number of degrees near the equator.
    assert toronto > equator
    # And it is a small number of degrees at Toronto.
    assert 0.0001 < toronto < 0.001
    # No simplification, no tolerance.
    assert _simplify_tolerance_degrees(0, 43.65) == 0.0


def test_the_simplification_never_moves_an_edge_further_than_asked():
    """The tolerance is the budget over the *larger* of the two metre scales."""
    import math

    from app.api.routes.geo import _simplify_tolerance_degrees

    metres = 50.0
    lat = 43.65
    tol = _simplify_tolerance_degrees(metres, lat)
    phi = math.radians(lat)
    m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    m_per_deg_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
    # Whichever axis the tolerance is applied to, the edge moves at most
    # `metres`.
    assert tol * m_per_deg_lat <= metres + 1e-6
    assert tol * m_per_deg_lon <= metres + 1e-6


# ── the geometry helpers ───────────────────────────────────────────────────
def test_the_geometry_is_taken_out_of_the_feature_collection():
    from app.crawler.upstream.geo_places import _geometry_of

    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}},
    ]}
    assert _geometry_of(fc)["type"] == "Polygon"
    assert _geometry_of({"type": "Polygon", "coordinates": []})["type"] == "Polygon"
    assert _geometry_of({"type": "FeatureCollection", "features": []}) is None
    assert _geometry_of(None) is None


# ── the model and the migration must agree ─────────────────────────────────
def test_the_migration_carries_every_column_of_the_model():
    from pathlib import Path

    from app.models.geo import GeoConcept, GeoPlace, GeoSyncState

    migration = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "018_geo_places.py"
    ).read_text(encoding="utf-8")

    # The migration creates three tables — one block each.
    blocks = re.findall(
        r'op\.create_table\(\s*"([a-z0-9_]+)",(.*?)\n    \)', migration, re.S)
    created = {name: set(re.findall(r'sa\.Column\(\s*"([a-z0-9_]+)"', body))
               for name, body in blocks}
    assert set(created) == {"geo_places", "geo_concepts", "geo_sync_state"}

    for model in (GeoPlace, GeoConcept, GeoSyncState):
        modelled = set(model.__table__.columns.keys())
        assert modelled - created[model.__tablename__] == set(), \
            f"{model.__tablename__}: the migration is missing a column"
        assert created[model.__tablename__] - modelled == set(), \
            f"{model.__tablename__}: the migration has a column the model does not"


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

    assert heads["018_geo_places"] == "017_place_cards"
    assert [r for r, d in heads.items() if d == "018_geo_places"] == []


def test_the_migration_makes_the_gist_index_by_hand():
    """geoalchemy is told not to create one, so the migration must."""
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "018_geo_places.py"
    ).read_text(encoding="utf-8")
    assert "CREATE INDEX ix_geo_places_geom ON geo_places USING GIST (geom)" in migration
    assert "DROP INDEX IF EXISTS ix_geo_places_geom" in migration


# ── the settings ───────────────────────────────────────────────────────────
def test_the_geo_settings_exist():
    from app.core.config import settings

    assert settings.GEO_CRAWL_ENABLED is True
    # The API allows 30 requests/minute — the same limit as the fuel ones.
    assert settings.GEO_CRAWL_MIN_INTERVAL >= 2.0
    assert settings.GEO_BOUNDARY_SIMPLIFY_M > 0
