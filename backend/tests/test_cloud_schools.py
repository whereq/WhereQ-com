"""The school cutover — the reader, the read mode and the parity ledger.

WHAT IS BEING TESTED
---------------------
whereq.com is reading the schools from whereq.cloud instead of from its own
twelve ``school*`` tables. Three things have to hold for that to be safe:

1. **The translation is right.** The upstream's school, taxonomy and stats
   payloads are re-shaped into the shapes this app's routes already
   return. A field that is renamed or dropped in the re-shaping is a field
   the app stops showing, and the re-shaping is where that happens.

2. **The read mode is a switch, not a rewrite.** ``local`` serves this
   app's own rows, ``cloud`` serves the upstream's, and ``dual`` serves the
   local rows *and* records the comparison. The app must behave the same in
   ``local`` and in ``dual`` — that is the whole point of a window.

3. **The comparison is sound.** It only calls a difference when it can
   compare like with like. A truncated answer is inconclusive, never a
   defect.

THE KEY IS THE UID
------------------
A school is identified by its **uid** — ``ycdsb/0158`` — the board's slug
and the school's own code joined by a slash. It is the key the two systems
agree on, and it is what whereq.cloud's routes take.

The uid carries a slash, and a slash cannot be a path parameter — the
router would see two path segments and match neither route. So the routes
use a converter that is told one slash is part of the id. Without it every
lookup of every school 404s, because every uid in the database has a slash
in it.
"""

from __future__ import annotations

import pytest


# ── the upstream's payloads ────────────────────────────────────────────
def _upstream_school(**overrides) -> dict:
    row = {
        "id": 5,
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
        "programs": ["french_immersion", "pace"],
        "has_boundary": True,
        "source": "board_site",
        "source_url": "https://www.dcdsb.ca",
        "license": "Board-published facts",
        "board": {
            "slug": "dcdsb",
            "name": "Durham Catholic District School Board",
            "type": "catholic",
            "region": "Durham Region",
            "school_count": 33,
        },
        "hs_score": 8.4,
        "hs_rank": 120,
        "hs_rank_total": 2995,
        "hs_school_type": "Secondary",
    }
    row.update(overrides)
    return row


class TestTheTranslation:
    """The upstream's row, re-shaped into this app's summary."""

    def test_the_uid_is_the_identifier(self):
        from app.services.cloud_schools import school_to_summary

        summary = school_to_summary(_upstream_school())
        assert summary["uid"] == "dcdsb/austin"

    def test_the_coordinates_are_renamed(self):
        """The upstream says `latitude` and `longitude`; this app says
        `lat` and `lng`."""
        from app.services.cloud_schools import school_to_summary

        summary = school_to_summary(_upstream_school())
        assert summary["lat"] == 43.9
        assert summary["lng"] == -78.9

    def test_the_board_carries_no_integer_id(self):
        """The upstream's board has no row id, and this app's board used to
        carry one. The slug is the key both sides have."""
        from app.services.cloud_schools import school_to_summary

        summary = school_to_summary(_upstream_school())
        assert summary["board"]["slug"] == "dcdsb"
        assert "id" not in summary["board"]

    def test_a_school_without_a_board_has_no_board(self):
        from app.services.cloud_schools import school_to_summary

        summary = school_to_summary(_upstream_school(board=None))
        assert summary["board"] is None

    def test_the_region_is_the_boards(self):
        from app.services.cloud_schools import school_to_summary

        summary = school_to_summary(_upstream_school())
        assert summary["region"] == "Durham Region"

    def test_the_programmes_are_the_codes(self):
        """The codes are what the `program` filter takes, so they have to
        survive the translation."""
        from app.services.cloud_schools import school_to_summary

        summary = school_to_summary(_upstream_school())
        assert summary["programs"] == ["french_immersion", "pace"]


