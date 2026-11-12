"""Per-provider geocoding usage counters (quota tracking)

Revision ID: 006_geocode_usage
Revises: 005_local_content
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = "006_geocode_usage"
down_revision = "005_local_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geocode_provider_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "period", name="uq_geocode_usage"),
    )
    op.create_index("ix_geocode_provider_usage_provider", "geocode_provider_usage", ["provider"])


def downgrade() -> None:
    op.drop_table("geocode_provider_usage")
