"""The school cutover's other surfaces — the detail, the outline, the point
in a catchment, the taxonomy and the stats.

WHAT IS BEING TESTED
---------------------
The directory list is one surface. The app also serves a school's **detail**,
its **catchment outline**, the catchments that cover a **point** and the whole
**taxonomy** — and a cut that only proves the list is not a cut that is proven.

So the questions are:

1. **The two sides are put in the same shape.** A comparison of two
   different shapes reports differences that are not differences, and a
   ledger full of those teaches its reader to ignore it. So the programmes
   are sorted on both sides, the score history is ordered on both sides, the
   board is compared as its own fields and not as a nested object, and the
   outline is compared by its measurements and not by a digest of its bytes.

2. **Each surface is compared, and written down.** Every surface records a
   row in the ledger, and a surface whose upstream answer could not be read
   records a **failure** — never a clean one.

3. **The route wires the comparison in, and only in the window.** In
   ``local`` mode nothing is compared; in ``dual`` mode the comparison runs
   **after** the response, because the window must not make the app wait on
   the upstream.
"""

from __future__ import annotations

import asyncio

import pytest


# ── the upstream's payloads ─────────────────────────────────────────────
def _upstream_detail(**overrides) -> dict:
    """The upstream's own school payload, in the upstream's own shape.

    The upstream calls its coordinates ``latitude`` and ``longitude``; this
    app calls them ``lat`` and ``lng``. The re-shaping is where that
    happens, so the comparison is made on the re-shaped rows.
    """
    detail = {
        "uid": "dcdsb/austin",
        "name": "Father Leo J. Austin Catholic Secondary School",
        "type": "secondary",
        "status": None,
        "province": "ON",
        "region": "Durham Region",
        "city": "Oshawa",
        "municipality": "Oshawa",
        "latitude": 43.9,
        "longitude": -78.9,
        "grade_range": "Grades 9-13",
        "programs": ["pace", "french_immersion"],
        "has_boundary": True,
        "hs_score": 8.4,
        "hs_rank": 120,
        "hs_rank_total": 2995,
        "hs_school_type": "Secondary",
        "board": {
            "slug": "dcdsb",
            "name": "Durham Catholic District School Board",
            "type": "catholic",
            "region": "Durham Region",
        },
        "address": "1 Main St",
        "phone": "905-000-0000",
        "phone2": None,
        "fax": None,
        "website_url": "https://www.dcdsb.ca",
        "boundary_pdf_url": None,
        "principal": "A Principal",
        "feeder_schools": {"elementary": ["dcdsb/0001"]},
        "hs_name": "Father Leo J. Austin CHS",
        "hs_board_type": "Catholic",
        "hs_score_year": 2024,
        "hs_score_average": 8.4,
        "hs_rank_year": 2024,
        "scores": [
            {"year": 2024, "rank": 120, "rank_total": 2995, "rank_score": 8.4,
             "avg_exam_mark": 78.0},
            {"year": 2023, "rank": 130, "rank_total": 3000, "rank_score": 8.2,
             "avg_exam_mark": 77.0},
        ],
        "eqao": [
            {"grade": 8, "year_mark": "2024 A", "rank": 10, "total": 40, "last5_avg": 36},
        ],
    }
    detail.update(overrides)
    return detail


def _local_detail(**overrides) -> dict:
    """The same school in this app's own detail shape — the local side."""
    from app.services.cloud_schools import school_to_detail

    detail = school_to_detail(_upstream_detail())
    detail.update(overrides)
    return detail


def _upstream_taxonomy(**overrides) -> dict:
    taxonomy = {
        "provinces": [{"id": "ON", "name": "Ontario", "count": 2528}],
        "regions": [{"id": "Durham Region", "name": "Durham Region",
                     "province": "ON", "count": 33}],
        "boards": [{"slug": "dcdsb", "name": "Durham Catholic District School Board",
                    "type": "catholic", "region": "Durham Region", "province": "ON",
                    "school_count": 33}],
        "types": [{"id": "secondary", "name": "Secondary", "count": 700}],
        "board_types": [{"id": "catholic", "name": "Catholic", "count": 900}],
        "program_categories": [{"id": "pace", "name": "French Alternative", "count": 100}],
        "stats": {
            "total_schools": 2528,
            "schools_with_boundary": 2000,
            "by_province": [{"id": "ON", "count": 2528}],
            "by_board_type": [{"id": "catholic", "count": 900}],
            "by_type": [{"id": "secondary", "count": 700}],
        },
    }
    taxonomy.update(overrides)
    return taxonomy


