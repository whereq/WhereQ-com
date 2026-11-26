"""Expression GiST indexes on ``(geom::geography)`` — the radius queries, indexed.

THE PROBLEM
-----------
Every radius query in this app asks PostGIS for **metres**:

    ST_DWithin(geom::geography, point::geography, radius_m)

The ``::geography`` cast is not optional. ``ST_DWithin`` on a 4326 *geometry*
measures in **degrees**, so a radius of 2000 would mean 2000 degrees — and the
maximum separation in lat/long space is about 254 degrees, so it would match
the entire planet. The cast is what makes the third argument metres.

But the cast is also what **loses the index**. Every spatial index in this
schema is a plain GiST index on the ``geom`` column (``ix_places_geom``,
``ix_local_content_geom``, ``ix_hazards_geom``), so the index entries hold
*geometry* values while the query asks for *geography* values. The expression
does not match the index column, so the planner falls back to a parallel
sequential scan and evaluates the predicate row by row.

Measured on PROD (2026-11-25, 87,240 rows, a 2 km radius, the exact predicate
above):

    Parallel Seq Scan          112 ms   (median of 24 runs)
    Parallel Bitmap Heap Scan    28 ms   (with this index)

The index is the fix, and the reason it was not built earlier is that the
**expression** index — an index on ``(geom::geography)``, not on ``geom`` — was
not the thing anyone reaches for first. A plain ``gist (geom)`` is the default
that every earlier migration created, and it is the right index for the
*viewport* queries (``ST_Intersects`` against an envelope, which expands to
``&&`` and matches the plain column).

WHAT THIS DOES NOT DO
---------------------
It does not replace any index. ``ix_places_geom`` and its siblings stay —
they serve the viewport queries, and ``ST_Intersects``/``&&`` still match the
plain column. The expression index is **additional**, and it is what the
**radius** queries need.

It also does not change a single row of data, and it does not change any
query: the same predicate, the same result, the same semantics. It changes
only how the rows are found.

THE COST
--------
An index entry now holds a geography representation as well, so the index is
about 1.9x the size of the plain one (measured on an identical copy of
``places``: 3,456 kB → 6,456 kB), and every INSERT/UPDATE maintains it. The
write path here is **batch ingest** — the weekly catalogue sync — not
high-frequency writes, so the write amplification is low.

One honest note: ``places`` is rewritten wholesale every week (the upstream
restamps ``updated_at`` on every row), and GiST does not reclaim the dead
entries. The existing ``ix_places_geom`` is already 18 MB with 85% free
space. This index will grow the same way. Rebuilding the existing index is a
separate operation and a separate decision.

The build is a plain ``CREATE INDEX``, which takes a SHARE lock: reads are not
blocked, writes are, for the duration of the build (measured at 239 ms on a
copy of the same 87,240 rows).

Revision ID: 021_geography_expression_indexes
Revises: 020_school_uid
Create Date: 2026-11-25
"""
from alembic import op

revision = "021_geography_expression_indexes"
down_revision = "020_school_uid"
branch_labels = None
depends_on = None


#: The three tables whose radius query casts to geography:
#: ``nearby.py:193`` (places), ``nearby.py:404`` (local content),
#: ``nearby.py:441`` (hazards) — plus ``fuel_stations.py:375`` and
#: ``place_dedup.py:56``, which read ``places`` with the same predicate.
_TABLES = ("places", "local_content", "hazards")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_geom_geog "
            f"ON {table} USING GIST ((geom::geography))"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_geom_geog")
