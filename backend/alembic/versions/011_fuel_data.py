"""Fuel data — sync bookkeeping + aggregated whereq.cloud price series

Revision ID: 011_fuel_data
Revises: 010_maps_service
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "011_fuel_data"
down_revision = "010_maps_service"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per fuel coverage target (country / state / municipality / bbox).
    # The crawler rotates through targets instead of re-pulling the whole
    # continent every tick, so it needs to know when each target was last
    # synced and whether the last attempt failed.
    op.create_table(
        "fuel_sync_state",
        sa.Column("target_key", sa.String(128), primary_key=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("municipality", sa.String(160), nullable=True),
        sa.Column("bbox", sa.String(128), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("station_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # The aggregated price series (EIA weekly for the US, StatCan monthly for
    # Canada, CRE for Mexico): state / national / metro averages per product.
    # Station-level prices live in `places.metadata_json` — this is the
    # regional context around them.
    op.create_table(
        "fuel_price_series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain", sa.String(24), nullable=False),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("region", sa.String(24), nullable=True),
        sa.Column("geo", sa.String(160), nullable=True),
        sa.Column("item", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(64), nullable=True),
        sa.Column("frequency", sa.String(16), nullable=True),
        sa.Column("latest_period", sa.String(32), nullable=True),
        sa.Column("latest_value", sa.Float(), nullable=True),
        sa.Column("prev_value", sa.Float(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("spark", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fuel_price_series_domain", "fuel_price_series", ["domain"])
    op.create_index("ix_fuel_price_series_source", "fuel_price_series", ["source"])
    op.create_index("ix_fuel_price_series_region", "fuel_price_series", ["region"])
    op.create_index("ix_fuel_price_series_geo", "fuel_price_series", ["geo"])


def downgrade() -> None:
    op.drop_index("ix_fuel_price_series_geo", table_name="fuel_price_series")
    op.drop_index("ix_fuel_price_series_region", table_name="fuel_price_series")
    op.drop_index("ix_fuel_price_series_source", table_name="fuel_price_series")
    op.drop_index("ix_fuel_price_series_domain", table_name="fuel_price_series")
    op.drop_table("fuel_price_series")
    op.drop_table("fuel_sync_state")
