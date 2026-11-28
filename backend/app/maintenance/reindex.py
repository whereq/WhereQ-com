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

A second floor applies: an index below ``MAINTENANCE_REINDEX_MIN_KB`` is
never rebuilt, whatever its growth ratio says. GiST's packing noise can
push a few-kB index past the ratio on noise alone, and the indexes that
matter are megabytes.

WHAT IT DOES NOT DO
-------------------
It does not touch the **heap**. ``REINDEX`` rebuilds the index from the
table's live rows, so the rows are never rewritten and the data is never at
risk — but it also means a bloated *table* is not fixed by this tool.
``VACUUM FULL`` would, and it takes an ``ACCESS EXCLUSIVE`` lock that blocks
every read and write, so it needs a maintenance window and a decision.

``REINDEX INDEX CONCURRENTLY`` takes only a ``SHARE UPDATE EXCLUSIVE`` lock:
reads and writes continue while the new index is built.

EXIT CODES
----------
``0``  everything asked for was done (including "nothing was bloated").
``1``  at least one rebuild failed, or the run itself could not read the
       indexes — check the message and the locks.
``2``  ``--index`` named an index that does not exist.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import NamedTuple

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

#: Exit codes. Anything a scheduler wraps this in reads them.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NO_MATCH = 2


class Candidate(NamedTuple):
    """One spatial index the tool may rebuild.

    A named tuple rather than a bare tuple because the fields are read in
    several places and a positional unpack that drifts is a silent bug.
    """
    schema_name: str    # the **index's** schema
    index_name: str
    table_schema: str   # the table's schema (equal to the index's, but said
    table_name: str     #   out separately so the two can never drift)
    size_bytes: int
    family: str         # "plain" | "geography"


#: The GiST indexes that can hold geometry: a plain column index, or an
#: expression index on ``(geom::geography)``. The expression ones are matched
#: by their definition, because an expression index has no column number to
#: look at (``indkey`` is 0 for it).
#:
#: ``family`` is what the index is compared against: the fresh build of the
#: same flavour on the same table.
_CANDIDATES_SQL = """
    SELECT n.nspname                AS schema_name,
           ic.relname               AS index_name,
           tn.nspname               AS table_schema,
           tc.relname               AS table_name,
           pg_relation_size(ic.oid) AS bytes,
           CASE WHEN EXISTS (SELECT 1
                               FROM pg_attribute a
                              WHERE a.attrelid = i.indrelid
                                AND a.attnum = i.indkey[0]
                                AND a.atttypid = 'geometry'::regtype)
                THEN 'plain' ELSE 'geography' END AS family
      FROM pg_class ic
      JOIN pg_index i      ON i.indexrelid = ic.oid
      JOIN pg_class tc     ON tc.oid = i.indrelid
      JOIN pg_namespace n  ON n.oid = ic.relnamespace
      JOIN pg_namespace tn ON tn.oid = tc.relnamespace
      JOIN pg_am am        ON am.oid = ic.relam
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
#:
#: The schema is selected here as well as in the candidates query, and the two
#: must agree: the baseline is keyed by (schema, table), and the probe copies
#: the column out of ``"<schema>"."<table>"``. A bare ``relname`` here would
#: make the probe look for a table called ``myschema.mytable``.
_TABLES_SQL = """
    SELECT DISTINCT n.nspname AS schema_name,
                    tc.relname AS table_name,
                    a.attname  AS column_name
      FROM pg_index i
      JOIN pg_class c      ON c.oid = i.indexrelid
      JOIN pg_class tc     ON tc.oid = i.indrelid
      JOIN pg_am am        ON am.oid = c.relam
      JOIN pg_namespace n  ON n.oid = tc.relnamespace
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

#: The prefix of the temporary table the fresh baseline is built on. The name
#: is made unique per run: a fixed name would let ``DROP TABLE IF EXISTS``
#: fall through to a **permanent** table of the same name in ``public``.
_PROBE_PREFIX = "_wq_reindex_probe"


def should_reindex(current_bytes: int | None, baseline_bytes: int | None, *,
                   ratio: float, force: bool = False,
                   min_bytes: int = 0) -> tuple[bool, str]:
    """Whether an index is worth rebuilding, and why.

    The decision is **growth against a fresh build** of the same index:
    ``current / baseline``. An index that cannot be measured is never
    rebuilt on a guess — only ``--force`` overrides that.

    ``min_bytes`` is an absolute floor: below it, GiST packing noise can push a
    tiny index past the ratio, so it is left alone regardless of growth (again,
    ``--force`` overrides).
    """
    if force:
        return True, "forced"
    if current_bytes is None or not baseline_bytes:
        return False, "not measured"
    if current_bytes < min_bytes:
        return False, f"too small to matter ({_kb(current_bytes)} < {_kb(min_bytes)})"
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


