"""Cutting the outlines over to whereq.cloud — the last geography surface.

THE SIXTH SURFACE
-----------------
whereq.com's geography has six surfaces. Five read whereq.cloud directly.
The sixth — the **outlines** — read the local mirror, and the reason was
the shape of the upstream API: whereq.cloud served outlines one place at a
time (``/v1/geo/places/{uid}/boundary``), so a map pan would have cost one
upstream request per polygon, far past the 30 requests/minute the API
allows.

whereq.cloud now serves ``GET /v1/geo/boundaries`` — a viewport's worth of
outlines in one request, with the attribution on every item — so the cut
is possible and the mirror can stop.

THE TWO ANSWERS ARE THE SAME SET
--------------------------------
The upstream is asked for the same viewport, the same kinds and the same
exclusion of the country, the province and the state that this app's own
query applies, so the two answers are like with like and the comparison is
a comparison rather than a report of two different populations.

THE OUTLINE IS COMPARED BY ITS MEASUREMENTS
--------------------------------------------
An outline is a shape, and two identical shapes do not have the same text
on the two sides — they come out of different serialisers through
different simplifications. They are compared by what they are: how many
polygons, how many vertices, how big, and where.
"""

from __future__ import annotations

import inspect


# ── the reader ─────────────────────────────────────────────────────────────
def test_the_reader_reads_the_bulk_endpoint():
    """One request for a viewport, not one per polygon."""
    from app.services.cloud_geo import fetch_cloud_boundaries

    source = inspect.getsource(fetch_cloud_boundaries)
    assert "geo_boundaries" in source, (
        "the reader still asks for the outlines one place at a time"
    )


def test_the_reader_asks_for_the_same_set_this_app_asks_for():
    """The viewport, the kinds, the exclusion and the simplification."""
    from app.services.cloud_geo import fetch_cloud_boundaries

    signature = inspect.signature(fetch_cloud_boundaries)
    for name in ("bbox", "kinds", "excluded_kinds", "sources", "simplify_m", "limit"):
        assert name in signature.parameters, f"{name} is not a filter the reader passes"


def test_the_reader_carries_the_attribution():
    """ODbL and CC-BY both require it, and the local copy carried it."""
    from app.services.cloud_geo import boundaries_to_read

    items = boundaries_to_read({"items": [{
        "uid": "osm:r1", "name": "A", "kind": "ward", "source": "osm",
        "license": "ODbL 1.0 (OpenStreetMap contributors)",
        "source_url": "https://www.openstreetmap.org/relation/1",
        "area_km2": 1.5, "centroid_lon": -79.4, "centroid_lat": 43.6,
        "simplified_m": 50.0, "geometry": {"type": "Polygon", "coordinates": []},
    }]})
    assert items[0]["license"] == "ODbL 1.0 (OpenStreetMap contributors)"
    assert items[0]["source_url"].endswith("/1")
    assert items[0]["geometry"]["type"] == "Polygon"


def test_the_reader_returns_nothing_for_an_empty_answer():
    from app.services.cloud_geo import boundaries_to_read

    assert boundaries_to_read({}) == []
    assert boundaries_to_read({"items": []}) == []


# ── the route ───────────────────────────────────────────────────────────────
def test_the_route_reads_the_upstream_in_cloud_mode():
    """The cut is in the route, not in a flag somebody has to remember."""
    from app.api.routes import geo

    source = inspect.getsource(geo.geo_boundaries)
    assert 'mode == "cloud"' in source
    assert "_cloud_boundaries" in source


def test_the_route_asks_for_the_same_exclusion_the_local_query_applies():
    """No kind asked for → the drawable set on both sides."""
    from app.api.routes import geo

    source = inspect.getsource(geo.geo_boundaries)
    assert "excluded_kinds=None if kinds else list(LARGE_KINDS)" in source, (
        "the upstream is asked for a different set than the local query "
        "selects, so the two answers cannot be compared"
    )


def test_the_route_says_whether_the_upstream_answer_was_truncated():
    """A client that draws polygons must be able to tell."""
    from app.api.routes import geo

    source = inspect.getsource(geo.geo_boundaries)
    assert 'truncated=bool(payload.get("truncated"))' in source


def test_an_empty_upstream_answer_falls_back_and_says_so():
    """An empty upstream answer is a failure that looks like an empty map."""
    from app.api.routes import geo

    source = inspect.getsource(geo.geo_boundaries)
    assert "the upstream returned no outlines" in source


def test_the_outlines_have_their_own_switch():
    """Their cut needed a bulk geometry endpoint, so their window is their
    own decision — and a map already reading whereq.cloud's thirty thousand
    places must not drop back to the mirror's three hundred while one
    surface gathers its evidence."""
    from app.api.routes import geo

    source = inspect.getsource(geo)
    assert "GEO_BOUNDARIES_READ_MODE" in source
    assert "def _boundaries_mode" in source


def test_the_outlines_switch_falls_back_to_the_geography_one():
    """One switch for the whole geography, unless the operator wants
    otherwise."""
    from app.api.routes import geo

    source = inspect.getsource(geo._boundaries_mode)
    assert "_mode()" in source, "the outlines do not fall back to the geography's switch"


