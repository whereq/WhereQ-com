"""Administrative geography — the places that contain the places.

The whereq.cloud geography feed: provinces, regions, municipalities, cities,
towns, wards and neighbourhoods, with their real outlines and the licence
each row owes its source.

Three tables:

- ``geo_places``    — the places themselves. ``uid`` is the feed's own id and
  the upsert identity. The outline is stored twice, like the school
  catchments: ``boundary_geojson`` (JSONB, what the API serves) and ``geom``
  (PostGIS, for the viewport and point-in-polygon queries).
- ``geo_concepts``  — the vocabulary: one row per kind of place, with the
  feed's bilingual name and description.
- ``geo_sync_state`` — one row per coverage target, so the crawler can rotate
  targets round-robin instead of re-pulling everything on every tick.

Revision ID: 018_geo_places
Revises: 017_place_cards
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = "018_geo_places"
down_revision = "017_place_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_places",
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("kind_source", sa.String(length=24), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("name_zh", sa.String(length=255), nullable=True),
        sa.Column("name_local", sa.String(length=255), nullable=True),
        sa.Column("official_name", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.String(length=96), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("license", sa.String(length=160), nullable=True),
        sa.Column("raw_admin_level", sa.Integer(), nullable=True),
        sa.Column("raw_place", sa.String(length=48), nullable=True),
        sa.Column("raw_boundary", sa.String(length=48), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("province_code", sa.String(length=8), nullable=True),
        sa.Column("iso_code", sa.String(length=16), nullable=True),
        sa.Column("ref", sa.String(length=48), nullable=True),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("population_date", sa.String(length=16), nullable=True),
        sa.Column("wikidata", sa.String(length=32), nullable=True),
        sa.Column("wikipedia", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("capital", sa.String(length=160), nullable=True),
        sa.Column("centroid_lon", sa.Float(), nullable=True),
        sa.Column("centroid_lat", sa.Float(), nullable=True),
        sa.Column("bbox_min_lon", sa.Float(), nullable=True),
        sa.Column("bbox_min_lat", sa.Float(), nullable=True),
        sa.Column("bbox_max_lon", sa.Float(), nullable=True),
        sa.Column("bbox_max_lat", sa.Float(), nullable=True),
        sa.Column("area_km2", sa.Float(), nullable=True),
        sa.Column("has_boundary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("boundary_geojson", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "geom",
            Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("uid", name="pk_geo_places"),
    )

    op.create_index("ix_geo_places_kind", "geo_places", ["kind"])
    op.create_index("ix_geo_places_name", "geo_places", ["name"])
    op.create_index("ix_geo_places_source", "geo_places", ["source"])
    op.create_index("ix_geo_places_country_code", "geo_places", ["country_code"])
    op.create_index("ix_geo_places_has_boundary", "geo_places", ["has_boundary"])
    # GiST for the viewport and point-in-polygon queries.
    op.execute("CREATE INDEX ix_geo_places_geom ON geo_places USING GIST (geom)")

    op.create_table(
        "geo_concepts",
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("name_cn", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_cn", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), server_default="0", nullable=False),
        sa.Column("upstream_places", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("kind", name="pk_geo_concepts"),
    )

    op.create_table(
        "geo_sync_state",
        sa.Column("target_key", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("bbox", sa.String(length=128), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("place_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("boundary_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("target_key", name="pk_geo_sync_state"),
    )


def downgrade() -> None:
    op.drop_table("geo_sync_state")
    op.drop_table("geo_concepts")
    op.execute("DROP INDEX IF EXISTS ix_geo_places_geom")
    op.drop_index("ix_geo_places_has_boundary", table_name="geo_places")
    op.drop_index("ix_geo_places_country_code", table_name="geo_places")
    op.drop_index("ix_geo_places_source", table_name="geo_places")
    op.drop_index("ix_geo_places_name", table_name="geo_places")
    op.drop_index("ix_geo_places_kind", table_name="geo_places")
    op.drop_table("geo_places")
