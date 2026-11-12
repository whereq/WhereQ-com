"""Schools domain — hierarchy, facts, boundaries (PostGIS), provenance + history

Revision ID: 002_schools
Revises: 001_initial
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = "002_schools"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # -- crawl_snapshot (referenced by snapshot_id everywhere; create first) --
    op.create_table(
        "crawl_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("entity_type", sa.String(32), index=True),
        sa.Column("entity_ref", sa.String(255), index=True),
        sa.Column("province", sa.String(8)),
        sa.Column("board", sa.String(128)),
        sa.Column("slug", sa.String(255)),
        sa.Column("lang", sa.String(8)),
        sa.Column("source", sa.String(64)),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, index=True),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("entity_type", "entity_ref", "lang", "content_sha256",
                            name="uq_snapshot_entity_hash"),
    )

    # -- country --
    op.create_table(
        "country",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iso2", sa.String(2), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- province --
    op.create_table(
        "province",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("country.id"), nullable=False, index=True),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("name", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("country_id", "code", name="uq_province_country_code"),
    )

    # -- school_board --
    op.create_table(
        "school_board",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("province_id", sa.Integer(), sa.ForeignKey("province.id"), nullable=False, index=True),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(64)),
        sa.Column("type", sa.String(16), index=True),
        sa.Column("region", sa.String(128)),
        sa.Column("website_url", sa.String(512)),
        sa.Column("school_count_total", sa.Integer()),
        sa.Column("school_count_elementary", sa.Integer()),
        sa.Column("school_count_secondary", sa.Integer()),
        sa.Column("source_url", sa.String(512)),
        sa.Column("crawled_at", sa.DateTime(timezone=True)),
        sa.Column("current_snapshot_id", sa.BigInteger(), sa.ForeignKey("crawl_snapshot.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("province_id", "slug", name="uq_board_province_slug"),
    )

    # -- board_category --
    op.create_table(
        "board_category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("school_board.id"), nullable=False, index=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255)),
        sa.Column("category_type", sa.String(32)),
        sa.Column("description", sa.Text()),
        sa.UniqueConstraint("board_id", "code", name="uq_board_category"),
    )

    # -- program --
    op.create_table(
        "program",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("label", sa.String(255)),
    )

    # -- school --
    op.create_table(
        "school",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("province_id", sa.Integer(), sa.ForeignKey("province.id"), nullable=False, index=True),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("school_board.id"), index=True),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("name", sa.String(512), nullable=False, index=True),
        sa.Column("type", sa.String(32), index=True),
        sa.Column("status", sa.String(32)),
        sa.Column("source_id", sa.String(64), index=True),
        sa.Column("board_name", sa.String(255)),
        sa.Column("school_code", sa.String(64)),
        sa.Column("address", sa.String(512)),
        sa.Column("city", sa.String(255), index=True),
        sa.Column("municipality", sa.String(255)),
        sa.Column("region", sa.String(128)),
        sa.Column("phone", sa.String(64)),
        sa.Column("phone2", sa.String(64)),
        sa.Column("fax", sa.String(64)),
        sa.Column("website_url", sa.String(512)),
        sa.Column("grade_range", sa.String(64)),
        sa.Column("boundary_pdf_url", sa.String(512)),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.Column("principal", sa.String(255)),
        sa.Column("vice_principal", sa.String(255)),
        sa.Column("superintendent", sa.String(255)),
        sa.Column("trustee", sa.String(255)),
        sa.Column("bell_times", postgresql.JSONB()),
        sa.Column("hs_id", sa.Integer(), unique=True, index=True),
        sa.Column("hs_name", sa.String(512)),
        sa.Column("hs_board_type", sa.String(32)),
        sa.Column("hs_school_type", sa.String(32)),
        sa.Column("hs_score", sa.Float(), index=True),
        sa.Column("hs_score_year", sa.Integer()),
        sa.Column("hs_score_average", sa.Float()),
        sa.Column("hs_rank", sa.Integer(), index=True),
        sa.Column("hs_rank_total", sa.Integer()),
        sa.Column("hs_rank_year", sa.Integer()),
        sa.Column("feeder_schools", postgresql.JSONB()),
        sa.Column("extra", postgresql.JSONB()),
        sa.Column("current_snapshot_id", sa.BigInteger(), sa.ForeignKey("crawl_snapshot.id")),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Unique school within (province, board, slug); board_id NULL collapses to -1
    op.execute(
        "CREATE UNIQUE INDEX uq_school_prov_board_slug "
        "ON school (province_id, COALESCE(board_id, -1), slug)"
    )

    # -- school_program (M:N) --
    op.create_table(
        "school_program",
        sa.Column("school_id", sa.BigInteger(),
                  sa.ForeignKey("school.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("program_id", sa.Integer(),
                  sa.ForeignKey("program.id", ondelete="CASCADE"), primary_key=True),
    )

    # -- school_version (SCD-2) --
    op.create_table(
        "school_version",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("school_id", sa.BigInteger(),
                  sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), index=True),
        sa.Column("content_sha256", sa.String(64), index=True),
        sa.Column("snapshot_id", sa.BigInteger(), sa.ForeignKey("crawl_snapshot.id")),
        sa.Column("attrs", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- school_score (yearly time-series) --
    op.create_table(
        "school_score",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("school_id", sa.BigInteger(),
                  sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        sa.Column("rank", sa.Integer()),
        sa.Column("rank_total", sa.Integer()),
        sa.Column("rank_score", sa.Float()),
        sa.Column("avg_exam_mark", sa.Float()),
        sa.Column("year_label", sa.String(16)),
        sa.Column("source", sa.String(32), server_default="housesigma"),
        sa.Column("snapshot_id", sa.BigInteger(), sa.ForeignKey("crawl_snapshot.id")),
        sa.UniqueConstraint("school_id", "year", "source", name="uq_score_school_year"),
    )

    # -- school_eqao --
    op.create_table(
        "school_eqao",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("school_id", sa.BigInteger(),
                  sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("year_mark", sa.String(16)),
        sa.Column("rank", sa.Integer()),
        sa.Column("total", sa.Integer()),
        sa.Column("last5_avg", sa.Integer()),
        sa.Column("snapshot_id", sa.BigInteger(), sa.ForeignKey("crawl_snapshot.id")),
        sa.UniqueConstraint("school_id", "grade", "year_mark", name="uq_eqao_school_grade"),
    )

    # -- school_boundary (one polygon per row; PostGIS geom + GiST) --
    op.create_table(
        "school_boundary",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("school_id", sa.BigInteger(),
                  sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("polygon_index", sa.Integer(), nullable=False),
        sa.Column("geojson", postgresql.JSONB()),
        sa.Column("geom", Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False)),
        sa.Column("source", sa.String(64)),
        sa.Column("snapshot_id", sa.BigInteger(), sa.ForeignKey("crawl_snapshot.id")),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("CREATE INDEX ix_school_boundary_geom ON school_boundary USING GIST (geom)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_school_boundary_geom")
    op.drop_table("school_boundary")
    op.drop_table("school_eqao")
    op.drop_table("school_score")
    op.drop_table("school_version")
    op.drop_table("school_program")
    op.execute("DROP INDEX IF EXISTS uq_school_prov_board_slug")
    op.drop_table("school")
    op.drop_table("program")
    op.drop_table("board_category")
    op.drop_table("school_board")
    op.drop_table("province")
    op.drop_table("country")
    op.drop_table("crawl_snapshot")
