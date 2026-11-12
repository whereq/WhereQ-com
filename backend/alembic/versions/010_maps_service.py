"""WhereQ Maps service — API consumers, usage accounting, route cache

Revision ID: 010_maps_service
Revises: 009_sync_model_columns
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010_maps_service"
down_revision = "009_sync_model_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A keyed consumer app (e.g. a consumer app). Only the sha256 hash of the key is
    # stored; the plaintext is shown once at mint time and never persisted.
    op.create_table(
        "maps_api_consumer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False,
                  server_default="{}"),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("monthly_quota", sa.Integer(), nullable=False, server_default="50000"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("uq_maps_consumer_key_hash", "maps_api_consumer", ["key_hash"], unique=True)
    op.create_index("ix_maps_consumer_key_prefix", "maps_api_consumer", ["key_prefix"])

    # Per-consumer, per-day, per-endpoint, per-provider counters (quota +
    # observability + cost attribution). Upserted on each request.
    op.create_table(
        "maps_api_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("consumer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("maps_api_consumer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("consumer_id", "day", "endpoint", "provider",
                            name="uq_maps_usage"),
    )
    op.create_index("ix_maps_usage_consumer_day", "maps_api_usage", ["consumer_id", "day"])

    # Short-term cache for /route (+/matrix later). ToS: routing results may be
    # cached only short-term — a TTL is enforced on read (see route_cache logic).
    op.create_table(
        "route_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("duration_in_traffic_s", sa.Integer(), nullable=True),
        sa.Column("polyline", sa.Text(), nullable=True),
        sa.Column("bounds", postgresql.JSONB(), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False, server_default="google"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("route_cache")
    op.drop_index("ix_maps_usage_consumer_day", table_name="maps_api_usage")
    op.drop_table("maps_api_usage")
    op.drop_index("ix_maps_consumer_key_prefix", table_name="maps_api_consumer")
    op.drop_index("uq_maps_consumer_key_hash", table_name="maps_api_consumer")
    op.drop_table("maps_api_consumer")