# ── the fake session ────────────────────────────────────────────────────
class _Result:
    """What ``db.execute`` hands back."""

    def __init__(self, rows):
        if rows is None:
            self._rows = []
        elif isinstance(rows, (list, tuple)):
            self._rows = list(rows)
        else:
            # One row, not a list of rows.
            self._rows = [rows]

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar_one(self):
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """A database session that answers with canned rows.

    The routes are called with it directly, so the tests need no database:
    the rows the route asks for are handed to it in order.
    """

    def __init__(self, results=None):
        self.results = list(results or [])
        self.executed = []

    async def execute(self, statement):
        self.executed.append(statement)
        if not self.results:
            return _Result([])
        return _Result(self.results.pop(0))

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeBackgroundTasks:
    """Captures the tasks a route adds, so a test can run them."""

    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))

    async def run(self):
        for func, args, kwargs in self.tasks:
            await func(*args, **kwargs)


@pytest.fixture
def recorded(monkeypatch):
    """Capture what the ledger is told, instead of writing it."""
    from app.services import cloud_parity

    calls: list[dict] = []

    async def _record(db, surface, local_rows, cloud_rows, params=None, **kwargs):
        calls.append({
            "surface": surface,
            "local": list(local_rows),
            "cloud": list(cloud_rows),
            "params": params or {},
            **kwargs,
        })
        return object()

    async def _record_error(db, surface, error, params=None):
        calls.append({"surface": surface, "error": error, "params": params or {}})
        return object()

    async def _record_result(db, surface, result, *, local_count, cloud_count,
                             params=None, complete=True):
        calls.append({
            "surface": surface,
            "result": result,
            "local_count": local_count,
            "cloud_count": cloud_count,
            "params": params or {},
            "complete": complete,
        })
        return object()

    monkeypatch.setattr(cloud_parity, "record", _record)
    monkeypatch.setattr(cloud_parity, "record_error", _record_error)
    monkeypatch.setattr(cloud_parity, "record_result", _record_result)
    return calls


@pytest.fixture
def fake_db(monkeypatch):
    """The ledger's own session — it must never touch a real database."""
    import app.core.database as database

    session = _FakeSession()

    def _session_local():
        return session

    monkeypatch.setattr(database, "AsyncSessionLocal", _session_local)
    return session


# ── the shapes ───────────────────────────────────────────────────────────
class TestTheShapes:
    """The two sides must be in the same shape before they are compared."""

    def test_the_programmes_are_sorted_on_both_sides(self):
        from app.services.cloud_school_parity import detail_to_read

        one = detail_to_read(_local_detail(programs=["pace", "french_immersion"]))
        two = detail_to_read(_upstream_detail(programs=["french_immersion", "pace"]))

        assert one["programs"] == ["french_immersion", "pace"]
        assert one["programs"] == two["programs"]

    def test_the_score_history_is_ordered_on_both_sides(self):
        from app.services.cloud_school_parity import detail_to_read

        forward = detail_to_read(_local_detail())
        backward = detail_to_read(_upstream_detail(
            scores=list(reversed(_upstream_detail()["scores"]))))

        assert [s["year"] for s in forward["scores"]] == [2023, 2024]
        assert forward["scores"] == backward["scores"]

    def test_the_eqao_marks_are_ordered_on_both_sides(self):
        from app.services.cloud_school_parity import detail_to_read

        one = detail_to_read(_local_detail(eqao=[
            {"grade": 8, "year_mark": "2024 A", "rank": 10, "total": 40, "last5_avg": 36},
            {"grade": 6, "year_mark": "2024 A", "rank": 5, "total": 40, "last5_avg": 34},
        ]))
        two = detail_to_read(_upstream_detail(eqao=[
            {"grade": 6, "year_mark": "2024 A", "rank": 5, "total": 40, "last5_avg": 34},
            {"grade": 8, "year_mark": "2024 A", "rank": 10, "total": 40, "last5_avg": 36},
        ]))

        assert [m["grade"] for m in one["eqao"]] == [6, 8]
        assert one["eqao"] == two["eqao"]

    def test_the_board_is_compared_as_its_own_fields(self):
        from app.services.cloud_school_parity import detail_to_read

        detail = detail_to_read(_local_detail())

        assert detail["board"] == {
            "slug": "dcdsb", "name": "Durham Catholic District School Board",
            "type": "catholic", "region": "Durham Region",
        }

    def test_a_nested_block_is_compared_by_its_content(self):
        from app.services.cloud_parity import same

        # The same document, written with the keys in another order.
        assert same("feeder_schools", {"a": 1, "b": 2}, {"b": 2, "a": 1})
        assert not same("feeder_schools", {"a": 1, "b": 2}, {"a": 1, "b": 3})

    def test_a_missing_school_is_not_a_shape(self):
        from app.services.cloud_school_parity import detail_to_read

        assert detail_to_read(None) is None


