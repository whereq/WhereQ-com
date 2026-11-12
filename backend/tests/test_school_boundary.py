"""The catchment outline of a school — the endpoint the map draws.

A school is not a point: it serves an *area*. When the user picks a school on
the map, the map asks for that area and draws it. These tests check the
things that must hold:

* the endpoint exists and answers with a **GeoJSON MultiPolygon** — a school
  may have several catchment polygons (a multi-campus school), so a single
  Polygon would lose the others;
* it is **gated**: the catchment polygons are the school board's licensed
  data, so an anonymous caller must not get them (the map offers the sign-in
  instead of a silent nothing);
* a school with **no** boundary answers 404 — "there is no outline for this
  one" — rather than an empty geometry the caller has to guess about.
"""

import re
from pathlib import Path


ROUTES_SOURCE = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "schools.py"


# ── the wiring ─────────────────────────────────────────────────────────────
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


def test_the_school_boundary_endpoint_is_registered():
    paths = {r.path for r in _routes("/schools")}
    assert "/schools/{school_id}/boundary" in paths


def test_the_school_boundary_is_gated():
    """The catchment polygons are the board's licensed data."""
    from app.core.security import get_current_user

    route = next(r for r in _routes("/schools") if r.path == "/schools/{school_id}/boundary")
    assert get_current_user in _deps(route)


def test_the_school_boundary_asks_for_a_session_in_the_openapi_document():
    from app.main import app

    spec = app.openapi()
    op = spec["paths"]["/api/schools/{school_id}/boundary"]["get"]
    assert op.get("security"), "the catchment endpoint asks for no session"


def test_the_school_boundary_answers_a_multipolygon():
    """Several catchment polygons are one MultiPolygon — never a bare Polygon."""
    from app.schemas.school import SchoolBoundaryOut

    out = SchoolBoundaryOut(
        school_id=1,
        name="A School",
        geometry={"type": "MultiPolygon", "coordinates": []},
    )
    assert out.geometry["type"] == "MultiPolygon"
    assert out.polygon_count == 0
    assert out.point_count == 0


def test_a_school_without_a_boundary_is_a_404_not_an_empty_geometry():
    """The route must not answer 200 with an empty shape."""
    source = ROUTES_SOURCE.read_text(encoding="utf-8")
    body = source.split("async def school_boundary(", 1)[1]
    body = body.split("\n@router.get", 1)[0]
    assert 'status_code=404' in body
    # The 404 says *why*: there is no boundary for this school.
    assert "has no boundary" in body


def test_the_point_count_counts_positions_not_coordinates():
    """A stored ring of 36 points is 36 points, not 72.

    A GeoJSON Polygon's ``coordinates`` is a list of rings and a ring is a
    list of ``[lng, lat]`` positions, so counting the *length of each
    position* would double every point.
    """
    from app.api.routes.schools import _count_points

    ring = [[-79.1 + i * 0.001, 43.8 + i * 0.001] for i in range(36)]
    assert _count_points([ring]) == 36
    # Two rings (a polygon with a hole) add up.
    assert _count_points([ring, ring[:10]]) == 46
    assert _count_points([]) == 0
