"""Rebuild the spatial indexes that the upstream's weekly rewrite bloats.

Run inside the api (or consumer) container so it reuses the app's DATABASE_URL:

    python -m app.maintenance.reindex             # rebuild whatever is bloated
    python -m app.maintenance.reindex --dry-run   # report only, change nothing
    python -m app.maintenance.reindex --force     # rebuild every candidate
    python -m app.maintenance.reindex --index ix_places_geom

WHY IT EXISTS
-------------
whereq.cloud restamps every row every week — ``updated_at = now()`` on an
``on_conflict_do_update`` — so every row of ``places`` is rewritten, and GiST
never returns the pages the dead index entries occupy. The index grows: on
PROD ``ix_places_geom`` had reached **18,136 kB** while the same index built
fresh is **3,456 kB**.

HOW IT DECIDES
--------------
**Not** by the share of free space, and **not** by the tuple count. Both are
misleading for a GiST index:

* *Free space* is a property of the **data**, not of bloat. A freshly built
  geography index on ``local_content`` is **89.52 % free** (GiST splits
  pages and does not pack them away) while a freshly built plain geometry
  index on ``places`` is **29.75 % free**. A threshold on free space flags
  the healthy ones and misses the bloated ones.
* *Tuple count* is only wrong in one direction: GiST marks an entry dead
  only when a VACUUM has visited the index, so an index that was never
  vacuumed reports its dead entries as live tuples and looks twice its
  real size.

So the tool measures the thing that is actually true — **how much bigger the
index is than a fresh build of the same index would be**. It builds that
fresh build itself, on a temporary copy of the table's geometry column, and
compares. An index is rebuilt when it has grown past
``MAINTENANCE_REINDEX_GROWTH_RATIO`` times that baseline.

The **baseline is not the rebuild**: GiST's packing is not deterministic, so
a rebuild of a healthy index can land 20 % above or below a fresh build.
That is why the threshold is a ratio and not an equality — and why a
rebuild of a healthy index is not worth doing at all.

WHAT IT DOES NOT DO
-------------------
It does not touch the **heap**. ``REINDEX`` rebuilds the index from the
table's live rows, so the rows are never rewritten and the data is never at
risk — but it also means a bloated *table* is not fixed by this tool.
``VACUUM FULL`` would, and it takes an ``ACCESS EXCLUSIVE`` lock that blocks
every read and write, so it needs a maintenance window and a decision.

``REINDEX INDEX CONCURRENTLY`` takes only a ``SHARE UPDATE EXCLUSIVE`` lock:
reads and writes continue while the new index is built.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

#: The GiST indexes that can hold geometry: a plain column index, or an
#: expression index on ``(geom::geography)``. The expression ones are matched
#: by their definition, because an expression index has no column number to
#: look at (``indkey`` is 0 for it).
#
#: ``family`` is what the index is compared against: the fresh build of the
#: same flavour on the same table.
_CANDIDATES_SQL = """
    SELECT n.nspname                AS schema_name,
           ic.relname               AS index_name,
           tc.relname               AS table_name,
           pg_relation_size(ic.oid) AS bytes,
           CASE WHEN EXISTS (SELECT 1
                               FROM pg_attribute a
                              WHERE a.attrelid = i.indrelid
                                AND a.attnum = i.indkey[0]
                                AND a.atttypid = 'geometry'::regtype)
                THEN 'plain' ELSE 'geography' END AS family
      FROM pg_class ic
      JOIN pg_index i     ON i.indexrelid = ic.oid
      JOIN pg_class tc    ON tc.oid = i.indrelid
      JOIN pg_namespace n ON n.oid = ic.relnamespace
      JOIN pg_am am       ON am.oid = ic.relam
     WHERE am.amname = 'gist'
       AND ic.relkind = 'i'
       -- an index that backs a constraint cannot be rebuilt this way
       AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = ic.oid)
       AND ( EXISTS (SELECT 1
                       FROM pg_attribute a
                      WHERE a.attrelid = i.indrelid
                        AND a.attnum = i.indkey[0]
                        AND a.atttypid IN ('geometry'::regtype, 'geography'::regtype))
             OR pg_get_indexdef(ic.oid) ILIKE '%geography%' )
     ORDER BY pg_relation_size(ic.oid) DESC
