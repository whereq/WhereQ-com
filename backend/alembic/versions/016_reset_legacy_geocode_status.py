"""Reset the legacy 'fallback_city' geocode status.

Migration 014 removed the city-centre pins from every row the crawler had
placed that way, but it left the marker behind in ``geocode_status``.  Those
rows still say *fallback_city* — a value that is not in the documented
vocabulary (``none|pending|ok|failed|rejected``) and that describes a pin they
no longer have.  The column was lying about half the corpus.

*none* is what an unplaced row says: the column's own server default, and the
value the crawler writes for content it could not place.  No coordinate
changes here and no code reads this column, so the change is pure bookkeeping —
but the column is the first thing anyone (or anything) looks at when asking
"why does this row have no position?", and it should answer honestly.

The update covers every row that still carries the marker, active or expired.
Scoping it to the active rows would leave a moving target: a row that is
active today is expired tomorrow, still carrying the marker, and a migration
that has already run will not touch it again.

Revision ID: 016_reset_legacy_geocode_status
Revises: 015_nearby_default_radius
Create Date: 2026-11-07
"""
from alembic import op

revision = "016_reset_legacy_geocode_status"
down_revision = "015_nearby_default_radius"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE local_content SET geocode_status = 'none' "
        "WHERE geocode_status = 'fallback_city'"
    )


def downgrade() -> None:
    # Nothing to undo.  The old value described a city-centre pin that
    # migration 014 had already removed; restoring it would put the marker
    # back on rows that have no position, which is the state this migration
    # exists to end.
    pass
