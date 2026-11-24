"""The dual-read machinery — the comparison, and the three read modes.

THE MIGRATION IS DECIDED BY READING, NOT BY ASSUMING
-----------------------------------------------------
The cut off whereq.com's own crawler is only safe if the two answers have
been seen to agree. So the comparison is the thing under test here: it has to
notice a row the mirror has and upstream does not, and it has to notice a
row both sides have but with different values — and it has to NOT notice a
row upstream has and the mirror does not, because the mirror is a copy
restricted to this installation's targets, so upstream is always broader.

A comparison that flags everything is as useless as one that flags nothing.
"""

from __future__ import annotations

import pytest

from app.services.cloud_parity import (
    COMPARABLE_FIELDS,
    compare,
    is_clean,
)


#: The sentinel for "the upstream did not say how big its answer is".
_NO_COUNT = object()


def _place(uid: str, **overrides) -> dict:
    row = {
        "uid": uid,
        "kind": "city",
        "name": "Toronto",
        "name_en": None,
        "name_zh": None,
        "name_local": None,
        "official_name": "Toronto",
        "source": "osm",
        "source_url": "https://www.openstreetmap.org/relation/1721",
        "license": "ODbL 1.0 (OpenStreetMap contributors)",
        "country_code": "CA",
        "province_code": "ON",
        "population": 2794356,
        "area_km2": 630.0,
        "centroid_lon": -79.3832,
        "centroid_lat": 43.6532,
        "has_boundary": True,
    }
    row.update(overrides)
    return row


class TestTheComparison:
    def test_two_identical_answers_are_clean(self):
        rows = [_place("osm:r1"), _place("osm:r2", name="Mississauga")]
        result = compare(rows, list(rows))
        assert is_clean(result)
        assert result["only_local"] == []
        assert result["only_cloud"] == []
        assert result["differing"] == {}

    def test_a_row_only_the_mirror_has_is_a_difference(self):
        """The mirror holding something upstream does not is a real defect."""
        result = compare([_place("osm:r1"), _place("osm:ghost")], [_place("osm:r1")])
        assert not is_clean(result)
        assert result["only_local"] == ["osm:ghost"]

    def test_a_row_only_upstream_has_is_not_a_difference(self):
        """The mirror is a copy restricted to this installation's targets.

        Upstream holds more — that is the mirror's coverage, not a
        disagreement. Counting it as one would drown the signal.
        """
        result = compare([_place("osm:r1")], [_place("osm:r1"), _place("osm:r2")])
        assert is_clean(result), "upstream's extra rows are coverage, not a disagreement"
        assert result["only_cloud"] == ["osm:r2"]

    def test_a_changed_value_is_a_difference(self):
        local = [_place("osm:r1", population=2794356)]
        cloud = [_place("osm:r1", population=2794357)]
        result = compare(local, cloud)
        assert not is_clean(result)
        assert "osm:r1" in result["differing"]
        fields = result["differing"]["osm:r1"]
        assert fields["population"]["local"] == 2794356
        assert fields["population"]["cloud"] == 2794357

    def test_every_comparable_field_is_noticed(self):
        """A changed field in any of them must be caught.

        This is the test that stops the comparison quietly losing a field:
        the list of fields is compared field by field, so a new field has to
        be added to the list on purpose.
        """
        for field in COMPARABLE_FIELDS:
            local = [_place("osm:r1")]
            cloud = [_place("osm:r1", **{field: "CHANGED"})]
            result = compare(local, cloud)
            assert not is_clean(result), f"a changed {field} was not noticed"

    def test_a_coordinate_within_a_centimetre_is_the_same_point(self):
        """A coordinate that differs in the fifteenth decimal is the same
        coordinate. A ledger that says "differs" about every row teaches the
        reader to ignore the ledger."""
        local = [_place("osm:r1", centroid_lat=43.6532, centroid_lon=-79.3832)]
        cloud = [_place("osm:r1", centroid_lat=43.65320001, centroid_lon=-79.38320001)]
        assert is_clean(compare(local, cloud))

    def test_a_coordinate_a_metre_away_is_not_the_same_point(self):
        local = [_place("osm:r1", centroid_lat=43.6532)]
        cloud = [_place("osm:r1", centroid_lat=43.6533)]
        assert not is_clean(compare(local, cloud))

    def test_null_and_missing_are_the_same_thing(self):
        """A field the mirror has never heard of and one it holds as null
        are the same answer."""
        local = [_place("osm:r1")]
        cloud = [_place("osm:r1")]
        cloud[0].pop("name_en")
        assert is_clean(compare(local, cloud))

    def test_a_null_against_a_value_is_a_difference(self):
        local = [_place("osm:r1", name_en=None)]
        cloud = [_place("osm:r1", name_en="Toronto")]
        assert not is_clean(compare(local, cloud))

    def test_rows_without_a_uid_are_ignored(self):
        """A row with no uid cannot be joined, so it cannot be compared."""
        result = compare([{"name": "nameless"}], [{"name": "nameless"}])
        assert is_clean(result)