class TestTheDetail:
    """The detail carries the HouseSigma facts, and the EQAO marks."""

    def test_the_licensed_block_survives(self):
        from app.services.cloud_schools import school_to_detail

        detail = school_to_detail(_upstream_school(
            hs_name="Austin CSS", hs_board_type="Catholic",
            hs_score_year=2024, hs_score_average=8.4, hs_rank_year=2024))
        assert detail["hs_board_type"] == "Catholic"
        assert detail["hs_score_year"] == 2024
        assert detail["hs_rank_year"] == 2024

    def test_the_eqao_marks_are_flattened_out_of_the_scores(self):
        """The upstream nests the EQAO marks inside each year; this app's
        detail carries them as their own list."""
        from app.services.cloud_schools import school_to_detail

        detail = school_to_detail(_upstream_school(scores=[
            {"year": 2024, "rank": 12, "rank_total": 800, "rank_score": 8.1,
             "avg_exam_mark": 8.1, "eqao": [
                 {"grade": 8, "year_mark": "2021-22", "rank": 5, "total": 30,
                  "last5_avg": 8},
             ]},
        ]))
        assert len(detail["scores"]) == 1
        assert len(detail["eqao"]) == 1
        assert detail["eqao"][0]["grade"] == 8
        assert detail["eqao"][0]["year_mark"] == "2021-22"

    def test_a_school_with_no_scores_has_empty_lists(self):
        from app.services.cloud_schools import school_to_detail

        detail = school_to_detail(_upstream_school(scores=None))
        assert detail["scores"] == []
        assert detail["eqao"] == []


class TestTheTaxonomy:
    """The upstream's vocabulary, re-shaped into this app's."""

    def test_the_programmes_are_renamed(self):
        """The upstream calls them `program_categories`; this app calls them
        `programs`."""
        from app.services.cloud_schools import taxonomy_to_local

        taxonomy = taxonomy_to_local({
            "program_categories": [{"id": "pace", "name": "PACE", "count": 12}],
        })
        assert taxonomy["programs"] == [{"id": "pace", "name": "PACE", "school_count": 12}]

    def test_the_counts_are_renamed(self):
        """The upstream counts everything `count`; this app counts schools
        `school_count`."""
        from app.services.cloud_schools import taxonomy_to_local

        taxonomy = taxonomy_to_local({
            "provinces": [{"id": "ON", "name": "Ontario", "count": 1558}],
        })
        assert taxonomy["provinces"][0]["school_count"] == 1558

    def test_the_provinces_are_enabled(self):
        """This app's taxonomy has always had the flag."""
        from app.services.cloud_schools import taxonomy_to_local

        taxonomy = taxonomy_to_local({
            "provinces": [{"id": "ON", "name": "Ontario", "count": 1558}],
        })
        assert taxonomy["provinces"][0]["enabled"] is True

    def test_the_types_are_title_cased(self):
        """This app's own taxonomy title-cases the level."""
        from app.services.cloud_schools import taxonomy_to_local

        taxonomy = taxonomy_to_local({
            "types": [{"id": "elementary", "name": "elementary", "count": 900}],
        })
        assert taxonomy["types"][0]["name"] == "Elementary"

    def test_a_programme_without_a_label_falls_back_to_its_code(self):
        from app.services.cloud_schools import taxonomy_to_local

        taxonomy = taxonomy_to_local({
            "program_categories": [{"id": "pace", "name": None, "count": 1}],
        })
        assert taxonomy["programs"][0]["name"] == "pace"

    def test_the_stats_are_renamed(self):
        """The upstream says `total_schools`; this app says `total`."""
        from app.services.cloud_schools import stats_to_local

        stats = stats_to_local({"stats": {
            "total_schools": 2528, "schools_with_boundary": 2391, "boards": 9,
            "by_province": [{"id": "ON", "count": 1558}],
            "by_board_type": [{"id": "public", "count": 1169}],
            "by_type": [{"id": "secondary", "count": 1200}],
        }})
        assert stats["total"] == 2528
        assert stats["with_boundary"] == 2391
        assert stats["by_province"] == [{"id": "ON", "count": 1558}]
        assert stats["by_board_type"] == [{"id": "public", "count": 1169}]
        assert stats["by_type"] == [{"id": "secondary", "count": 1200}]


