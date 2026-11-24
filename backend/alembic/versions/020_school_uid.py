"""The school's cross-system key — the uid.

THE UID
-------
A school is identified across the two systems by its **uid**: the board's
slug and the school's own code, joined by a slash — ``ycdsb/0158``,
``dcdsb/austin``. whereq.cloud's routes take it as the path parameter, and
it does not change when the dataset is reloaded.

This app's school rows were identified by an integer row id, which is a
key in this app's own database and in nowhere else. That is not a
migration problem for the *data* — the rows are the same rows — but it is a
migration problem for the **join**: the dual-read window has to know that
the school it holds locally is the school whereq.cloud holds, and the
integer id is not a key the two systems share.

So the uid is added here, and `scripts/seed_school_uids.py` fills it from
whereq.cloud.

WHY THE SCRIPT AND NOT THE MIGRATION
------------------------------------
The value comes from another system, over the network, with a key that
lives in the environment. A migration must not need either. The script is
idempotent, it only ever **fills** a missing uid, and it refuses to guess:
it matches on the row id — the import preserved this app's integers, so
the platform's id *is* this app's id — and it reports every row it could
not match rather than writing something plausible.

WHAT THIS DOES NOT DO
---------------------
It does not touch any other column. The local tables stay exactly as they
are — they are kept, read-only, for the rollback window — and this column
is the only thing added.

Revision ID: 020_school_uid
Revises: 019_cloud_parity_checks
Create Date: 2026-11-22
"""
from alembic import op
import sqlalchemy as sa

revision = "020_school_uid"
down_revision = "019_cloud_parity_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("school", sa.Column("uid", sa.String(length=255), nullable=True))
    # The uid is looked up on every detail and boundary request, so it is
    # indexed. The index is partial: a row with no uid yet — the seed has
    # not run — is not a school anybody can ask for.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_school_uid "
        "ON school (uid) WHERE uid IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_school_uid")
    op.drop_column("school", "uid")