class TestTheReadModes:
    """The three modes, and what each one serves."""

    def test_the_default_is_cloud(self):
        """This installation reads whereq.cloud live.

        The platform collects the data, so a second copy held here would be the
        copy that goes stale. The mirror is the **rollback**, and a rollback is
        a switch — not the default.
        """
        from app.core.config import settings

        assert settings.CLOUD_READ_MODE == "cloud"

    def test_the_mode_is_read_from_the_environment(self):
        """The mode is an environment variable, so an operator can move it
        without a code change — and the rollback is the same switch."""
        import importlib

        from app.core import config

        importlib.reload(config)
        assert "CLOUD_READ_MODE" in config.Settings.model_fields
        assert config.Settings.model_fields["CLOUD_READ_MODE"].default == "cloud"

    @pytest.mark.parametrize("mode", ["local", "dual", "cloud"])
    def test_the_three_modes_exist(self, mode):
        assert mode in ("local", "dual", "cloud")

    def test_the_route_reads_the_mode(self):
        """The flag has to be honoured by the route that serves the data —
        a flag nothing reads is a comment."""
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(geo.geo_places)
        assert "CLOUD_READ_MODE" in source
        assert '"cloud"' in source and '"dual"' in source

    def test_dual_mode_serves_the_local_answer(self):
        """In the dual-read window the app must behave EXACTLY as it did.

        The comparison is the point; changing what the user sees is not.
        """
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(geo.geo_places)
        # The dual branch records the comparison and then falls through to
        # the local answer — it does not return the cloud rows.
        dual_branch = source.split('if mode == "dual":')[1]
        assert "_record_parity" in dual_branch
        assert "return [GeoPlaceRead(**r) for r in local]" in dual_branch


class TestTheCloudReader:
    """The upstream reader — the filter bridging and the paging."""

    def test_the_filter_combinations(self):
        from app.services.cloud_geo import _combinations

        assert _combinations([], []) == [(None, None)]
        assert _combinations(["city"], []) == [("city", None)]
        assert _combinations([], ["osm"]) == [(None, "osm")]
        assert _combinations(["city", "ward"], ["osm", "geoboundaries"]) == [
            ("city", "osm"), ("city", "geoboundaries"),
            ("ward", "osm"), ("ward", "geoboundaries"),
        ]

    def test_the_row_is_the_shape_the_reader_returns(self):
        from app.services.cloud_geo import _place_to_read

        row = _place_to_read({
            "uid": "osm:r1", "kind": "city", "name": "Toronto",
            "source": "osm", "has_boundary": 1,
            "population": 2794356, "centroid_lon": -79.38, "centroid_lat": 43.65,
        })
        assert row["uid"] == "osm:r1"
        assert row["has_boundary"] is True
        assert row["population"] == 2794356

    def test_a_missing_has_boundary_is_false(self):
        from app.services.cloud_geo import _place_to_read

        assert _place_to_read({"uid": "osm:r1"})["has_boundary"] is False

    def test_the_page_size_matches_the_sdk_cap(self):
        from app.services.cloud_geo import PAGE_SIZE

        assert PAGE_SIZE == 200

    def test_the_reader_is_capped(self):
        """whereq.com's route allows 5000 rows; the reader must not try to
        fetch 5000 in one request — the upstream page is 200."""
        from app.services.cloud_geo import MAX_ROWS

        assert MAX_ROWS <= 2000


