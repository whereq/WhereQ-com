"""The maintenance tool that rebuilds the bloated spatial indexes.

The decision rule is the whole point of the tool, so it is a **pure
function** and is tested as one: an index is rebuilt when it has grown past
a multiple of **a fresh build of itself**. Not by its share of free space —
a freshly built geography index on ``local_content`` is 89.52 % free while a
bloated plain index on ``places`` sat at 85.52 % — and not by its tuple
count, because GiST only marks an entry dead once a VACUUM has visited the
index.

These tests need no database and no network.
"""

import argparse
import ast
import asyncio
import inspect
import re

from app.maintenance import reindex
from app.maintenance.reindex import (
    _CANDIDATES_SQL,
    _TABLES_SQL,
    _qualified,
    should_reindex,
)


def _executed_sql(func) -> list[str]:
    """The SQL a function actually **executes** — not the prose around it.

    The strings are read out of the AST so a docstring that merely mentions
    ``DROP TABLE IF EXISTS`` cannot satisfy (or break) an assertion about
    what the code does.
    """
    out: list[str] = []
    for node in ast.walk(ast.parse(inspect.getsource(func))):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute"
                and node.args):
            continue
        first = node.args[0]
        if (isinstance(first, ast.Call) and isinstance(first.func, ast.Name)
                and first.func.id == "text" and first.args):
            first = first.args[0]          # unwrap text(...)
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            out.append(first.value)
        elif isinstance(first, ast.JoinedStr):
            # an f-string: the literal parts are what matters here
            out.append("".join(p.value for p in first.values
                               if isinstance(p, ast.Constant)
                               and isinstance(p.value, str)))
    return out


# ── the decision ────────────────────────────────────────────────────────────
def test_a_healthy_index_is_left_alone():
    """An index the size of a fresh build is not worth rebuilding."""
    rebuild, reason = should_reindex(3456 * 1024, 3456 * 1024, ratio=2.0)
    assert rebuild is False
    assert "1.00x" in reason


def test_a_bloated_index_is_rebuilt():
    """The shape PROD was in: 18,136 kB against a 3,456 kB fresh build."""
    rebuild, reason = should_reindex(18136 * 1024, 3456 * 1024, ratio=2.0)
    assert rebuild is True
    assert "5.25x" in reason


def test_the_ratio_is_inclusive():
    rebuild, _ = should_reindex(2000, 1000, ratio=2.0)
    assert rebuild is True


def test_growth_is_measured_against_the_fresh_build_not_an_absolute_size():
    """A big index that is the right size is still fine.

    ``local_content``'s geography index weighs 2,272 kB for 7,289 rows — more
    than a third of the size of ``places``' plain index with twelve times the
    rows. An absolute size threshold would rebuild it for ever, and a
    GiST rebuild is not byte-identical to a fresh build, so each pass would
    make it a little bigger.
    """
    rebuild, _ = should_reindex(2272 * 1024, 2272 * 1024, ratio=2.0)
    assert rebuild is False


def test_an_unmeasurable_index_is_never_rebuilt_on_a_guess():
    """No measurement is not a reason to rebuild — only --force overrides it."""
    rebuild, reason = should_reindex(None, 1000, ratio=2.0)
    assert rebuild is False
    assert "not measured" in reason

    rebuild, reason = should_reindex(1000, None, ratio=2.0)
    assert rebuild is False
    assert "not measured" in reason


def test_force_overrides_everything():
    assert should_reindex(None, 1000, ratio=2.0, force=True)[0] is True
    assert should_reindex(1000, None, ratio=2.0, force=True)[0] is True
    assert should_reindex(1000, 1000, ratio=2.0, force=True)[0] is True


def test_a_lower_ratio_rebuilds_more():
    assert should_reindex(1500, 1000, ratio=1.5)[0] is True
    assert should_reindex(1500, 1000, ratio=2.0)[0] is False