class TestTheComparison:
    """The comparison must compare like with like."""

    def test_the_programmes_are_sorted_on_both_sides(self):
        """The upstream returns them in code order; the local database
        returns them in whatever order the join produced. A comparison that
        is sensitive to the order would report a difference for every
        school with more than one programme."""
        from app.services.cloud_schools import school_to_read

        read = school_to_read(_upstream_school(programs=["pace", "french_immersion"]))
        assert read["programs"] == ["french_immersion", "pace"]

    def test_the_board_is_flattened(self):
        """A nested object compares by identity, so the board is compared
        field by field."""
        from app.services.cloud_schools import school_to_read

        read = school_to_read(_upstream_school())
        assert read["board_slug"] == "dcdsb"
        assert read["board_name"] == "Durham Catholic District School Board"
        assert read["board_type"] == "catholic"
        assert read["board_region"] == "Durham Region"

    def test_the_comparable_fields_are_the_ones_both_sides_have(self):
        from app.services.cloud_schools import COMPARABLE_FIELDS

        for field in ("name", "province", "region", "programs", "has_boundary",
                      "hs_score", "board_slug", "board_type"):
            assert field in COMPARABLE_FIELDS

    def test_a_truncated_answer_is_never_a_defect(self):
        """A comparison where one side was cut short cannot tell "upstream
        lost this school" from "the page stopped here"."""
        from app.services.cloud_parity import decide

        status, result = decide({"only_local": ["a"], "differing": {}}, complete=False)
        assert status == "partial"
        assert result["only_local"] == []

    def test_a_whole_comparison_calls_the_difference(self):
        from app.services.cloud_parity import decide

        status, result = decide({"only_local": ["a"], "differing": {}}, complete=True)
        assert status == "differ"
        assert result["only_local"] == ["a"]


class TestTheUidInThePath:
    """The uid carries a slash, and a slash cannot be a path parameter."""

    def test_the_converter_takes_at_most_one_slash(self):
        import re

        from app.api.routes.schools import _SchoolUidConvertor

        convertor = _SchoolUidConvertor()
        pattern = re.compile(f"^(?:{convertor.regex})$")
        assert pattern.match("ycdsb/0158")
        assert pattern.match("dcdsb")
        assert not pattern.match("a/b/c")
        assert not pattern.match("")

    def test_the_routes_use_the_converter(self):
        from app.api.routes.schools import router

        paths = [r.path for r in router.routes]
        assert "/schools/{school_uid:school_uid}" in paths
        assert "/schools/{school_uid:school_uid}/boundary" in paths

    def test_the_openapi_template_says_the_uid(self):
        """The converter is a routing detail. The contract — and every
        client generated from it — must still see `{school_uid}`."""
        from app.main import app

        paths = app.openapi()["paths"]
        assert "/api/schools/{school_uid}" in paths
        assert "/api/schools/{school_uid}/boundary" in paths


