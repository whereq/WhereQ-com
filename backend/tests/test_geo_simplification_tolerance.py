"""The outline's simplification — metres, at each place's own latitude.

THE RULE
--------
``ST_SimplifyPreserveTopology`` works on geometry, whose unit here is a
DEGREE — and a degree is not a fixed length. One degree of longitude is
about 111 km at the equator and about 81 km at Toronto, so a tolerance given
in metres has to be converted **at the place's own latitude** or it means
different things in different places. The budget is divided by the LARGER of
the two axes' metres-per-degree: a degree is the unit on both, so the binding
axis moves at most the budget and the other moves less.

WHY PER PLACE, NOT PER BATCH
----------------------------
The upstream simplifies the same way, and the two answers are compared
shape against shape. A per-batch tolerance makes one place's shape depend on
which other outlines happen to be in the same answer — so two readers that
batched the same places differently disagree about the same outline. That is
not a rounding difference; it is an outline that is right in one answer and
wrong in the other, and the ledger cannot tell which is which.

So the tolerance is computed per place, from the place's own latitude. The
same place is then the same shape here as it is upstream, whatever else is in
the batch.

THE TWO SIDES MUST AGREE
------------------------
The upstream wraps its simplified shape in ``ST_Multi(ST_CollectionExtract(…,
3))`` — a MultiPolygon, which is what the column holds. This side has to
wrap it the same way, or the two answers differ in kind rather than in
detail.
"""

from __future__ import annotations

import inspect
import math
import sqlite3

import pytest
from sqlalchemy.dialects import postgresql


def _sql_of(expression) -> str:
    return str(expression.compile(dialect=postgresql.dialect(),
                                  compile_kwargs={"literal_binds": True}))


def _evaluated_tolerance(metres: float, lat: float) -> float:
    """Run the route's own tolerance SQL and return the degrees it asks for.

    SQLite stands in for Postgres here: the expression is arithmetic, and
    ``cos``/``radians``/``max``/``min`` all exist in both. The point is to
    evaluate the TEXT the route sends, so a change in that text is a change
    in what is measured.
    """
    from app.api.routes.geo import _tolerance_expression

    sql = _sql_of(_tolerance_expression(metres))
    sql = sql.replace("geo_places.centroid_lat", str(lat))
    sql = sql.replace("GREATEST(", "max(").replace("LEAST(", "min(")
    sql = sql.replace("greatest(", "max(").replace("least(", "min(")
    conn = sqlite3.connect(":memory:")
    try:
        row = conn.execute(f"SELECT {sql}").fetchone()
    finally:
        conn.close()
    return float(row[0])


class TestTheRule:
    def test_the_tolerance_is_the_rule(self):
        from app.api.routes.geo import _simplify_tolerance_degrees

        metres, lat = 50.0, 43.65
        phi = math.radians(lat)
        m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
        m_per_deg_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
        assert _simplify_tolerance_degrees(metres, lat) == pytest.approx(
            metres / max(m_per_deg_lat, m_per_deg_lon), rel=1e-12)

    def test_the_same_metres_are_more_degrees_where_a_degree_is_shorter(self):
        """The budget is divided by the LONGEST degree — so where a degree is
        longer, the same number of metres is a smaller number of degrees."""
        from app.api.routes.geo import _simplify_tolerance_degrees

        assert _simplify_tolerance_degrees(50.0, 0.0) < _simplify_tolerance_degrees(50.0, 43.65)

    def test_no_simplification_means_no_tolerance(self):
        from app.api.routes.geo import _simplify_tolerance_degrees

        assert _simplify_tolerance_degrees(0, 43.65) == 0.0


class TestTheToleranceIsPerPlace:
    def test_the_route_simplifies_with_the_per_place_expression(self):
        from app.api.routes.geo import _boundaries

        source = inspect.getsource(_boundaries)
        assert "_tolerance_expression(metres)" in source, (
            "the outlines are not simplified at each place's own latitude"
        )

    def test_the_route_does_not_average_the_batch(self):
        """A per-batch tolerance makes one place's shape depend on its
        neighbours."""
        from app.api.routes.geo import _boundaries

        source = inspect.getsource(_boundaries)
        assert "sum(lats)" not in source
        assert "len(lats)" not in source

    def test_the_expression_uses_the_places_own_latitude(self):
        from app.api.routes.geo import GeoPlace, _tolerance_expression

        sql = _sql_of(_tolerance_expression(50.0))
        assert "centroid_lat" in sql
        assert "geo_places.centroid_lat" in sql

    def test_the_expression_does_not_average_anything(self):
        from app.api.routes.geo import _tolerance_expression

        sql = _sql_of(_tolerance_expression(50.0)).lower()
        assert "avg(" not in sql


