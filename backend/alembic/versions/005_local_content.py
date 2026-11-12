"""Local content domain: news/events/stories/topics on the map

Revision ID: 005_local_content
Revises: 004_keycloak
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = "005_local_content"
down_revision = "004_keycloak"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # -- news_source (crawler source registry) --
    op.create_table(
        "news_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="rss"),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("homepage_url", sa.String(512)),
        sa.Column("default_type", sa.String(16), server_default="news"),
        sa.Column("default_category", sa.String(32)),
        sa.Column("default_city", sa.String(128)),
        sa.Column("default_province", sa.String(16)),
        sa.Column("default_country", sa.String(8), server_default="CA"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("crawl_interval_minutes", sa.Integer(), server_default="60"),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(16)),
        sa.Column("last_error", sa.Text()),
        sa.Column("config", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_news_source_slug"),
    )
    op.create_index("ix_news_source_slug", "news_source", ["slug"])
    op.create_index("ix_news_source_enabled", "news_source", ["enabled"])

    # -- local_content (normalized records; PostGIS POINT geom + GiST) --
    op.create_table(
        "local_content",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("news_source.id"), index=True),
        sa.Column("type", sa.String(16), nullable=False, server_default="news"),
        sa.Column("category", sa.String(32), nullable=False, server_default="other"),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("source_name", sa.String(128)),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("external_id", sa.String(255)),
        sa.Column("event_time", sa.DateTime(timezone=True)),
        sa.Column("event_end_time", sa.DateTime(timezone=True)),
        sa.Column("publish_time", sa.DateTime(timezone=True)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False)),
        sa.Column("address", sa.String(512)),
        sa.Column("city", sa.String(128)),
        sa.Column("province", sa.String(16)),
        sa.Column("country", sa.String(8)),
        sa.Column("geocode_status", sa.String(16), server_default="none"),
        sa.Column("geocode_source", sa.String(16)),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("image_url", sa.String(1024)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("dedup_key", sa.String(64)),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "external_id", name="uq_local_source_external"),
    )
    op.create_index("ix_local_content_type", "local_content", ["type"])
    op.create_index("ix_local_content_category", "local_content", ["category"])
    op.create_index("ix_local_content_status", "local_content", ["status"])
    op.create_index("ix_local_content_event_time", "local_content", ["event_time"])
    op.create_index("ix_local_content_publish_time", "local_content", ["publish_time"])
    op.create_index("ix_local_content_expires_at", "local_content", ["expires_at"])
    op.create_index("ix_local_content_source_url", "local_content", ["source_url"])
    op.create_index("ix_local_content_content_sha256", "local_content", ["content_sha256"])
    op.create_index("ix_local_content_dedup_key", "local_content", ["dedup_key"])
    op.create_index("ix_local_content_city", "local_content", ["city"])
    # Composite for the common viewport filter (status + type) before the spatial scan.
    op.create_index("ix_local_content_status_type", "local_content", ["status", "type"])
    op.execute("CREATE INDEX ix_local_content_geom ON local_content USING GIST (geom)")
    # Unique source_url only when present (user-generated content may have none).
    op.execute(
        "CREATE UNIQUE INDEX uq_local_content_source_url ON local_content (source_url) "
        "WHERE source_url IS NOT NULL"
    )

    # -- local_content_tag --
    op.create_table(
        "local_content_tag",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.BigInteger(),
                  sa.ForeignKey("local_content.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tag", sa.String(64), nullable=False),
        sa.UniqueConstraint("content_id", "tag", name="uq_local_content_tag"),
    )
    op.create_index("ix_local_content_tag_tag", "local_content_tag", ["tag"])

    # -- local_content_location (future multi-location expansion) --
    op.create_table(
        "local_content_location",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.BigInteger(),
                  sa.ForeignKey("local_content.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False)),
        sa.Column("address", sa.String(512)),
        sa.Column("label", sa.String(255)),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false")),
    )
    op.execute("CREATE INDEX ix_local_content_location_geom ON local_content_location USING GIST (geom)")

    # -- geocode_cache (avoid repeat Google Geocoding billing) --
    op.create_table(
        "geocode_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_sha256", sa.String(64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("formatted_address", sa.String(512)),
        sa.Column("confidence", sa.Float()),
        sa.Column("provider", sa.String(16), server_default="google"),
        sa.Column("hit_count", sa.Integer(), server_default="0"),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("query_sha256", name="uq_geocode_cache_query"),
    )
    op.create_index("ix_geocode_cache_query_sha256", "geocode_cache", ["query_sha256"])


def downgrade() -> None:
    op.drop_table("geocode_cache")
    op.execute("DROP INDEX IF EXISTS ix_local_content_location_geom")
    op.drop_table("local_content_location")
    op.drop_table("local_content_tag")
    op.execute("DROP INDEX IF EXISTS uq_local_content_source_url")
    op.execute("DROP INDEX IF EXISTS ix_local_content_geom")
    op.drop_table("local_content")
    op.drop_table("news_source")