def test_the_dual_mode_records_the_comparison():
    from app.api.routes import geo

    source = inspect.getsource(geo.geo_boundaries)
    assert "_record_boundaries_parity" in source


# ── the comparison ──────────────────────────────────────────────────────────
def test_the_outline_is_compared_by_its_measurements():
    """Two identical shapes do not have the same text."""
    from app.services.cloud_geo_parity import BOUNDARY_FIELDS

    assert "polygon_count" in BOUNDARY_FIELDS
    assert "vertex_count" in BOUNDARY_FIELDS
    assert "bbox" in BOUNDARY_FIELDS
    assert "geometry" not in BOUNDARY_FIELDS, (
        "the raw geometry is not comparable — two identical shapes have two "
        "different texts"
    )


def test_the_attribution_is_compared_too():
    """A difference here means one side cannot be attributed."""
    from app.services.cloud_geo_parity import BOUNDARY_FIELDS

    assert "license" in BOUNDARY_FIELDS
    assert "source_url" in BOUNDARY_FIELDS


def test_the_vertex_count_does_not_count_the_closing_point():
    """A GeoJSON ring repeats its first position."""
    from app.services.cloud_geo_parity import boundary_to_read

    read = boundary_to_read({
        "uid": "osm:r1", "kind": "ward",
        "geometry": {"type": "Polygon", "coordinates": [[
            [0, 0], [1, 0], [1, 1], [0, 0],
        ]]},
    })
    assert read["vertex_count"] == 3, "the ring's closing point was counted twice"
    assert read["polygon_count"] == 1


def test_a_multipolygon_counts_its_own_polygons():
    from app.services.cloud_geo_parity import boundary_to_read

    read = boundary_to_read({
        "uid": "osm:r1", "kind": "ward",
        "geometry": {"type": "MultiPolygon", "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            [[[2, 2], [3, 2], [3, 3], [2, 2]]],
        ]},
    })
    assert read["polygon_count"] == 2


def test_the_same_shape_on_both_sides_is_a_match():
    from app.services.cloud_geo_parity import compare_boundaries

    shape = {"uid": "osm:r1", "name": "A", "kind": "ward", "source": "osm",
             "license": "ODbL 1.0", "source_url": "https://example/1",
             "area_km2": 1.5, "geometry": {"type": "Polygon", "coordinates": [[
                 [0, 0], [1, 0], [1, 1], [0, 0]]]}}
    result = compare_boundaries([shape], [dict(shape)])
    assert not result["only_local"]
    assert not result["differing"]


def test_a_different_shape_is_a_difference():
    from app.services.cloud_geo_parity import compare_boundaries

    left = {"uid": "osm:r1", "kind": "ward", "license": "ODbL 1.0",
            "geometry": {"type": "Polygon", "coordinates": [[
                [0, 0], [1, 0], [1, 1], [0, 0]]]}}
    right = dict(left)
    right["geometry"] = {"type": "Polygon", "coordinates": [[
        [0, 0], [2, 0], [2, 2], [0, 0]]]}
    result = compare_boundaries([left], [right])
    assert "osm:r1" in result["differing"]
    # The shape moved, so its extent moved. The vertex count did not — the
    # two rings have the same number of points — and the comparison says
    # exactly which fields disagree, not merely that something did.
    assert "bbox" in result["differing"]["osm:r1"]
    assert "vertex_count" not in result["differing"]["osm:r1"]


def test_a_shape_with_another_number_of_vertices_is_a_difference():
    from app.services.cloud_geo_parity import compare_boundaries

    left = {"uid": "osm:r1", "kind": "ward", "license": "ODbL 1.0",
            "geometry": {"type": "Polygon", "coordinates": [[
                [0, 0], [1, 0], [1, 1], [0, 0]]]}}
    right = dict(left)
    right["geometry"] = {"type": "Polygon", "coordinates": [[
        [0, 0], [1, 0], [1, 1], [0.5, 0.5], [0, 0]]]}
    result = compare_boundaries([left], [right])
    assert "vertex_count" in result["differing"]["osm:r1"]


def test_a_missing_attribution_is_a_difference():
    """Not a formality: a shape nobody can attribute cannot be served."""
    from app.services.cloud_geo_parity import compare_boundaries

    left = {"uid": "osm:r1", "kind": "ward", "license": "ODbL 1.0",
            "geometry": {"type": "Polygon", "coordinates": [[
                [0, 0], [1, 0], [1, 1], [0, 0]]]}}
    right = dict(left)
    right["license"] = None
    result = compare_boundaries([left], [right])
    assert "license" in result["differing"]["osm:r1"]


def test_a_row_only_the_upstream_has_is_coverage_not_a_defect():
    """The upstream holds every place in the country; the mirror holds the
    ones in this app's coverage. The extra ones are not a disagreement."""
    from app.services.cloud_geo_parity import compare_boundaries

    left = {"uid": "osm:r1", "kind": "ward"}
    right = {"uid": "osm:r2", "kind": "ward"}
    result = compare_boundaries([left], [right])
    assert result["only_local"] == ["osm:r1"]
    assert result["only_cloud"] == ["osm:r2"]