"""

#: The tables that carry a geometry column, with that column's name.
_TABLES_SQL = """
    SELECT DISTINCT i.indrelid::regclass::text AS table_name,
                    a.attname                   AS column_name
      FROM pg_index i
      JOIN pg_class c ON c.oid = i.indexrelid
      JOIN pg_am am   ON am.oid = c.relam
      JOIN pg_attribute a
        ON a.attrelid = i.indrelid
       AND a.atttypid = 'geometry'::regtype
     WHERE am.amname = 'gist'
       AND c.relkind = 'i'
"""

#: The free-space share of an index, and how many of its tuples are dead.
#: The name is **bound as a value** and cast to ``regclass``: passed as SQL
#: identifiers it would be parsed as a FROM-clause entry, not as a relation
#: name.
_MEASURE_SQL = """
    SELECT free_percent, tuple_count, dead_tuple_count
      FROM pgstattuple(CAST(:qualified AS regclass))
"""

_HAS_PGSTATTUPLE_SQL = """
    SELECT 1 FROM pg_extension WHERE extname = 'pgstattuple'
"""

#: The temporary table the fresh baseline is built on.
_PROBE_TABLE = "_wq_reindex_probe"


def should_reindex(current_bytes: int | None, baseline_bytes: int | None, *,
                   ratio: float, force: bool = False) -> tuple[bool, str]:
    """Whether an index is worth rebuilding, and why.

    The decision is **growth against a fresh build** of the same index:
    ``current / baseline``. An index that cannot be measured is never
    rebuilt on a guess — only ``--force`` overrides that.
    """
    if force:
        return True, "forced"
    if current_bytes is None or not baseline_bytes:
        return False, "not measured"
    growth = current_bytes / baseline_bytes
    if growth >= ratio:
        return True, f"{growth:.2f}x a fresh build (>= {ratio:g}x)"
    return False, f"{growth:.2f}x a fresh build (< {ratio:g}x)"


def _qualified(schema_name: str, index_name: str) -> str:
    """A safely quoted, schema-qualified index name."""
    return '"{}"."{}"'.format(schema_name.replace('"', '""'),
                               index_name.replace('"', '""'))


def _kb(size_bytes: int) -> str:
    return f"{size_bytes / 1024:,.0f} kB"


def _h(title: str) -> None:
    print(f"\n\033[1;36m{title}\033[0m")
    print("─" * len(title))


async def _candidates(conn) -> list[tuple[str, str, str, int, str]]:
    rows = (await conn.execute(text(_CANDIDATES_SQL))).all()
    return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]


async def _baselines(conn) -> dict[tuple[str, str], int]:
    """The size of a **fresh** build of each index flavour, per table.

    The baseline is built for real, on a temporary copy of the table's
    geometry column — a guess about what a GiST index "should" weigh would
    be exactly the kind of number this tool exists to replace with a
    measurement.
    """
    tables = (await conn.execute(text(_TABLES_SQL))).all()
    baselines: dict[tuple[str, str], int] = {}
    for table_name, column_name in tables:
        await conn.execute(text(f'DROP TABLE IF EXISTS "{_PROBE_TABLE}"'))
        await conn.execute(text(
            f'CREATE TEMP TABLE "{_PROBE_TABLE}" AS '
            f'SELECT "{column_name}" AS geom FROM "{table_name}"'
        ))
        for family, definition in (
            ("plain", "USING gist (geom)"),
            ("geography", "USING gist ((geom::geography))"),
        ):
            name = f"{_PROBE_TABLE}_{family}"
            await conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
            await conn.execute(text(
                f'CREATE INDEX "{name}" ON "{_PROBE_TABLE}" {definition}'
            ))
            size = (await conn.execute(
                text("SELECT pg_relation_size(:name)"),
                {"name": name},
            )).scalar_one()
            baselines[(table_name, family)] = int(size)
            await conn.execute(text(f'DROP INDEX "{name}"'))
        await conn.execute(text(f'DROP TABLE "{_PROBE_TABLE}"'))
    return baselines


async def _measure(conn, schema_name: str, index_name: str):
    """``(free_percent, tuple_count, dead_tuple_count)``."""
    qualified = _qualified(schema_name, index_name)
    row = (await conn.execute(text(_MEASURE_SQL),
                              {"qualified": qualified})).one()
    return float(row[0]), int(row[1]), int(row[2])


async def _reindex(schema_name: str, index_name: str) -> None:
    """``REINDEX INDEX CONCURRENTLY`` — it cannot run inside a transaction."""
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(
            text(f"REINDEX INDEX CONCURRENTLY {_qualified(schema_name, index_name)}")
        )


async def _run(args) -> None:
    only = set(args.index or [])

    # The read phase — discovery, baselines and measurement — shares one
    # connection; the rebuild phase opens its own, because REINDEX
    # CONCURRENTLY cannot run inside a transaction.
    async with engine.connect() as conn:
        candidates = await _candidates(conn)
        if not candidates:
            print("No spatial indexes found.")
            return

        has_pgstattuple = bool(
            (await conn.execute(text(_HAS_PGSTATTUPLE_SQL))).first()
        )
        baselines = await _baselines(conn)

        _h(f"Spatial indexes — {len(candidates)} candidate(s)")
        print(f"  {'index':<32} {'size':>11} {'fresh':>11} {'growth':>8} {'free':>7}  verdict")
        print(f"  {'-' * 32} {'-' * 11} {'-' * 11} {'-' * 8} {'-' * 7}  {'-' * 30}")

        plan: list[tuple[str, str, str, int, bool, str]] = []
        for schema_name, index_name, table_name, size_bytes, family in candidates:
            if only and index_name not in only:
                continue
            baseline = baselines.get((table_name, family))
            rebuild, reason = should_reindex(
                size_bytes, baseline, ratio=args.ratio, force=args.force)
            free = None
            if has_pgstattuple:
                free = (await _measure(conn, schema_name, index_name))[0]
            plan.append((schema_name, index_name, table_name, size_bytes, rebuild, reason))
            growth = (f"{size_bytes / baseline:.2f}x" if baseline else "n/a")
            fresh = _kb(baseline) if baseline else "n/a"
            free_text = f"{free:.2f} %" if free is not None else "n/a"
            print(f"  {index_name:<32} {_kb(size_bytes):>11} {fresh:>11} "
                  f"{growth:>8} {free_text:>7}  {reason}")

    todo = [p for p in plan if p[4]]
    if not todo:
        _h("Nothing to rebuild")
        print("  Every candidate is within the growth threshold.")
        print(f"  (rebuild when an index is {args.ratio:g}x a fresh build of itself)")
        return

    if args.dry_run:
        _h(f"Dry run — {len(todo)} index(es) would be rebuilt")
        for schema_name, index_name, table_name, size_bytes, _, reason in todo:
            print(f"  {index_name} ({table_name}) — {_kb(size_bytes)} — {reason}")
        return

    _h(f"Rebuilding {len(todo)} index(es)")
    for schema_name, index_name, table_name, size_bytes, _, reason in todo:
        await _reindex(schema_name, index_name)
        print(f"  REINDEX INDEX CONCURRENTLY {index_name} — {reason}")

    async with engine.connect() as conn:
        after = {(r[0], r[1]): r[3] for r in await _candidates(conn)}

    _h("Result")
    total_before = total_after = 0
    for schema_name, index_name, table_name, size_bytes, _, _ in todo:
        new_bytes = after.get((schema_name, index_name), size_bytes)
        total_before += size_bytes
        total_after += new_bytes
        print(f"  {index_name:<32} {_kb(size_bytes):>11} -> {_kb(new_bytes):<11} "
              f"({_kb(size_bytes - new_bytes)} reclaimed)")
    print(f"  {'-' * 32} {'-' * 11}    {_kb(total_before - total_after)} reclaimed in total")
    if total_after > total_before:
        print("  (A GiST rebuild is not byte-identical to a fresh build — its packing differs.)")


async def _main(args) -> None:
    try:
        await _run(args)
    finally:
        # Disposed in the same event loop the engine was used in — a second
        # `asyncio.run` would try to close the pool's connections from a
        # different loop.
        await engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser(
        prog="python -m app.maintenance.reindex",
        description="Rebuild the spatial indexes the weekly upstream rewrite bloats",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="report what would be rebuilt and change nothing")
    p.add_argument("--force", action="store_true",
                   help="rebuild every candidate, measured or not")
    p.add_argument("--index", action="append", metavar="NAME",
                   help="only this index (repeatable)")
    p.add_argument("--ratio", type=float,
                   default=settings.MAINTENANCE_REINDEX_GROWTH_RATIO,
                   help="rebuild when an index is at least this many times a "
                        f"fresh build of itself (default "
                        f"{settings.MAINTENANCE_REINDEX_GROWTH_RATIO:g})")
    args = p.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
