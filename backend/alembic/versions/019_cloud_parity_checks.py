"""The dual-read ledger — one row per local-vs-cloud comparison.

The migration off whereq.com's own crawler is decided by **reading** the
differences between the two answers, not by assuming there are none. So the
comparisons are recorded, in a table, with the counts and the identities
that differ.

The identity arrays and the difference map are JSONB rather than text: a
comparison is read back as a set of uids to join against, and a JSON
document keeps one row per comparison instead of a second table.

Revision ID: 019_cloud_parity_checks
Revises: 018_geo_places
Create Date: 2026-11-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "019_cloud_parity_checks"
down_revision = "018_geo_places"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloud_parity_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("surface", sa.String(length=40), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="match"),
        sa.Column("local_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cloud_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("only_local", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("only_cloud", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("differing", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cloud_parity_checks_surface", "cloud_parity_checks", ["surface"])
    op.create_index("ix_cloud_parity_checks_checked_at", "cloud_parity_checks", ["checked_at"])
    op.create_index(
        "ix_cloud_parity_surface_checked", "cloud_parity_checks", ["surface", "checked_at"])


def downgrade() -> None:
    op.drop_index("ix_cloud_parity_surface_checked", table_name="cloud_parity_checks")
    op.drop_index("ix_cloud_parity_checks_checked_at", table_name="cloud_parity_checks")
    op.drop_index("ix_cloud_parity_checks_surface", table_name="cloud_parity_checks")
    op.drop_table("cloud_parity_checks")
