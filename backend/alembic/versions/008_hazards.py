"""Hazards / community reports layer

Revision ID: 008_hazards
Revises: 007_places_geo
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "008_hazards"
down_revision = "007_places_geo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "hazards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(24), nullable=False, server_default="hazard"),
        sa.Column("severity", sa.String(8), nullable=False, server_default="med"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False)),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("confirmations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(8), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hazards_type", "hazards", ["type"])
    op.create_index("ix_hazards_status", "hazards", ["status"])
    op.create_index("ix_hazards_expires_at", "hazards", ["expires_at"])
    op.create_index("ix_hazards_reporter_id", "hazards", ["reporter_id"])
    op.execute("CREATE INDEX ix_hazards_geom ON hazards USING GIST (geom)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_hazards_geom")
    op.drop_index("ix_hazards_reporter_id", table_name="hazards")
    op.drop_index("ix_hazards_expires_at", table_name="hazards")
    op.drop_index("ix_hazards_status", table_name="hazards")
    op.drop_index("ix_hazards_type", table_name="hazards")
    op.drop_table("hazards")