def test_a_tiny_index_is_left_alone_whatever_its_growth():
    """Below the floor, GiST packing noise can push a few-kB index past the
    ratio — so it is not rebuilt however bloated it looks, unless forced."""
    floor = 512 * 1024
    # 16 kB index at 2x growth — would rebuild, but it is below the floor.
    rebuild, reason = should_reindex(16 * 1024, 8 * 1024, ratio=2.0, min_bytes=floor)
    assert rebuild is False
    assert "too small" in reason
    # --force still overrides the floor.
    assert should_reindex(16 * 1024, 8 * 1024, ratio=2.0, min_bytes=floor, force=True)[0] is True
    # A real, megabyte-scale index above the floor is unaffected.
    assert should_reindex(18136 * 1024, 3456 * 1024, ratio=2.0, min_bytes=floor)[0] is True
    # The floor defaults to 0 (a no-op) so existing call sites are unchanged.
    assert should_reindex(16 * 1024, 8 * 1024, ratio=2.0)[0] is True


# ── naming ──────────────────────────────────────────────────────────────────
def test_qualified_names_are_quoted():
    assert _qualified("public", "ix_places_geom") == '"public"."ix_places_geom"'


def test_qualified_names_escape_embedded_quotes():
    """A quoted identifier with a quote in it must not break the statement."""
    assert _qualified('pu"blic', 'ix"geom') == '"pu""blic"."ix""geom"'


# ── the discovery query ─────────────────────────────────────────────────────
def test_the_candidates_query_finds_both_kinds_of_spatial_index():
    """A plain column index AND an expression index on (geom::geography).

    An expression index has no column number to look at — ``indkey`` is 0 for
    it — so it has to be matched by its definition instead. Missing it would
    leave the two biggest indexes on the table unmonitored.
    """
    sql = _CANDIDATES_SQL
    assert "amname = 'gist'" in sql
    assert "geometry" in sql and "geography" in sql
    assert "pg_get_indexdef" in sql, "the expression index is matched by its definition"
    assert "indkey[0]" in sql, "the plain index is matched by its column type"


def test_the_candidates_query_skips_constraint_backed_indexes():
    """REINDEX cannot rebuild an index that backs a constraint."""
    assert "pg_constraint" in _CANDIDATES_SQL
    assert "conindid" in _CANDIDATES_SQL


def test_the_candidates_query_labels_the_family():
    """Each index has to be compared against a fresh build of its *own* kind.

    A plain geometry index and an expression index on the same table are
    different sizes by a factor of several, so a baseline of one is not a
    baseline of the other.
    """
    assert "family" in _CANDIDATES_SQL
    assert "'plain'" in _CANDIDATES_SQL
    assert "'geography'" in _CANDIDATES_SQL


def test_the_tables_query_finds_the_geometry_column():
    """The baseline is built on a copy of the geometry column, so the tool
    needs to know which column it is."""
    sql = _TABLES_SQL
    assert "geometry" in sql
    assert "attname" in sql
    assert "atttypid" in sql


# ── the setting ─────────────────────────────────────────────────────────────
def test_the_ratio_is_a_setting():
    from app.core.config import settings

    ratio = settings.MAINTENANCE_REINDEX_GROWTH_RATIO
    assert isinstance(ratio, float)
    assert ratio > 1.0, (
        "a ratio at or below 1 would rebuild every index every run — and a "
        "GiST rebuild is not byte-identical to a fresh build, so each pass "
        "would make the index a little bigger"
    )


def test_the_size_floor_is_a_setting():
    from app.core.config import settings

    floor = settings.MAINTENANCE_REINDEX_MIN_KB
    assert isinstance(floor, int)
    assert floor > 0, (
        "a floor of 0 would leave the near-empty tables' few-kB indexes at "
        "the mercy of GiST packing noise"
    )


# ── the exit codes ──────────────────────────────────────────────────────────
def test_the_exit_codes_are_distinct_and_stable():
    """A scheduler wrapping this tool reads the exit code, so the numbers are
    part of the contract."""
    assert reindex.EXIT_OK == 0
    assert reindex.EXIT_FAILED == 1
    assert reindex.EXIT_NO_MATCH == 2