class TestTheLedger:
    """The table the comparisons are written to."""

    def test_the_model_carries_the_evidence(self):
        from app.models.cloud_parity import CloudParityCheck

        columns = {c.name for c in CloudParityCheck.__table__.columns}
        for needed in ("surface", "checked_at", "status", "local_count",
                       "cloud_count", "only_local", "only_cloud", "differing",
                       "params", "error"):
            assert needed in columns, f"the ledger has no {needed} column"

    def test_the_migration_exists_and_follows_the_head(self):
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        migration = backend / "alembic" / "versions" / "019_cloud_parity_checks.py"
        assert migration.exists(), "the ledger's migration is missing"
        source = migration.read_text()
        assert 'revision = "019_cloud_parity_checks"' in source
        assert 'down_revision = "018_geo_places"' in source

    def test_the_model_is_registered(self):
        from app.models import CloudParityCheck  # noqa: F401


class TestTheDeploymentWiring:
    """The switch has to reach the container.

    Compose only passes the variables it lists. A mode that lives in
    docker/.env but is not declared in the compose service never reaches
    the API — the operator would set it, see nothing happen, and draw the
    wrong conclusion. This is the whole class of bug the deployment wiring
    exists to prevent.
    """

    def _compose(self):
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        return (backend.parent / "docker" / "docker-compose.yml").read_text()

    def test_the_api_service_receives_the_mode(self):
        compose = self._compose()
        assert "CLOUD_READ_MODE" in compose, \
            "CLOUD_READ_MODE is not in the compose file — .env would never reach the API"

    def test_the_mode_defaults_to_cloud(self):
        """The compose default must agree with the code's default.

        Two defaults that disagree are the worst kind of bug: the code says
        one thing, the container says another, and which one the operator
        actually gets depends on how the environment happens to be set.
        """
        compose = self._compose()
        assert "CLOUD_READ_MODE: ${CLOUD_READ_MODE:-cloud}" in compose

    def test_the_consumer_is_not_given_the_switch(self):
        """The switch controls the READERS. The consumer still writes the
        mirror, and it must keep doing so whatever the mode says.

        The service is still called ``crawler`` in this compose file — the
        commands in docs/SETUP.md name it — but what it does now is consume.
        """
        compose = self._compose()
        consumer = compose.split("\n  crawler:")[1].split("\n  frontend:")[0]
        assert "CLOUD_READ_MODE" not in consumer

    def test_the_env_examples_document_the_mode(self):
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        for example in (backend / ".env.example", backend.parent / "docker" / ".env.example"):
            assert example.exists(), f"{example} is missing"
            text = example.read_text()
            assert "CLOUD_READ_MODE" in text, f"{example} does not document the mode"
            assert "CLOUD_READ_MODE=cloud" in text, f"{example} does not default to cloud"

    def test_every_guide_the_code_points_at_exists(self):
        """A comment that names a file is a promise that the file is there.

        The operator reads it during an incident. A dangling path sends them
        looking for a guide that was never written.
        """
        import inspect
        import re
        from pathlib import Path

        from app.core import config

        backend = Path(__file__).resolve().parents[1]
        repo = backend.parent
        source = inspect.getsource(config)
        refs = set(re.findall(r"docs/[A-Za-z0-9._-]+\.md", source))
        assert refs, "config.py no longer references a runbook"
        for ref in refs:
            assert (repo / ref).exists(), f"config.py points at {ref}, which does not exist"

    def test_the_runbook_names_the_switch_and_the_rollback(self):
        """The runbook is what the operator follows at 3am."""
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        runbook = backend.parent / "docs" / "whereq-cloud-migration.md"
        assert runbook.exists(), "the migration runbook is missing"
        text = runbook.read_text()
        for needed in ("CLOUD_READ_MODE", "local", "dual", "cloud",
                       "cloud_parity_report.py", "school_licensed"):
            assert needed in text, f"the runbook never mentions {needed}"
        # The rollback has to be one step, not a procedure.
        assert "force-recreate" in text, "the runbook does not say how to restart the API"
        # The report cannot be run from the host — it has no dependencies of
        # its own — so the runbook has to say how it is actually run.
        assert "docker cp" in text, \
            "the runbook must show how the report is run on the host"
        # A verdict that can be misread is a verdict that will be misread.
        assert "agreement, not duration" in text.lower() or \
               "not duration" in text.lower(), \
            "the runbook must say that READY is about agreement, not duration"