class TestTheOutline:
    """The outline is compared by what it is, not by what its bytes are."""

    def _outline(self, **overrides):
        outline = {
            "uid": "dcdsb/austin",
            "name": "A School",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            },
            "polygon_count": 1,
            "point_count": 4,
        }
        outline.update(overrides)
        return outline

    def test_the_vertices_come_off_the_geometry(self):
        from app.services.cloud_school_parity import boundary_to_read

        read = boundary_to_read(self._outline())

        # Four positions, one ring — a closed ring repeats its first point,
        # so the shape has three vertices.
        assert read["vertex_count"] == 3

    def test_the_extent_comes_off_the_geometry(self):
        from app.services.cloud_school_parity import boundary_to_read

        read = boundary_to_read(self._outline())

        assert read["bbox"] == [0.0, 0.0, 1.0, 1.0]

    def test_two_copies_of_the_same_shape_agree(self):
        from app.services.cloud_school_parity import boundary_to_read

        one = boundary_to_read(self._outline())
        two = boundary_to_read(self._outline())

        assert one == two

    def test_a_different_shape_is_a_difference(self):
        from app.services.cloud_school_parity import boundary_to_read

        one = boundary_to_read(self._outline())
        two = boundary_to_read(self._outline(geometry={
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [2, 0], [1, 1], [0.5, 0.5], [0, 0]]]]},
            point_count=5))

        assert one["vertex_count"] != two["vertex_count"]
        assert one["bbox"] != two["bbox"]

    def test_the_uid_is_carried(self):
        from app.services.cloud_school_parity import boundary_to_read

        assert boundary_to_read(self._outline(), uid="dcdsb/austin")["uid"] == "dcdsb/austin"


class TestThePointInACatchment:
    """A catchment can be several polygons, so the key carries the index."""

    def test_the_key_carries_the_polygon(self):
        from app.services.cloud_school_parity import at_to_read

        hit = at_to_read({"uid": "dcdsb/austin", "name": "A School", "type": "secondary",
                           "board": "A Board", "polygon_index": 1})

        assert hit["uid"] == "dcdsb/austin#1"

    def test_two_polygons_are_two_shapes(self):
        from app.services.cloud_school_parity import at_to_read

        one = at_to_read({"uid": "dcdsb/austin", "polygon_index": 0})
        two = at_to_read({"uid": "dcdsb/austin", "polygon_index": 1})

        assert one["uid"] != two["uid"]

    def test_a_missing_index_is_the_first_polygon(self):
        from app.services.cloud_school_parity import at_to_read

        assert at_to_read({"uid": "dcdsb/austin"})["uid"] == "dcdsb/austin#0"