def test_a_failed_run_exits_non_zero(monkeypatch, capsys):
    """A run that could not even read the indexes must not look successful."""
    async def boom(args):
        raise RuntimeError("canceling statement due to lock timeout")

    monkeypatch.setattr(reindex, "_run", boom)
    code = asyncio.run(reindex._main(argparse.Namespace()))
    assert code == reindex.EXIT_FAILED
    assert "lock timeout" in capsys.readouterr().out


def test_a_failed_rebuild_makes_the_run_exit_non_zero(monkeypatch):
    """One index that could not be rebuilt is a failure of the run, not a
    success — a cron wrapper must be able to see it."""
    async def failed(args):
        return reindex.EXIT_FAILED

    monkeypatch.setattr(reindex, "_run", failed)
    assert asyncio.run(reindex._main(argparse.Namespace())) == reindex.EXIT_FAILED


def test_the_top_level_guard_does_not_raise(monkeypatch):
    """The guard catches the error and returns a code — it must not re-raise,
    or the operator gets a SQLAlchemy traceback instead of a message."""
    async def boom(args):
        raise RuntimeError("boom")

    monkeypatch.setattr(reindex, "_run", boom)
    assert asyncio.run(reindex._main(argparse.Namespace())) == reindex.EXIT_FAILED


# ── the schemas ─────────────────────────────────────────────────────────────
def test_the_two_discovery_queries_agree_on_the_schema():
    """The baseline is keyed by ``(schema, table)`` and the probe copies the
    column out of ``"<schema>"."<table>"``.

    If one query reports a bare ``relname`` and the other a schema-qualified
    name, the baseline lookup misses and the index is **silently** never
    rebuilt ("not measured") — and the probe would look for a table literally
    named ``myschema.mytable``.
    """
    for sql in (_CANDIDATES_SQL, _TABLES_SQL):
        assert "nspname" in sql, "both queries must report the schema"
    assert "tn.nspname" in _CANDIDATES_SQL
    assert "indrelid::regclass::text" not in _TABLES_SQL, (
        "regclass::text is schema-qualified only when the schema is outside "
        "the search_path — it must not be the identity of a table here"
    )


def test_the_tables_query_reports_the_table_not_the_index():
    """``c`` in the tables query is the **index** class (``c.oid =
    i.indexrelid``), so ``c.relname`` is the *index's* name.

    The baseline is keyed by table and the probe copies the column out of
    that table — a query that reported the index's name would look every
    baseline up under a key no candidate uses, and every index would read
    "not measured" (nothing is rebuilt on a guess, so it fails safe, but it
    measures nothing at all).
    """
    sql = _TABLES_SQL
    assert re.search(r"JOIN pg_class tc\s+ON tc\.oid = i\.indrelid", sql, re.I), (
        "the table's own class must be joined on the index's parent"
    )
    assert "tc.relname AS table_name" in sql, (
        "table_name must be the TABLE's name, not the index's"
    )


def test_the_probe_selects_from_the_schema_qualified_table():
    """The copy must name the schema *and* the table, each quoted separately."""
    src = inspect.getsource(reindex._baselines)
    assert '"{schema_name}"."{table_name}"' in src


def test_the_probe_table_cannot_drop_a_permanent_table():
    """The probe table is TEMPORARY and uniquely named.

    A fixed name would let ``DROP TABLE IF EXISTS`` fall through to a
    **permanent** table of the same name in ``public`` and drop it — a
    maintenance tool must never destroy data it did not create.
    """
    sqls = _executed_sql(reindex._baselines)
    assert sqls, "the baseline builder must execute some SQL"
    assert any("CREATE TEMP TABLE" in s.upper() for s in sqls)
    assert not any("IF EXISTS" in s.upper() for s in sqls), (
        "an IF EXISTS drop can fall through to a permanent table of the same "
        "name — the probe table is uniquely named instead"
    )
    assert "uuid" in inspect.getsource(reindex._baselines), (
        "the probe table must carry a unique token"
    )