class TestTheReadMode:
    """`SCHOOL_READ_MODE` is the switch the cut turns."""

    def test_it_defaults_to_cloud(self):
        """The school directory is whereq.cloud's, and the catchment polygons
        are licensed data that travels with it — so the directory is read
        live."""
        from app.core.config import Settings

        assert Settings().SCHOOL_READ_MODE == "cloud"

    def test_it_is_its_own_switch(self):
        """The geography's cut and the schools' cut are separate decisions
        with separate windows, so they have separate switches."""
        from app.core.config import Settings

        settings = Settings()
        assert hasattr(settings, "SCHOOL_READ_MODE")
        assert hasattr(settings, "CLOUD_READ_MODE")

    def test_the_compose_wires_it_to_the_api_only(self):
        """The crawler must not get the switch: it writes the local tables,
        and a crawler reading from the upstream would be reading the data it
        is supposed to be producing."""
        from pathlib import Path

        compose = (Path(__file__).resolve().parents[2]
                   / "docker" / "docker-compose.yml").read_text()
        assert "SCHOOL_READ_MODE: ${SCHOOL_READ_MODE:-cloud}" in compose
        # The switch is wired once — in the api service. The crawler must
        # not get it: it writes the local tables, and a crawler reading from
        # the upstream would be reading the data it is supposed to produce.
        wiring = [line for line in compose.splitlines()
                  if "SCHOOL_READ_MODE:" in line and not line.strip().startswith("#")]
        assert len(wiring) == 1, wiring

    def test_the_env_examples_document_it(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        assert "SCHOOL_READ_MODE=cloud" in (root / "backend" / ".env.example").read_text()
        assert "SCHOOL_READ_MODE=cloud" in (root / "docker" / ".env.example").read_text()

    def test_the_route_reads_the_switch(self):
        from app.api.routes.schools import _mode

        assert _mode() in ("local", "dual", "cloud")

    def test_the_api_announces_the_mode_it_serves(self, caplog, monkeypatch):
        """A read mode that is switched on and never announced is a read mode
        nobody can check from the outside.

        The announcement lives in the API rather than in the crawler's
        banner: the switch belongs to the API, and the crawler's own guard
        is that it must not be able to read the schools at all.
        """
        import logging

        from app import main as main_module

        monkeypatch.setattr(main_module.settings, "SCHOOL_READ_MODE", "cloud")
        with caplog.at_level(logging.INFO, logger="app"):
            main_module._log_the_read_modes()
        assert any("SCHOOL_READ_MODE=cloud" in r.message for r in caplog.records), (
            "the API does not say that the school directory reads "
            "whereq.cloud live"
        )

    def test_it_says_nothing_when_the_local_copy_is_served(self, caplog, monkeypatch):
        """The announcement is for a mode that is switched ON. A banner that
        names a cut that has not happened is worse than no banner."""
        import logging

        from app import main as main_module

        monkeypatch.setattr(main_module.settings, "SCHOOL_READ_MODE", "local")
        with caplog.at_level(logging.INFO, logger="app"):
            main_module._log_the_read_modes()
        assert not any("SCHOOL_READ_MODE" in r.message for r in caplog.records), (
            "the API announced a cut that is not switched on"
        )


    def test_the_announcement_is_wired_into_the_startup(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2]
               / "backend" / "app" / "main.py").read_text()
        assert "_log_the_read_modes()" in src, (
            "the API's startup does not announce the read modes"
        )

    def test_the_api_configures_its_own_logging(self):
        """Uvicorn configures its own loggers and nothing configured the
        root logger, so an INFO from the app went nowhere — the
        announcement included. The other entry points in this repo call
        `configure_logging()`; the API did not."""
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2]
               / "backend" / "app" / "main.py").read_text()
        assert "configure_logging()" in src, (
            "the API does not configure its root logger, so its own INFO "
            "lines — the read-mode announcement included — are dropped"
        )