class TestTheTaxonomy:
    """The vocabulary is compared group by group."""

    def _local(self, **overrides):
        taxonomy = {
            "provinces": [{"id": "ON", "name": "Ontario", "school_count": 2528, "enabled": True}],
            "regions": [{"id": "Durham Region", "name": "Durham Region",
                         "province": "ON", "school_count": 33}],
            "boards": [{"slug": "dcdsb", "name": "Durham Catholic District School Board",
                        "type": "catholic", "region": "Durham Region", "province": "ON",
                        "school_count": 33}],
            "types": [{"id": "secondary", "name": "Secondary", "school_count": 700}],
            "board_types": [{"id": "catholic", "name": "Catholic", "school_count": 900}],
            "programs": [{"id": "pace", "name": "French Alternative", "school_count": 100}],
        }
        taxonomy.update(overrides)
        return taxonomy

    def test_two_identical_taxonomies_agree(self):
        from app.services.cloud_school_parity import compare_taxonomies
        from app.services.cloud_schools import taxonomy_to_local

        cloud = taxonomy_to_local(_upstream_taxonomy())

        result = compare_taxonomies(self._local(), cloud)

        assert result["differing"] == {}

    def test_a_wrong_count_is_a_difference(self):
        from app.services.cloud_school_parity import compare_taxonomies
        from app.services.cloud_schools import taxonomy_to_local

        cloud = taxonomy_to_local(_upstream_taxonomy())
        local = self._local()
        local["provinces"][0]["school_count"] = 2500

        result = compare_taxonomies(local, cloud)

        assert "provinces" in result["differing"]
        assert result["differing"]["provinces"]["ON"]["school_count"] == {
            "local": 2500, "cloud": 2528,
        }

    def test_a_missing_row_is_a_difference(self):
        from app.services.cloud_school_parity import compare_taxonomies
        from app.services.cloud_schools import taxonomy_to_local

        cloud = taxonomy_to_local(_upstream_taxonomy())
        local = self._local()
        local["types"] = []

        result = compare_taxonomies(local, cloud)

        assert result["differing"]["types"]["only_cloud"] == ["secondary"]

    def test_the_boards_are_keyed_by_their_slug(self):
        from app.services.cloud_school_parity import compare_taxonomies
        from app.services.cloud_schools import taxonomy_to_local

        cloud = taxonomy_to_local(_upstream_taxonomy())
        local = self._local()
        local["boards"][0]["slug"] = "dcdsb-old"

        result = compare_taxonomies(local, cloud)

        entry = result["differing"]["boards"]
        assert entry["only_local"] == ["dcdsb-old"]
        assert entry["only_cloud"] == ["dcdsb"]


class TestTheStats:
    """The headline numbers are compared too."""

    def _local(self, **overrides):
        stats = {
            "total": 2528,
            "with_boundary": 2000,
            "by_province": [{"id": "ON", "count": 2528}],
            "by_board_type": [{"id": "catholic", "count": 900}],
            "by_type": [{"id": "secondary", "count": 700}],
        }
        stats.update(overrides)
        return stats

    def test_two_identical_stats_agree(self):
        from app.services.cloud_school_parity import compare_stats
        from app.services.cloud_schools import stats_to_local

        result = compare_stats(self._local(), stats_to_local(_upstream_taxonomy()))

        assert result["differing"] == {}

    def test_a_wrong_total_is_a_difference(self):
        from app.services.cloud_school_parity import compare_stats
        from app.services.cloud_schools import stats_to_local

        result = compare_stats(self._local(total=2500), stats_to_local(_upstream_taxonomy()))

        assert result["differing"]["counts"]["total"] == {"local": 2500, "cloud": 2528}

    def test_a_wrong_breakdown_is_a_difference(self):
        from app.services.cloud_school_parity import compare_stats
        from app.services.cloud_schools import stats_to_local

        local = self._local()
        local["by_province"][0]["count"] = 2000

        result = compare_stats(local, stats_to_local(_upstream_taxonomy()))

        assert result["differing"]["by_province"]["ON"]["count"] == {
            "local": 2000, "cloud": 2528,
        }


