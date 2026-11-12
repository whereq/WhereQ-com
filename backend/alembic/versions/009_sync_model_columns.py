"""Sync neighborhoods + stories columns with ORM models

Adds columns present in the SQLAlchemy models but never created by a migration
(model/migration drift): neighborhoods.{description,latitude,longitude,safety_score}
and stories.is_published. Adds-only; existing data preserved.

Revision ID: 009_sync_model_columns
Revises: 008_hazards
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = "009_sync_model_columns"
down_revision = "008_hazards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # neighborhoods — columns defined on the model but missing in the DB
    op.add_column("neighborhoods", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("neighborhoods", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("neighborhoods", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("neighborhoods", sa.Column("safety_score", sa.Integer(), nullable=True))
    # stories — publish flag; NOT NULL, backfill existing rows to true
    op.add_column(
        "stories",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("stories", "is_published")
    op.drop_column("neighborhoods", "safety_score")
    op.drop_column("neighborhoods", "longitude")
    op.drop_column("neighborhoods", "latitude")
    op.drop_column("neighborhoods", "description")
