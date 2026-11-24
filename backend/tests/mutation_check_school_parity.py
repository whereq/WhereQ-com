#!/usr/bin/env python3
"""Mutation check for the school parity surfaces.

Each mutation breaks one thing the code is supposed to do. Each test must
**fail** when its bug is back. A test that passes with its bug reintroduced
is a test that proves nothing.

**This edits the working tree.** Every file it touches is written back
exactly as it was, whether the mutation was caught or not — but run it on a
clean tree, and never on production.
"""
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARITY = ROOT / "backend/app/services/cloud_school_parity.py"
LEDGER = ROOT / "backend/app/services/cloud_parity.py"
ROUTES = ROOT / "backend/app/api/routes/schools.py"

MUTATIONS = [
    ("the programmes are not sorted", PARITY,
     '        return sorted(value)\n',
     '        return value\n',
     ["test_cloud_school_parity.py::TestTheShapes::test_the_programmes_are_sorted_on_both_sides"]),

    ("the score history is not ordered", PARITY,
     '    return sorted(\n        (dict(row) for row in value),\n        key=lambda row: (row.get("year") is None, row.get("year")),\n    )',
     '    return [dict(row) for row in value]',
     ["test_cloud_school_parity.py::TestTheShapes::test_the_score_history_is_ordered_on_both_sides"]),

    ("the board is not flattened", PARITY,
     '    return {key: value.get(key) for key in ("slug", "name", "type", "region")}',
     '    return value',
     ["test_cloud_school_parity.py::TestTheShapes::test_the_board_is_compared_as_its_own_fields"]),

    ("a nested block is compared as text", LEDGER,
     '    if isinstance(left, (dict, list, tuple)) or isinstance(right, (dict, list, tuple)):\n        return _canonical(left) == _canonical(right)\n',
     '',
     ["test_cloud_school_parity.py::TestTheShapes::test_a_nested_block_is_compared_by_its_content"]),

    ("the polygon index is not in the key", PARITY,
     '        "uid": f"{hit.get(\'uid\')}#{hit.get(\'polygon_index\') or 0}",',
     '        "uid": hit.get("uid"),',
     ["test_cloud_school_parity.py::TestThePointInACatchment::test_the_key_carries_the_polygon",
      "test_cloud_school_parity.py::TestThePointInACatchment::test_two_polygons_are_two_shapes"]),

    ("the vertex count is not off the rings", PARITY,
     '        "vertex_count": geometry_points(geometry) - geometry_rings(geometry),',
     '        "vertex_count": geometry_points(geometry),',
     ["test_cloud_school_parity.py::TestTheOutline::test_the_vertices_come_off_the_geometry"]),

    ("the taxonomy counts are not compared", PARITY,
     '    return _grouped_difference(\n        local or {}, cloud or {}, TAXONOMY_GROUPS, TAXONOMY_KEY, TAXONOMY_FIELDS,\n    )',
     '    return {"only_local": [], "only_cloud": [], "differing": {}}',
     ["test_cloud_school_parity.py::TestTheTaxonomy::test_a_wrong_count_is_a_difference",
      "test_cloud_school_parity.py::TestTheTaxonomy::test_a_missing_row_is_a_difference"]),

    ("the taxonomy's own rows are not compared", PARITY,
     '    entry: dict[str, Any] = {}\n        only_local = sorted(set(left) - set(right))',
     '    entry: dict[str, Any] = {}\n        only_local = []',
     ["test_cloud_school_parity.py::TestTheTaxonomy::test_a_missing_row_is_a_difference",
      "test_cloud_school_parity.py::TestTheTaxonomy::test_the_boards_are_keyed_by_their_slug"]),

    ("the stats' totals are not compared", PARITY,
     '    for field in STATS_SCALARS:\n        if not same(field, local.get(field), cloud.get(field)):\n            scalars[field] = {"local": local.get(field), "cloud": cloud.get(field)}',
     '    pass',
     ["test_cloud_school_parity.py::TestTheStats::test_a_wrong_total_is_a_difference"]),

    ("the stats' breakdowns are not compared", PARITY,
     '    result = _grouped_difference(\n        local, cloud, STATS_GROUPS, {}, {g: STATS_FIELDS for g in STATS_GROUPS},\n    )',
     '    result = {"only_local": [], "only_cloud": [], "differing": {}}',
     ["test_cloud_school_parity.py::TestTheStats::test_a_wrong_breakdown_is_a_difference"]),

    ("the detail surface does not compare itself", ROUTES,
     '    if mode == "dual":\n        # The principal is compared too: both copies carry it, and a cut that\n        # dropped it would be a cut the ledger would not have noticed.\n        background_tasks.add_task(\n            _record_detail_parity, school_uid,\n            {**detail.model_dump(), "principal": s.principal},\n        )',
     '    if False:\n        pass',
     ["test_cloud_school_parity.py::TestTheWiring::test_the_detail_compares_itself_in_the_window"]),

    ("the detail surface compares itself outside the window", ROUTES,
     '    if mode == "dual":\n        # The principal is compared too: both copies carry it, and a cut that\n        # dropped it would be a cut the ledger would not have noticed.\n        background_tasks.add_task(\n            _record_detail_parity, school_uid,\n            {**detail.model_dump(), "principal": s.principal},\n        )',
     '    if True:\n        background_tasks.add_task(\n            _record_detail_parity, school_uid,\n            {**detail.model_dump(), "principal": s.principal},\n        )',
     ["test_cloud_school_parity.py::TestTheWiring::test_the_detail_does_not_compare_outside_the_window"]),

    ("the outline surface does not compare itself", ROUTES,
     '    if mode == "dual":\n        background_tasks.add_task(\n            _record_boundary_parity, school_uid,\n            {"uid": school_uid, "name": row, "geometry": geometry,\n             "polygon_count": len(polys), "point_count": points},\n        )',
     '    if False:\n        pass',
     ["test_cloud_school_parity.py::TestTheWiring::test_the_outline_compares_itself_in_the_window"]),

    ("the point-in-a-catchment surface does not compare itself", ROUTES,
     '    if mode == "dual":\n        background_tasks.add_task(\n            _record_at_parity, lat, lng,\n            [{"uid": h.uid, "name": h.name, "type": h.type, "board": h.board,\n              "polygon_index": h.polygon_index} for h in hits],\n        )',
     '    if False:\n        pass',
     ["test_cloud_school_parity.py::TestTheWiring::test_the_point_in_a_catchment_compares_itself_in_the_window"]),

    ("the taxonomy surface does not compare itself", ROUTES,
     '    if mode == "dual":\n        background_tasks.add_task(_record_taxonomy_parity, rows)',
     '    if False:\n        pass',
     ["test_cloud_school_parity.py::TestTheWiring::test_the_taxonomy_compares_itself_in_the_window"]),

    ("the stats surface does not compare itself", ROUTES,
     '    if mode == "dual":\n        background_tasks.add_task(_record_stats_parity, local)',
     '    if False:\n        pass',
     ["test_cloud_school_parity.py::TestTheWiring::test_the_stats_compare_themselves_in_the_window"]),

    ("a failed comparison is not written down", ROUTES,
     '        logger.warning("cloud parity: school_detail %s could not be compared — %s", uid, exc)\n        async with AsyncSessionLocal() as db:\n            await cloud_parity.record_error(db, "school_detail", str(exc), params={"uid": uid})\n        return',
     '        logger.warning("cloud parity: school_detail %s could not be compared — %s", uid, exc)\n        return',
     ["test_cloud_school_parity.py::TestTheDetailSurface::test_an_upstream_failure_is_recorded_as_a_failure"]),

    ("a school the upstream lost is not a difference", ROUTES,
     '            cloud_complete=True,\n            fields=DETAIL_FIELDS,',
     '            cloud_complete=False,\n            fields=DETAIL_FIELDS,',
     ["test_cloud_school_parity.py::TestTheDetailSurface::test_a_school_the_upstream_does_not_have_is_a_difference"]),
]


def run(tests):
    return subprocess.run(
        [".venv/bin/python", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *tests],
        cwd=ROOT / "backend", capture_output=True, text=True,
    )


def main():
    survived = []
    for name, path, old, new, tests in MUTATIONS:
        original = path.read_text()
        if old not in original:
            print(f"SKIP  {name}: the pattern is not in {path.name}")
            survived.append((name, "pattern not found"))
            continue
        try:
            path.write_text(original.replace(old, new, 1))
            result = run(tests)
        finally:
            path.write_text(original)
        caught = result.returncode != 0
        print(f"{'CAUGHT' if caught else 'SURVIVED'}  {name}")
        if not caught:
            survived.append((name, "the test still passed"))
            print(result.stdout[-1500:])

    print()
    if survived:
        print(f"{len(survived)} mutation(s) survived:")
        for name, why in survived:
            print(f"  - {name} ({why})")
        return 1
    print(f"all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
