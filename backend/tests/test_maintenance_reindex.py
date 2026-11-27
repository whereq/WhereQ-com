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

from app.maintenance.reindex import (
    _CANDIDATES_SQL,
    _TABLES_SQL,
    _qualified,
    should_reindex,
)


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
