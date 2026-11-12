"""Initial schema — all models for whereq.com

Revision ID: 001_initial
Revises:
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- users --
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("username", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("locale", sa.String(8), server_default="en"),
        sa.Column("theme", sa.String(8), server_default="dark"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- places --
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text()),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address", sa.String(512)),
        sa.Column("city", sa.String(128)),
        sa.Column("country", sa.String(128)),
        sa.Column("category", sa.String(64), server_default="general"),
        sa.Column("kind", sa.String(32), server_default="poi", index=True),
        sa.Column("sub", sa.String(255)),
        sa.Column("metadata_json", postgresql.JSONB(), server_default="{}"),
        sa.Column("view_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- neighborhoods --
    op.create_table(
        "neighborhoods",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("city", sa.String(128)),
        sa.Column("country", sa.String(128)),
        sa.Column("boundary_geojson", postgresql.JSONB()),
        sa.Column("walkability_score", sa.Integer(), server_default="0"),
        sa.Column("transit_score", sa.Integer(), server_default="0"),
        sa.Column("food_score", sa.Integer(), server_default="0"),
        sa.Column("schools_score", sa.Integer(), server_default="0"),
        sa.Column("overall_score", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- routes --
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("waypoints", postgresql.JSONB(), server_default="[]"),
        sa.Column("total_distance_km", sa.Float()),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- stories --
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id", ondelete="CASCADE"), index=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), server_default="personal"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- saved_places --
    op.create_table(
        "saved_places",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id", ondelete="CASCADE"), index=True),
        sa.Column("label", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "place_id", name="uq_saved_user_place"),
    )

    # -- notifications --
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("kind", sa.String(32), server_default="info"),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- friendships --
    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("friend_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "friend_id", name="uq_friendship"),
    )

    # -- newsletter_subscribers --
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("newsletter_subscribers")
    op.drop_table("friendships")
    op.drop_table("notifications")
    op.drop_table("saved_places")
    op.drop_table("stories")
    op.drop_table("routes")
    op.drop_table("neighborhoods")
    op.drop_table("places")
    op.drop_table("users")
