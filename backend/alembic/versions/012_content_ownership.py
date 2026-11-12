"""Ownership on user-authored content — places + neighborhoods

Adds the creator of a place and of a neighborhood so that writes can be
restricted to the author (staff may override). Routes already carried
``user_id``; the missing piece there was the enforcement, not the column.

The column is nullable and ``ON DELETE SET NULL`` on purpose: pipeline-managed
rows (OSM POIs, whereq.cloud stations) have no creator, and removing a user
must never cascade-delete the POI dataset.

Revision ID: 012_content_ownership
Revises: 011_fuel_data
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "012_content_ownership"
down_revision = "011_fuel_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("places", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_places_user_id_users", "places", "users",
        ["user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_places_user_id", "places", ["user_id"])

    op.add_column("neighborhoods", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_neighborhoods_user_id_users", "neighborhoods", "users",
        ["user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_neighborhoods_user_id", "neighborhoods", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_neighborhoods_user_id", table_name="neighborhoods")
    op.drop_constraint("fk_neighborhoods_user_id_users", "neighborhoods", type_="foreignkey")
    op.drop_column("neighborhoods", "user_id")

    op.drop_index("ix_places_user_id", table_name="places")
    op.drop_constraint("fk_places_user_id_users", "places", type_="foreignkey")
    op.drop_column("places", "user_id")