async def _candidates(conn) -> list[Candidate]:
    rows = (await conn.execute(text(_CANDIDATES_SQL))).all()
    return [Candidate(*row) for row in rows]


async def _baselines(conn, only_tables: set[tuple[str, str]] | None = None,
                     ) -> dict[tuple[str, str, str], int]:
    """The size of a **fresh** build of each index flavour, per table.

    The baseline is built for real, on a temporary copy of the table's
    geometry column — a guess about what a GiST index "should" weigh would
    be exactly the kind of number this tool exists to replace with a
    measurement.

    The key is ``(schema, table, family)`` — the same three things the
    candidates query reports, so a baseline can never be looked up under a
    name the candidate does not use.

    ``only_tables`` restricts the (expensive) probe builds to the tables we
    actually need — so a ``--index`` run doesn't copy and index every geometry
    table in the database just to measure one.
    """
    rows = (await conn.execute(text(_TABLES_SQL))).all()
    baselines: dict[tuple[str, str, str], int] = {}
    token = uuid.uuid4().hex[:12]
    for n, (schema_name, table_name, column_name) in enumerate(rows):
        if only_tables is not None and (schema_name, table_name) not in only_tables:
            continue
        # A unique name per table, per run: nothing else in the database can
        # be named this, so the drop at the end can only ever hit our own
        # temporary table.
        probe = f"{_PROBE_PREFIX}_{token}_{n}"
        await conn.execute(text(
            f'CREATE TEMP TABLE "{probe}" AS '
            f'SELECT "{column_name}" AS geom FROM "{schema_name}"."{table_name}"'
        ))
        # Both flavours are built on the same probe table and are measured
        # before it is dropped — dropping the table drops its indexes too, so
        # no index has to be dropped by name.
        for family, definition in (
            ("plain", "USING gist (geom)"),
            ("geography", "USING gist ((geom::geography))"),
        ):
            name = f"{probe}_{family}"
            await conn.execute(text(
                f'CREATE INDEX "{name}" ON "{probe}" {definition}'
            ))
            size = (await conn.execute(
                text("SELECT pg_relation_size(:name)"),
                {"name": name},
            )).scalar_one()
            baselines[(schema_name, table_name, family)] = int(size)
        await conn.execute(text(f'DROP TABLE "{probe}"'))
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