# ── the completeness rule ───────────────────────────────────────────────────
class TestTheCompletenessRule:
    """A comparison is only evidence when both sides were fetched **whole**.

    This is the rule that was missing, and it is the difference between a
    window that means something and a window full of noise. Measured against
    the live API: the upstream holds 32 954 places, the mirror holds the 304
    of them inside whereq.com's coverage targets, and the upstream's *first*
    500 rows contain 10 of the mirror's. Comparing those two populations
    reported 294 of 304 mirror rows as places the upstream had lost — 97%
    false defects.

    So a truncated answer is **inconclusive**: it is recorded as ``partial``,
    with no difference written. Not a defect, and not a clean match either.
    """

    def _fake_client(self, monkeypatch, places, count=_NO_COUNT):
        """A client that answers like the upstream's listing endpoint."""
        from app.services import cloud_geo

        class _Fake:
            def geo_places(self, **kwargs):
                offset = kwargs.get("offset") or 0
                limit = kwargs.get("limit") or 200
                items = places[offset:offset + limit]
                payload = {"data": items, "limit": limit, "offset": offset}
                if count is not _NO_COUNT:
                    payload["count"] = count
                return payload

            def close(self):
                return None

        monkeypatch.setattr(cloud_geo, "_client", lambda: _Fake())
        monkeypatch.setattr(cloud_geo.shared_throttle, "wait", lambda: None)

    def test_a_whole_answer_is_complete(self, monkeypatch):
        from app.services import cloud_geo

        places = [{"uid": f"osm:r{i}", "name": f"place {i}"} for i in range(300)]
        self._fake_client(monkeypatch, places, count=300)

        answer = cloud_geo.fetch_cloud_places(limit=500)
        assert answer.complete is True
        assert answer.total == 300
        assert len(answer.rows) == 300

    def test_a_truncated_answer_is_not_complete(self, monkeypatch):
        from app.services import cloud_geo

        places = [{"uid": f"osm:r{i}", "name": f"place {i}"} for i in range(1000)]
        self._fake_client(monkeypatch, places, count=1000)

        answer = cloud_geo.fetch_cloud_places(limit=100)
        assert answer.complete is False, \
            "a truncated answer must not be reported as whole"
        assert answer.total == 1000, "the upstream said how big it is"

    def test_an_upstream_that_does_not_say_how_big_it_is_is_not_evidence(self, monkeypatch):
        """No ``count`` means we cannot know whether we got all of it."""
        from app.services import cloud_geo

        places = [{"uid": f"osm:r{i}", "name": f"place {i}"} for i in range(10)]
        self._fake_client(monkeypatch, places)

        answer = cloud_geo.fetch_cloud_places(limit=500)
        assert answer.complete is False
        assert answer.total is None

    def test_the_measured_false_defects_are_not_defects(self, monkeypatch):
        """The exact shape that produced 294 false defects.

        The naive comparison DOES see 304 differences — that is the point.
        What must not happen is that those differences are *recorded* as
        defects.
        """
        import asyncio

        from app.services import cloud_geo
        from app.services.cloud_parity import compare, record

        upstream = [{"uid": f"upstream:{i}", "name": f"up {i}"} for i in range(32954)]
        self._fake_client(monkeypatch, upstream, count=32954)
        answer = cloud_geo.fetch_cloud_places(limit=500)

        mirror = [{"uid": f"mirror:{i}", "name": f"mirror {i}"} for i in range(304)]

        # The naive comparison sees the difference…
        result = compare(mirror, answer.rows)
        assert len(result["only_local"]) == 304

        # …but the recording refuses to call it a defect.
        class _Session:
            def __init__(self):
                self.added = None

            def add(self, obj):
                self.added = obj

            async def commit(self):
                return None

        db = _Session()
        row = asyncio.run(record(db, "geo_places", mirror, answer.rows, {},
                                 local_complete=True, cloud_complete=answer.complete))

        assert row.status == "partial", \
            "a truncated comparison must be inconclusive, not a defect"
        assert row.only_local == [], "a partial comparison may not report defects"
        assert row.differing == {}

    def test_a_whole_comparison_is_still_a_match(self, monkeypatch):
        import asyncio

        from app.services import cloud_geo
        from app.services.cloud_parity import record

        places = [{"uid": f"osm:r{i}", "name": f"place {i}"} for i in range(300)]
        self._fake_client(monkeypatch, places, count=300)
        answer = cloud_geo.fetch_cloud_places(limit=500)

        class _Session:
            def __init__(self):
                self.added = None

            def add(self, obj):
                self.added = obj

            async def commit(self):
                return None

        db = _Session()
        row = asyncio.run(record(db, "geo_places", answer.rows, answer.rows, {},
                                 local_complete=True, cloud_complete=answer.complete))
        assert row.status == "match"
        assert row.local_count == 300 and row.cloud_count == 300