class TestTheCloudPath:
    """The routes in ``cloud`` mode, end to end.

    These are the tests that would have caught the bug the dual-read
    window caught first: the SDK is **synchronous**, and a route that
    awaits its result without putting the call on a thread raises
    ``'CloudSchools' object can't be awaited`` — a 500 on every school
    request.
    """

    def _stub_schools(self, **kwargs):
        from app.services.cloud_schools import CloudSchools

        return CloudSchools(
            rows=[{
                "uid": "dcdsb/austin", "name": "A School", "type": "secondary",
                "province": "ON", "region": "Durham Region", "city": "Oshawa",
                "lat": 43.9, "lng": -78.9, "hs_score": 8.4, "hs_rank": 120,
                "hs_rank_total": 2995, "grade_range": "Grades 9-13",
                "board": {"slug": "dcdsb", "name": "A Board", "type": "catholic",
                          "region": "Durham Region"},
                "programs": ["pace"], "has_boundary": True,
            }],
            total=1,
            complete=True,
        )

    def test_the_list_serves_the_upstream(self, monkeypatch):
        import asyncio

        from app.api.routes import schools as routes

        monkeypatch.setattr(routes, "_mode", lambda: "cloud")
        monkeypatch.setattr(routes, "fetch_cloud_schools", self._stub_schools)

        payload = asyncio.run(routes.list_schools(
            background_tasks=None, country=None, province=None, board=None,
            board_type=None, region=None, type=None, program=None, q=None,
            bbox=None, has_boundary=None, sort="name", order="asc", rank=False,
            page=1, page_size=2, db=None))

        assert payload.total == 1
        assert payload.items[0].uid == "dcdsb/austin"
        assert payload.items[0].region == "Durham Region"

    def test_the_detail_serves_the_upstream(self, monkeypatch):
        import asyncio

        from app.api.routes import schools as routes

        def _stub_detail(uid: str):
            return {
                "uid": uid, "name": "A School", "type": "secondary",
                "province": "ON", "region": "Durham Region", "city": "Oshawa",
                "lat": 43.9, "lng": -78.9, "hs_score": 8.4, "hs_rank": 120,
                "hs_rank_total": 2995, "grade_range": "Grades 9-13",
                "board": {"slug": "dcdsb", "name": "A Board", "type": "catholic",
                          "region": "Durham Region"},
                "programs": ["pace"], "has_boundary": True,
                "status": None, "address": "1 Main St", "municipality": "Oshawa",
                "phone": None, "phone2": None, "fax": None, "website_url": None,
                "boundary_pdf_url": None, "principal": None,
                "feeder_schools": None, "hs_name": "A School",
                "hs_board_type": "Catholic", "hs_school_type": "Secondary",
                "hs_score_year": 2024, "hs_score_average": 8.4, "hs_rank_year": 2024,
                "scores": [], "eqao": [],
            }

        monkeypatch.setattr(routes, "_mode", lambda: "cloud")
        monkeypatch.setattr(routes, "fetch_cloud_school", _stub_detail)

        detail = asyncio.run(routes.get_school(
            school_uid="dcdsb/austin", background_tasks=None, db=None, user=None))

        assert detail.uid == "dcdsb/austin"
        assert detail.hs_board_type == "Catholic"

    def test_the_taxonomy_serves_the_upstream(self, monkeypatch):
        import asyncio

        from app.api.routes import schools as routes

        def _stub_taxonomy():
            return (
                {"provinces": [{"id": "ON", "name": "Ontario", "school_count": 1558,
                                "enabled": True}],
                 "regions": [], "boards": [], "types": [], "board_types": [],
                 "programs": [{"id": "pace", "name": "PACE", "school_count": 12}]},
                {"total": 2528, "with_boundary": 2391, "by_province": [],
                 "by_board_type": [], "by_type": []},
            )

        monkeypatch.setattr(routes, "_mode", lambda: "cloud")
        monkeypatch.setattr(routes, "fetch_cloud_taxonomy", _stub_taxonomy)

        taxonomy = asyncio.run(routes.taxonomy(background_tasks=None, db=None))

        assert taxonomy.programs[0]["name"] == "PACE"
        assert taxonomy.provinces[0]["school_count"] == 1558


class TestTheSeed:
    """The local layer's missing source seed — the uid column."""

    def test_the_migration_adds_the_column(self):
        import importlib.util
        from pathlib import Path

        path = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
                / "020_school_uid.py")
        spec = importlib.util.spec_from_file_location("m020", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.revision == "020_school_uid"
        assert module.down_revision == "019_cloud_parity_checks"
        assert "uid" in module.__doc__

    def test_the_model_carries_the_column(self):
        from app.models.school import School

        assert "uid" in School.__table__.columns

    def test_the_seed_only_fills_and_never_guesses(self):
        """The seed's docstring is the contract: it fills a missing uid and
        reports what it could not match."""
        from pathlib import Path

        seed = (Path(__file__).resolve().parents[2] / "scripts"
                / "seed_school_uids.py").read_text()
        assert "never guesses" in seed
        assert "only fills" in seed
        assert "unmatched" in seed