async def _run(args) -> int:
    only = set(args.index or [])

    # The read phase — discovery, baselines and measurement — shares one
    # connection; the rebuild phase opens its own, because REINDEX
    # CONCURRENTLY cannot run inside a transaction.
    async with engine.connect() as conn:
        candidates = await _candidates(conn)
        if not candidates:
            print("No spatial indexes found.")
            return EXIT_OK

        # Filter first, so the header count, the baselines and the measurement
        # all concern only the indexes being considered — a --index run should
        # not probe-build every geometry table in the database to measure one.
        if only:
            candidates = [c for c in candidates if c.index_name in only]
            if not candidates:
                print(f"No spatial index matched: {', '.join(sorted(only))}")
                return EXIT_NO_MATCH

        has_pgstattuple = bool(
            (await conn.execute(text(_HAS_PGSTATTUPLE_SQL))).first()
        )
        needed_tables = {(c.table_schema, c.table_name) for c in candidates}
        baselines = await _baselines(conn, needed_tables)
        min_bytes = max(0, args.min_kb) * 1024

        _h(f"Spatial indexes — {len(candidates)} candidate(s)")
        print(f"  {'index':<32} {'size':>11} {'fresh':>11} {'growth':>8} {'free':>7}  verdict")
        print(f"  {'-' * 32} {'-' * 11} {'-' * 11} {'-' * 8} {'-' * 7}  {'-' * 30}")

        plan: list[tuple[Candidate, bool, str]] = []
        for c in candidates:
            baseline = baselines.get((c.table_schema, c.table_name, c.family))
            rebuild, reason = should_reindex(
                c.size_bytes, baseline, ratio=args.ratio, force=args.force,
                min_bytes=min_bytes)
            free = None
            if has_pgstattuple:
                try:
                    free = (await _measure(conn, c.schema_name, c.index_name))[0]
                except Exception as exc:  # noqa: BLE001 — a cosmetic number
                    # must not abort a run that can still rebuild the index.
                    free = None
                    reason += f" (free-space not measured: {type(exc).__name__})"
            plan.append((c, rebuild, reason))
            growth = (f"{c.size_bytes / baseline:.2f}x" if baseline else "n/a")
            fresh = _kb(baseline) if baseline else "n/a"
            free_text = f"{free:.2f} %" if free is not None else "n/a"
            print(f"  {c.index_name:<32} {_kb(c.size_bytes):>11} {fresh:>11} "
                  f"{growth:>8} {free_text:>7}  {reason}")

    todo = [p for p in plan if p[1]]
    if not todo:
        _h("Nothing to rebuild")
        print("  Every candidate is within the growth threshold.")
        print(f"  (rebuild when an index is {args.ratio:g}x a fresh build of itself)")
        return EXIT_OK

    if args.dry_run:
        _h(f"Dry run — {len(todo)} index(es) would be rebuilt")
        for c, _, reason in todo:
            print(f"  {c.index_name} ({c.table_name}) — {_kb(c.size_bytes)} — {reason}")
        return EXIT_OK

    _h(f"Rebuilding {len(todo)} index(es)")
    rebuilt: list[tuple[Candidate, bool, str]] = []
    failed: list[tuple[str, str, Exception]] = []
    for item in todo:
        c, _, reason = item
        try:
            await _reindex(c.schema_name, c.index_name)
        except Exception as exc:  # noqa: BLE001 — one index must not abort the rest
            failed.append((c.schema_name, c.index_name, exc))
            print(f"  \033[31m✖\033[0m {c.index_name} — FAILED: {exc}")
            continue
        rebuilt.append(item)
        print(f"  REINDEX INDEX CONCURRENTLY {c.index_name} — {reason}")

    if failed:
        # REINDEX CONCURRENTLY leaves an INVALID index behind on failure; it
        # keeps consuming space until it is dropped. Point the operator at it.
        _h(f"{len(failed)} rebuild(s) failed")
        for schema_name, index_name, exc in failed:
            print(f"  {index_name}: {exc}")
        print("  REINDEX INDEX CONCURRENTLY can leave an INVALID index behind.")
        print("  Find any:  SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;")
        print("  Drop it:   DROP INDEX CONCURRENTLY IF EXISTS <name>;  -- then re-run")

    if not rebuilt:
        # Nothing succeeded: the run failed, and a scheduler must be able to
        # tell that from "there was nothing to do".
        return EXIT_FAILED

    async with engine.connect() as conn:
        after = {(c.schema_name, c.index_name): c.size_bytes
                 for c in await _candidates(conn)}

    _h("Result")
    total_before = total_after = 0
    for c, _, _ in rebuilt:
        new_bytes = after.get((c.schema_name, c.index_name), c.size_bytes)
        total_before += c.size_bytes
        total_after += new_bytes
        print(f"  {c.index_name:<32} {_kb(c.size_bytes):>11} -> {_kb(new_bytes):<11} "
              f"({_kb(c.size_bytes - new_bytes)} reclaimed)")
    print(f"  {'-' * 32} {'-' * 11}    {_kb(total_before - total_after)} reclaimed in total")
    if total_after > total_before:
        print("  (A GiST rebuild is not byte-identical to a fresh build — its packing differs.)")

    return EXIT_FAILED if failed else EXIT_OK


async def _main(args) -> int:
    try:
        return await _run(args)
    except Exception as exc:  # noqa: BLE001 — the top-level guard
        # The read phase can fail for reasons that have nothing to do with
        # this tool: a lock held by another session, a missing privilege, a
        # dropped table. An operator should not have to read a SQLAlchemy
        # traceback to find out which.
        print(f"\n\033[31m✖\033[0m The reindex run failed: {exc}")
        print("  Nothing was rebuilt.")
        print("  The usual causes are a lock held by another session or a missing")
        print("  privilege. Check the locks:")
        print("    SELECT locktype, relation::regclass, mode, granted")
        print("      FROM pg_locks WHERE relation IS NOT NULL;")
        return EXIT_FAILED
    finally:
        # Disposed in the same event loop the engine was used in — a second
        # `asyncio.run` would try to close the pool's connections from a
        # different loop.
        try:
            await engine.dispose()
        except Exception:  # noqa: BLE001 — disposal must not mask the result
            pass


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
    p.add_argument("--min-kb", type=int,
                   default=settings.MAINTENANCE_REINDEX_MIN_KB,
                   help="never rebuild an index smaller than this, whatever its "
                        f"growth ratio (default {settings.MAINTENANCE_REINDEX_MIN_KB})")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