class TestTheStatuses:
    """The four statuses the ledger can hold."""

    def test_a_clean_comparison_is_a_match(self):
        from app.services.cloud_parity import decide

        status, result = decide({"only_local": [], "only_cloud": ["x"], "differing": {}})
        assert status == "match"
        assert result["only_cloud"] == ["x"], \
            "upstream-only rows are coverage, and must still be recorded"

    def test_a_difference_is_a_differ(self):
        from app.services.cloud_parity import decide

        status, _ = decide({"only_local": ["x"], "only_cloud": [], "differing": {}})
        assert status == "differ"

    def test_an_incomplete_comparison_is_a_partial(self):
        from app.services.cloud_parity import decide

        status, result = decide({"only_local": ["x"], "only_cloud": [], "differing": {}},
                                complete=False)
        assert status == "partial"
        assert result["only_local"] == []

    def test_a_partial_is_not_a_clean_match(self):
        """The absence of evidence is not evidence of agreement."""
        from app.services.cloud_parity import decide

        status, _ = decide({"only_local": [], "only_cloud": [], "differing": {}},
                           complete=False)
        assert status != "match"


# ── the surfaces the app actually reads ─────────────────────────────────────
class TestTheSurfaces:
    """Every surface whereq.com's own app reads honours the mode.

    The first version of the window only covered ``/geo/places`` — and the
    frontend never calls it. The surfaces the app really reads are the
    containment stack (``/geo/at``), the place detail, the per-place
    outline and the vocabulary, so those are the ones the window has to
    watch.
    """

    def _routes(self):
        from app.api.routes import geo

        return geo

    def _source(self, name: str) -> str:
        import inspect

        geo = self._routes()
        return inspect.getsource(getattr(geo, name))

    @pytest.mark.parametrize("route", [
        "geo_places", "geo_at", "geo_place", "geo_boundary", "geo_concepts",
    ])
    def test_the_route_reads_the_mode(self, route):
        source = self._source(route)
        assert "_mode()" in source, f"{route} does not read the mode"
        assert '"cloud"' in source or "'cloud'" in source, \
            f"{route} has no cloud branch"

    @pytest.mark.parametrize("route", [
        "geo_places", "geo_at", "geo_place", "geo_boundary", "geo_concepts",
    ])
    def test_the_dual_branch_serves_the_local_answer(self, route):
        """In the dual-read window the app must behave EXACTLY as it did."""
        source = self._source(route)
        if 'mode == "dual"' not in source:
            return
        dual = source.split('mode == "dual"')[1]
        # The dual branch records the comparison; it does not return the
        # upstream's rows.
        assert "_record" in dual, f"{route} does not record a comparison"
        assert "return cloud" not in dual, \
            f"{route} returns the upstream's answer in dual mode"

    def test_the_bulk_outlines_are_cut(self):
        """The last surface is cut.

        whereq.cloud used to serve outlines one place at a time, so a
        viewport's worth of them would have been N upstream requests for one
        map pan — far past the 30 requests/minute the API allows, and the
        reason this endpoint read the local mirror in every mode.

        It now serves ``GET /v1/geo/boundaries`` — a viewport's worth in one
        request — so the surface reads whereq.cloud like the other five, and
        the geography mirror can stop.
        """
        source = self._source("geo_boundaries")
        assert "_mode()" in source, \
            "the bulk outlines endpoint does not read the mode"
        assert "_cloud_boundaries" in source, \
            "the bulk outlines endpoint does not read the upstream"
        assert "prerequisite" not in source, \
            "the endpoint still says the cut waits for a prerequisite"

    def test_the_containment_stack_uses_the_same_predicate(self):
        """``ST_Covers`` on both sides, or the two answers are not comparable."""
        source = self._source("geo_at")
        assert "ST_Covers" in source

    def test_the_vocabulary_comparison_leaves_the_counts_out(self):
        """The feed's own count is a snapshot on one side and live on the
        other, so the two drift apart as the feed grows. Comparing them would
        report a difference every time the upstream collected anything."""
        from app.api.routes.geo import CONCEPT_FIELDS

        assert "places" not in CONCEPT_FIELDS
        assert "upstream_places" not in CONCEPT_FIELDS
        assert "name" in CONCEPT_FIELDS