# ── the surfaces ────────────────────────────────────────────────────────
class TestTheDetailSurface:
    """One school's detail, compared with the upstream's."""

    def test_a_matching_detail_is_written_down_as_a_match(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        from app.services.cloud_schools import school_to_detail

        monkeypatch.setattr(routes, "_mode", lambda: "dual")
        monkeypatch.setattr(routes, "fetch_cloud_school",
                            lambda uid: school_to_detail(_upstream_detail()))

        asyncio.run(routes._record_detail_parity("dcdsb/austin", _local_detail()))

        assert len(recorded) == 1
        assert recorded[0]["surface"] == "school_detail"
        assert recorded[0]["local"][0]["name"] == recorded[0]["cloud"][0]["name"]

    def test_a_different_name_is_a_difference(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes
        from app.services.cloud_schools import school_to_detail

        monkeypatch.setattr(routes, "fetch_cloud_school",
                            lambda uid: school_to_detail(
                                _upstream_detail(name="A Different Name")))

        asyncio.run(routes._record_detail_parity("dcdsb/austin", _local_detail()))

        assert recorded[0]["cloud"][0]["name"] == "A Different Name"

    def test_an_upstream_failure_is_recorded_as_a_failure(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        def _boom(uid):
            raise RuntimeError("the upstream is down")

        monkeypatch.setattr(routes, "fetch_cloud_school", _boom)

        asyncio.run(routes._record_detail_parity("dcdsb/austin", _local_detail()))

        assert recorded[0]["surface"] == "school_detail"
        assert "error" in recorded[0]

    def test_a_school_the_upstream_does_not_have_is_a_difference(
            self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "fetch_cloud_school", lambda uid: None)

        asyncio.run(routes._record_detail_parity("dcdsb/austin", _local_detail()))

        # The local copy holds it and the upstream does not: the upstream
        # answered, and its answer was "no".
        assert recorded[0]["cloud"] == []
        assert recorded[0]["cloud_complete"] is True


class TestTheOutlineSurface:
    """One school's catchment outline, compared with the upstream's."""

    def _outline(self):
        return {
            "uid": "dcdsb/austin",
            "name": "A School",
            "geometry": {"type": "MultiPolygon",
                         "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]},
            "polygon_count": 1,
            "point_count": 4,
        }

    def test_a_matching_outline_is_written_down(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "fetch_cloud_school_boundary", lambda uid: self._outline())

        asyncio.run(routes._record_boundary_parity("dcdsb/austin", self._outline()))

        assert recorded[0]["surface"] == "school_boundary"
        assert recorded[0]["local"][0]["bbox"] == recorded[0]["cloud"][0]["bbox"]

    def test_a_different_shape_is_a_difference(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        other = dict(self._outline(), point_count=5, geometry={
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0.5, 0.5], [0, 0]]]]})
        monkeypatch.setattr(routes, "fetch_cloud_school_boundary", lambda uid: other)

        asyncio.run(routes._record_boundary_parity("dcdsb/austin", self._outline()))

        assert recorded[0]["cloud"][0]["vertex_count"] == 4
        assert recorded[0]["local"][0]["vertex_count"] == 3

    def test_an_upstream_failure_is_recorded_as_a_failure(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        def _boom(uid):
            raise RuntimeError("the upstream is down")

        monkeypatch.setattr(routes, "fetch_cloud_school_boundary", _boom)

        asyncio.run(routes._record_boundary_parity("dcdsb/austin", self._outline()))

        assert "error" in recorded[0]


class TestThePointInACatchmentSurface:
    """The catchments covering a point, compared with the upstream's."""

    def test_the_same_catchments_agree(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        hits = [{"uid": "dcdsb/austin", "name": "A School", "type": "secondary",
                 "board": "A Board", "polygon_index": 0}]
        monkeypatch.setattr(routes, "fetch_cloud_schools_at",
                            lambda lat, lng: hits)

        asyncio.run(routes._record_at_parity(43.9, -78.9, hits))

        assert recorded[0]["surface"] == "school_at"
        assert recorded[0]["local"][0]["uid"] == "dcdsb/austin#0"

    def test_an_upstream_failure_is_recorded_as_a_failure(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        def _boom(lat, lng):
            raise RuntimeError("the upstream is down")

        monkeypatch.setattr(routes, "fetch_cloud_schools_at", _boom)

        asyncio.run(routes._record_at_parity(43.9, -78.9, []))

        assert "error" in recorded[0]


class TestTheTaxonomySurface:
    """The whole vocabulary, compared with the upstream's."""

    def _local(self):
        from app.services.cloud_schools import taxonomy_to_local

        return taxonomy_to_local(_upstream_taxonomy())

    def test_a_matching_taxonomy_is_written_down(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "fetch_cloud_taxonomy",
                            lambda: (self._local(), {"total": 2528}))

        asyncio.run(routes._record_taxonomy_parity(self._local()))

        assert recorded[0]["surface"] == "school_taxonomy"
        assert recorded[0]["result"]["differing"] == {}

    def test_an_upstream_failure_is_recorded_as_a_failure(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes

        def _boom():
            raise RuntimeError("the upstream is down")

        monkeypatch.setattr(routes, "fetch_cloud_taxonomy", _boom)

        asyncio.run(routes._record_taxonomy_parity(self._local()))

        assert "error" in recorded[0]


class TestTheStatsSurface:
    """The headline counts, compared with the upstream's."""

    def test_matching_stats_are_written_down(self, monkeypatch, recorded, fake_db):
        from app.api.routes import schools as routes
        from app.services.cloud_schools import stats_to_local

        cloud = stats_to_local(_upstream_taxonomy())
        monkeypatch.setattr(routes, "fetch_cloud_taxonomy", lambda: ({}, cloud))

        asyncio.run(routes._record_stats_parity({
            "total": 2528, "with_boundary": 2000,
            "by_province": [{"id": "ON", "count": 2528}],
            "by_board_type": [{"id": "catholic", "count": 900}],
            "by_type": [{"id": "secondary", "count": 700}],
        }))

        assert recorded[0]["surface"] == "school_stats"
        assert recorded[0]["result"]["differing"] == {}


# ── the wiring ──────────────────────────────────────────────────────────
class TestTheWiring:
    """Each surface compares itself — in the window, and only in it."""

    def _school(self):
        from app.models.school import Province, School, SchoolBoard

        school = School(
            id=5, uid="dcdsb/austin", name="A School", type="secondary",
            status=None, province_id=1, board_id=1, city="Oshawa",
            municipality="Oshawa", lat=43.9, lng=-78.9, grade_range="Grades 9-13",
            address="1 Main St", hs_score=8.4, hs_rank=120, hs_rank_total=2995,
            principal="A Principal", hs_score_year=2024, hs_score_average=8.4,
            hs_rank_year=2024, feeder_schools=None,
        )
        school.board = SchoolBoard(
            id=1, slug="dcdsb", name="A Board", type="catholic",
            region="Durham Region", province_id=1)
        school.province = Province(id=1, code="ON", name="Ontario", country_id=1)
        school.scores = []
        school.eqao = []
        school.boundaries = []
        return school

    def test_the_detail_compares_itself_in_the_window(self, monkeypatch):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "_mode", lambda: "dual")
        tasks = _FakeBackgroundTasks()

        asyncio.run(routes.get_school(
            school_uid="dcdsb/austin", background_tasks=tasks,
            db=_FakeSession([self._school()]), user=None))

        assert len(tasks.tasks) == 1
        assert tasks.tasks[0][0] is routes._record_detail_parity

    def test_the_detail_does_not_compare_outside_the_window(self, monkeypatch):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "_mode", lambda: "local")
        tasks = _FakeBackgroundTasks()

        asyncio.run(routes.get_school(
            school_uid="dcdsb/austin", background_tasks=tasks,
            db=_FakeSession([self._school()]), user=None))

        assert tasks.tasks == []

    def test_the_outline_compares_itself_in_the_window(self, monkeypatch):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "_mode", lambda: "dual")
        tasks = _FakeBackgroundTasks()

        asyncio.run(routes.school_boundary(
            school_uid="dcdsb/austin", background_tasks=tasks,
            db=_FakeSession([
                ["A School"], [5],
                [{"coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}],
            ]), _user=None))

        assert len(tasks.tasks) == 1
        assert tasks.tasks[0][0] is routes._record_boundary_parity

    def test_the_point_in_a_catchment_compares_itself_in_the_window(self, monkeypatch):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "_mode", lambda: "dual")
        tasks = _FakeBackgroundTasks()

        asyncio.run(routes.schools_at_point(
            background_tasks=tasks, lat=43.9, lng=-78.9,
            db=_FakeSession([[("dcdsb/austin", "A School", "secondary", "A Board", 0)]]),
            _user=None))

        assert len(tasks.tasks) == 1
        assert tasks.tasks[0][0] is routes._record_at_parity

    def test_the_taxonomy_compares_itself_in_the_window(self, monkeypatch):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "_mode", lambda: "dual")
        monkeypatch.setattr(routes, "_local_taxonomy_rows",
                            _FakeSession and (lambda db: _async_rows()))
        tasks = _FakeBackgroundTasks()

        asyncio.run(routes.taxonomy(background_tasks=tasks, db=_FakeSession()))

        assert len(tasks.tasks) == 1
        assert tasks.tasks[0][0] is routes._record_taxonomy_parity

    def test_the_stats_compare_themselves_in_the_window(self, monkeypatch):
        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "_mode", lambda: "dual")
        tasks = _FakeBackgroundTasks()

        rows = [[2528], [2000], [("ON", 2528)], [("catholic", 900)], [("secondary", 700)]]
        asyncio.run(routes.stats(background_tasks=tasks, db=_FakeSession(rows)))

        assert len(tasks.tasks) == 1
        assert tasks.tasks[0][0] is routes._record_stats_parity


async def _async_rows():
    return {"provinces": [], "regions": [], "boards": [], "types": [],
            "board_types": [], "programs": []}


# ── the report ──────────────────────────────────────────────────────────
def _load_report():
    """The parity report script, as a module."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "cloud_parity_report.py"
    spec = importlib.util.spec_from_file_location("cloud_parity_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheReport:
    """The two windows are separate decisions, so they are judged apart.

    The report reads one ledger, and the ledger now holds both windows'
    comparisons. A verdict that mixed them would say "NOT READY" for a cut
    that is not the one being considered.
    """

    def test_the_two_windows_are_separate(self):
        report = _load_report()

        assert set(report.WINDOWS) == {"geo", "schools"}

    def test_the_school_window_holds_every_school_surface(self):
        report = _load_report()

        assert set(report.WINDOWS["schools"]) == {
            "school_list", "school_detail", "school_boundary",
            "school_at", "school_taxonomy", "school_stats",
        }

    def test_the_geo_window_does_not_hold_a_school_surface(self):
        report = _load_report()

        assert not any(s.startswith("school_") for s in report.WINDOWS["geo"])

    def test_the_two_flags_cannot_be_given_together(self):
        import subprocess
        import sys
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "scripts" / "cloud_parity_report.py"
        result = subprocess.run(
            [sys.executable, str(path), "--surface", "school_list", "--window", "schools"],
            capture_output=True, text=True,
        )

        assert result.returncode == 2
        assert "cannot both be given" in result.stderr


class _FakeRow:
    """One ledger row, as the report sees it."""

    def __init__(self, surface, status, minutes, local=1, cloud=1):
        from datetime import datetime, timedelta, timezone

        self.surface = surface
        self.status = status
        self.checked_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        self.local_count = local
        self.cloud_count = cloud
        self.error = "boom" if status == "error" else None
        self.only_local = []
        self.only_cloud = []
        self.differing = {}


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeLedgerSession:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement):
        return _FakeResult(self.rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestTheVerdict:
    """The verdict is about the present; the history is kept beside it.

    A bug that was fixed an hour ago must not veto the cut forever, or no
    window would ever pass — and the ledger's whole point is that it is
    never cleaned up.
    """

    def _run(self, rows, monkeypatch, capsys):
        import asyncio

        report = _load_report()
        monkeypatch.setattr(report, "AsyncSessionLocal",
                            lambda: _FakeLedgerSession(rows))
        code = asyncio.run(report.summarise(days=7, surface=None, verbose=False,
                                             window="schools"))
        return code, capsys.readouterr().out

    def test_a_clean_window_is_ready(self, monkeypatch, capsys):
        rows = [_FakeRow("school_list", "match", 5),
                _FakeRow("school_detail", "match", 4)]

        code, out = self._run(rows, monkeypatch, capsys)

        assert code == 0
        assert "READY" in out

    def test_a_fixed_error_does_not_veto_the_verdict(self, monkeypatch, capsys):
        rows = [_FakeRow("school_list", "error", 60),
                _FakeRow("school_list", "match", 5)]

        code, out = self._run(rows, monkeypatch, capsys)

        assert code == 0
        assert "READY" in out
        # The history is still reported — nothing is hidden.
        assert "1 error" in out

    def test_a_live_difference_vetoes_the_verdict(self, monkeypatch, capsys):
        rows = [_FakeRow("school_list", "match", 60),
                _FakeRow("school_list", "differ", 5)]

        code, out = self._run(rows, monkeypatch, capsys)

        assert code == 1
        assert "NOT READY" in out
        assert "disagree" in out

    def test_a_live_error_vetoes_the_verdict(self, monkeypatch, capsys):
        rows = [_FakeRow("school_list", "match", 60),
                _FakeRow("school_list", "error", 5)]

        code, out = self._run(rows, monkeypatch, capsys)

        assert code == 1
        assert "could not be made" in out

    def test_a_live_partial_is_not_a_check(self, monkeypatch, capsys):
        rows = [_FakeRow("school_list", "match", 60),
                _FakeRow("school_list", "partial", 5)]

        code, out = self._run(rows, monkeypatch, capsys)

        assert code == 1
        assert "no clean comparison yet" in out

    def test_a_window_with_nothing_in_it_is_not_ready(self, monkeypatch, capsys):
        code, out = self._run([], monkeypatch, capsys)

        assert code == 1
        assert "no comparisons recorded" in out