class TestTheSqlIsTheRule:
    """The SQL the database runs, evaluated — not a copy of it."""

    def test_it_matches_the_python_rule_at_Toronto(self):
        from app.api.routes.geo import _simplify_tolerance_degrees

        assert _evaluated_tolerance(50.0, 43.65) == pytest.approx(
            _simplify_tolerance_degrees(50.0, 43.65), rel=1e-12)

    def test_it_matches_the_python_rule_at_the_equator(self):
        from app.api.routes.geo import _simplify_tolerance_degrees

        assert _evaluated_tolerance(50.0, 0.0) == pytest.approx(
            _simplify_tolerance_degrees(50.0, 0.0), rel=1e-12)

    def test_the_latitude_is_clamped_at_the_poles(self):
        """At the poles a degree of longitude collapses towards nothing, and
        the formula divides by it."""
        assert _evaluated_tolerance(50.0, 90.0) == pytest.approx(
            _evaluated_tolerance(50.0, 89.0), rel=1e-12)
        assert _evaluated_tolerance(50.0, -90.0) == pytest.approx(
            _evaluated_tolerance(50.0, -89.0), rel=1e-12)

    def test_it_stays_finite_at_the_pole(self):
        assert math.isfinite(_evaluated_tolerance(50.0, 90.0))
        assert _evaluated_tolerance(50.0, 90.0) > 0.0


class TestTheTwoSidesShareOneRule:
    def test_the_sql_and_the_python_rule_read_the_same_constants(self, monkeypatch):
        """The SQL the database runs and the readable Python rule must not be
        able to drift apart — so they read the SAME constants."""
        from app.api.routes import geo

        monkeypatch.setattr(geo, "M_PER_DEG_LAT", (1.0, 2.0, 3.0))
        monkeypatch.setattr(geo, "M_PER_DEG_LON", (4.0, 5.0))

        sql = _sql_of(geo._tolerance_expression(50.0))
        for constant in ("1.0", "2.0", "3.0", "4.0", "5.0"):
            assert constant in sql, f"{constant} is not in the SQL"

        # And the Python rule moved with them.
        phi = math.radians(43.65)
        expected = 50.0 / max(
            1.0 - 2.0 * math.cos(2 * phi) + 3.0 * math.cos(4 * phi),
            max(4.0 * math.cos(phi) - 5.0 * math.cos(3 * phi), 1.0),
        )
        assert geo._simplify_tolerance_degrees(50.0, 43.65) == pytest.approx(
            expected, rel=1e-12)

    def test_the_constants_are_the_geodesic_ones(self):
        from app.api.routes.geo import M_PER_DEG_LAT, M_PER_DEG_LON

        assert M_PER_DEG_LAT == (111132.92, 559.82, 1.175)
        assert M_PER_DEG_LON == (111412.84, 93.5)

    def test_the_expression_is_not_a_fixed_divisor(self):
        """A fixed divisor is 0.19 % off the real rule at Toronto's latitude
        — close enough to look right, different enough to change the answer."""
        from app.api.routes.geo import _tolerance_expression

        sql = _sql_of(_tolerance_expression(50.0))
        assert "111320" not in sql


class TestTheShapeIsTheSameKindOfObject:
    def test_the_outline_is_wrapped_like_the_upstream_wraps_it(self):
        """The upstream returns a MultiPolygon. A Polygon here and a
        MultiPolygon there are the same shape in different words — and the
        comparison counts polygons."""
        from app.api.routes.geo import _boundaries

        source = inspect.getsource(_boundaries)
        assert "ST_Multi" in source
        assert "ST_CollectionExtract" in source

    def test_the_simplifier_keeps_the_topology(self):
        """A plain ST_Simplify can collapse a MultiPolygon into a shape that
        no longer matches the place it came from."""
        from app.api.routes.geo import _boundaries

        assert "ST_SimplifyPreserveTopology" in inspect.getsource(_boundaries)