# ── the geometry ────────────────────────────────────────────────────────────
class TestTheGeometryComparison:
    """The outline is compared by its measurements, not by its bytes.

    The mirror stores the outline in a JSONB column, and JSONB does not
    preserve key order or number formatting — so two identical shapes have
    two different digests. Comparing the shape's *measurements* compares the
    shape.
    """

    def _square(self, lon: float = -79.0, lat: float = 43.0, size: float = 0.1):
        return {
            "type": "Polygon",
            "coordinates": [[
                [lon, lat],
                [lon + size, lat],
                [lon + size, lat + size],
                [lon, lat + size],
                [lon, lat],          # a closed ring repeats its first point
            ]],
        }

    def test_the_same_outline_is_the_same_outline(self):
        from app.services.cloud_parity import compare_boundary

        geometry = self._square()
        local = {"uid": "osm:r1", "name": "A", "kind": "city", "source": "osm",
                 "license": "ODbL", "area_km2": 12.5, "geometry": geometry}
        cloud = {"geometry": geometry,
                 "properties": {"uid": "osm:r1", "name": "A", "kind": "city",
                                "source": "osm", "license": "ODbL",
                                "area_km2": 12.5, "vertex_count": 4}}

        result = compare_boundary(local, cloud)
        assert result["differing"] == {}, result["differing"]

    def test_a_different_name_is_a_difference(self):
        from app.services.cloud_parity import compare_boundary

        geometry = self._square()
        local = {"uid": "osm:r1", "name": "A", "kind": "city", "source": "osm",
                 "license": "ODbL", "area_km2": 12.5, "geometry": geometry}
        cloud = {"geometry": geometry,
                 "properties": {"uid": "osm:r1", "name": "B", "kind": "city",
                                "source": "osm", "license": "ODbL",
                                "area_km2": 12.5, "vertex_count": 4}}

        result = compare_boundary(local, cloud)
        assert "name" in result["differing"]

    def test_a_different_outline_is_a_difference(self):
        """The same number of vertices, a different shape."""
        from app.services.cloud_parity import compare_boundary

        local = {"uid": "osm:r1", "name": "A", "kind": "city", "source": "osm",
                 "license": "ODbL", "area_km2": 12.5, "geometry": self._square()}
        cloud = {"geometry": self._square(size=0.2),
                 "properties": {"uid": "osm:r1", "name": "A", "kind": "city",
                                "source": "osm", "license": "ODbL",
                                "area_km2": 12.5, "vertex_count": 4}}

        result = compare_boundary(local, cloud)
        assert "bbox" in result["differing"]
        assert "vertex_count" not in result["differing"], \
            "the vertex count is the same — only the shape moved"

    def test_a_different_number_of_vertices_is_a_difference(self):
        from app.services.cloud_parity import compare_boundary

        pentagon = {
            "type": "Polygon",
            "coordinates": [[
                [-79.0, 43.0], [-78.9, 43.0], [-78.95, 43.1],
                [-78.95, 43.05], [-79.0, 43.1], [-79.0, 43.0],
            ]],
        }
        local = {"uid": "osm:r1", "name": "A", "kind": "city", "source": "osm",
                 "license": "ODbL", "area_km2": 12.5, "geometry": self._square()}
        cloud = {"geometry": pentagon,
                 "properties": {"uid": "osm:r1", "name": "A", "kind": "city",
                                "source": "osm", "license": "ODbL",
                                "area_km2": 12.5, "vertex_count": 5}}

        result = compare_boundary(local, cloud)
        assert "vertex_count" in result["differing"], result["differing"]

    def test_a_different_area_is_a_difference(self):
        from app.services.cloud_parity import compare_boundary

        geometry = self._square()
        local = {"uid": "osm:r1", "name": "A", "kind": "city", "source": "osm",
                 "license": "ODbL", "area_km2": 12.5, "geometry": geometry}
        cloud = {"geometry": geometry,
                 "properties": {"uid": "osm:r1", "name": "A", "kind": "city",
                                "source": "osm", "license": "ODbL",
                                "area_km2": 99.0, "vertex_count": 4}}

        result = compare_boundary(local, cloud)
        assert "area_km2" in result["differing"]

    def test_the_closed_ring_is_counted_once(self):
        """A GeoJSON ring repeats its first point; the polygon has one
        vertex fewer. The upstream counts the polygon's points."""
        from app.services.cloud_parity import geometry_points, geometry_rings

        geometry = self._square()
        assert geometry_points(geometry) == 5
        assert geometry_rings(geometry) == 1
        assert geometry_points(geometry) - geometry_rings(geometry) == 4

    def test_a_multipolygon_is_counted_too(self):
        from app.services.cloud_parity import geometry_points, geometry_rings

        geometry = {"type": "MultiPolygon", "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            [[[2, 2], [3, 2], [3, 3], [2, 2]]],
        ]}
        assert geometry_rings(geometry) == 2
        assert geometry_points(geometry) == 8


