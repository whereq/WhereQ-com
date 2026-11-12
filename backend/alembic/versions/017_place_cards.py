"""Place cards — the user's own card, a customised view of a place.

A card is deliberately **not** a row in ``places``: the map endpoint filters
on ``kind``/``category`` and never on ``source``, so a user-authored place
would become a pin for everybody and would inflate the category counts. The
card gets its own table.

The publication columns (``status``, ``publish_token``, the report counter)
are created now, so the publishing phase needs no second migration.

Revision ID: 017_place_cards
Revises: 016_reset_legacy_geocode_status
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "017_place_cards"
down_revision = "016_reset_legacy_geocode_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "place_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="business"),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address", sa.String(length=512), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("radius_km", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("categories", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("accent", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("publish_token", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_place_cards_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_place_cards"),
    )
    op.create_index("ix_place_cards_id", "place_cards", ["id"])
    op.create_index("ix_place_cards_user_id", "place_cards", ["user_id"])
    op.create_index("ix_place_cards_kind", "place_cards", ["kind"])
    op.create_index("ix_place_cards_status", "place_cards", ["status"])
    # The public identity: unique, so a token can never address two cards.
    # The name matches the model's index, so `alembic check` stays quiet.
    op.create_index(
        "ix_place_cards_publish_token", "place_cards", ["publish_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_place_cards_publish_token", table_name="place_cards")
    op.drop_index("ix_place_cards_status", table_name="place_cards")
    op.drop_index("ix_place_cards_kind", table_name="place_cards")
    op.drop_index("ix_place_cards_user_id", table_name="place_cards")
    op.drop_index("ix_place_cards_id", table_name="place_cards")
    op.drop_table("place_cards")
