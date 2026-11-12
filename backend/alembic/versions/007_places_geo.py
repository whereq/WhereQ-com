"""Places: PostGIS geom + crawl provenance (source/external_id)

Adds a PostGIS POINT geometry (GiST-indexed) for viewport queries and
source/external_id columns for idempotent POI crawls (e.g. OpenStreetMap).
Backfills geom from existing latitude/longitude.

Revision ID: 007_places_geo
Revises: 006_geocode_usage
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "007_places_geo"
down_revision = "006_geocode_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.add_column("places", sa.Column("source", sa.String(16), server_default="manual", nullable=False))
    op.add_column("places", sa.Column("external_id", sa.String(64), nullable=True))
    op.add_column("places", sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False)))

    # Backfill geom for existing rows from lat/lng.
    op.execute("UPDATE places SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
               "WHERE geom IS NULL AND longitude IS NOT NULL AND latitude IS NOT NULL")

    op.create_index("ix_places_source", "places", ["source"])
    op.create_index("ix_places_external_id", "places", ["external_id"])
    op.execute("CREATE INDEX ix_places_geom ON places USING GIST (geom)")
    # One row per crawled feature; lets us upsert by provenance.
    op.execute("CREATE UNIQUE INDEX uq_places_source_external "
               "ON places (source, external_id) WHERE external_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_places_source_external")
    op.execute("DROP INDEX IF EXISTS ix_places_geom")
    op.drop_index("ix_places_external_id", table_name="places")
    op.drop_index("ix_places_source", table_name="places")
    op.drop_column("places", "geom")
    op.drop_column("places", "external_id")
    op.drop_column("places", "source")