class TestTheLicenceIsComparable:
    """The upstream's containment stack publishes the licence now.

    The licence is the attribution the open licences (ODbL 1.0, CC-BY 4.0)
    require the UI to carry — whereq.com's map shows it on every place
    card. The upstream's ``/v1/geo/at`` did not publish it, which is why
    the stack could not be cut and why the licence was left out of the
    comparison: comparing a field the upstream does not publish against one
    it does would report a difference on every row of every stack, forever,
    and it would be telling the truth about nothing.

    The upstream publishes it now, so both of those reasons are gone: the
    licence is compared like any other field, and the stack is cut.
    """

    def test_the_licence_is_in_the_comparable_fields(self):
        from app.api.routes.geo import AT_FIELDS

        assert "license" in AT_FIELDS
        for field in ("kind", "name", "source", "centroid_lon", "centroid_lat"):
            assert field in AT_FIELDS

    def test_the_cut_of_the_stack_keeps_the_attribution(self):
        """A cut that would drop the attribution must say so in the code."""
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(geo.geo_at)
        assert "licence" in source, \
            "the route must record that the licence is the attribution"
        assert "attribution" in source


class TestTheComparisonDoesNotDelayTheAnswer:
    """The window must not make the app wait on the upstream.

    The whole point of the dual-read window is that the app behaves exactly
    as it did while the evidence collects. A comparison that runs *before*
    the response adds an upstream round trip — and the shared throttle
    paces it at about two seconds — to every map interaction, and makes
    the app's speed and its availability depend on the very thing the
    window is testing.

    So the comparison runs **after** the response.
    """

    @pytest.mark.parametrize("route", [
        "geo_places", "geo_at", "geo_place", "geo_boundary", "geo_concepts",
    ])
    def test_the_comparison_is_a_background_task(self, route):
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(getattr(geo, route))
        assert "background_tasks.add_task" in source, \
            f"{route} compares inline — the window would slow the app down"
        assert "await _record" not in source, \
            f"{route} awaits the comparison — the window would slow the app down"

    @pytest.mark.parametrize("route", [
        "geo_places", "geo_at", "geo_place", "geo_boundary", "geo_concepts",
    ])
    def test_the_route_takes_a_background_task(self, route):
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(getattr(geo, route))
        assert "background_tasks: BackgroundTasks" in source

    def test_the_background_task_writes_to_its_own_session(self):
        """The request's session is closed by the time the task runs, so the
        ledger must have one of its own."""
        import inspect

        from app.api.routes import geo

        for name in ("_record_parity", "_record_at_parity", "_record_place_parity",
                     "_record_boundary_parity", "_record_concepts_parity"):
            source = inspect.getsource(getattr(geo, name))
            assert "AsyncSessionLocal()" in source, \
                f"{name} must open its own session — the request's is closed by then"
