"""User settings — one row per user.

The nearby-events search (its radius and the categories the user kept) is a
per-user preference, so it belongs in the database rather than in the browser:
the choice should follow the account across devices.

The table is one row per user (``user_id`` is the primary key) and is created
lazily by the API — a user who never opens the nearby search has no row. The
foreign key cascades, so deleting a user takes their settings with it.

Revision ID: 013_user_settings
Revises: 012_content_ownership
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013_user_settings"
down_revision = "012_content_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("radius_km", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("categories", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_user_settings_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_settings"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
