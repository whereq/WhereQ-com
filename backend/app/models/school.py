"""School-domain models.

Hierarchy:  country → province → school_board (nullable) → school
Facts:      school_score (yearly), school_eqao, school_boundary (one row/polygon)
History:    crawl_snapshot (append-only raw archive) + school_version (SCD-2)

Coordinates are WGS84 (SRID 4326). Boundaries are stored twice: `geojson` (raw
fidelity) and `geom` (PostGIS, for spatial queries / GiST index).
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Provenance / raw archive (append-only) ──────────────────────────────────
class CrawlSnapshot(Base):
    """Immutable record of one fetched document version (dedup by content hash)."""

    __tablename__ = "crawl_snapshot"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_ref", "lang", "content_sha256",
                         name="uq_snapshot_entity_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)  # board|school|school_detail
    entity_ref: Mapped[str] = mapped_column(String(255), index=True)  # province/board/slug key
    province: Mapped[str | None] = mapped_column(String(8))
    board: Mapped[str | None] = mapped_column(String(128))
    slug: Mapped[str | None] = mapped_column(String(255))
    lang: Mapped[str | None] = mapped_column(String(8))            # en|cn|None
    source: Mapped[str | None] = mapped_column(String(64))         # housesigma|board_site
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(String(1024))    # archived file on disk
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Hierarchy ───────────────────────────────────────────────────────────────
class Country(Base):
    __tablename__ = "country"

    id: Mapped[int] = mapped_column(primary_key=True)
    iso2: Mapped[str] = mapped_column(String(2), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    provinces: Mapped[list["Province"]] = relationship(back_populates="country")


class Province(Base):
    __tablename__ = "province"
    __table_args__ = (UniqueConstraint("country_id", "code", name="uq_province_country_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(8), nullable=False)   # ON, AB, BC
    name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    country: Mapped["Country"] = relationship(back_populates="provinces")
    boards: Mapped[list["SchoolBoard"]] = relationship(back_populates="province")


class SchoolBoard(Base):
    __tablename__ = "school_board"
    __table_args__ = (UniqueConstraint("province_id", "slug", name="uq_board_province_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    province_id: Mapped[int] = mapped_column(ForeignKey("province.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)  # tdsb
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str | None] = mapped_column(String(16), index=True)  # public|catholic|private
    region: Mapped[str | None] = mapped_column(String(128))
    website_url: Mapped[str | None] = mapped_column(String(512))
    school_count_total: Mapped[int | None] = mapped_column(Integer)
    school_count_elementary: Mapped[int | None] = mapped_column(Integer)
    school_count_secondary: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(String(512))
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_snapshot.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    province: Mapped["Province"] = relationship(back_populates="boards")
    categories: Mapped[list["BoardCategory"]] = relationship(
        back_populates="board", cascade="all, delete-orphan")
    schools: Mapped[list["School"]] = relationship(back_populates="board")


class BoardCategory(Base):
    """A board's `categories[]` entry (type or program grouping)."""

    __tablename__ = "board_category"
    __table_args__ = (UniqueConstraint("board_id", "code", name="uq_board_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("school_board.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)        # elementary, french_immersion
    label: Mapped[str | None] = mapped_column(String(255))
    category_type: Mapped[str | None] = mapped_column(String(32))        # type|program
    description: Mapped[str | None] = mapped_column(Text)

    board: Mapped["SchoolBoard"] = relationship(back_populates="categories")


class Program(Base):
    __tablename__ = "program"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(255))


class SchoolProgram(Base):
    __tablename__ = "school_program"

    school_id: Mapped[int] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), primary_key=True)


# ── Core entity (current row; history in SchoolVersion) ─────────────────────
class School(Base):
    __tablename__ = "school"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    province_id: Mapped[int] = mapped_column(ForeignKey("province.id"), nullable=False, index=True)
    board_id: Mapped[int | None] = mapped_column(ForeignKey("school_board.id"), index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    type: Mapped[str | None] = mapped_column(String(32), index=True)  # elementary|secondary|…
    status: Mapped[str | None] = mapped_column(String(32))

    # Source/board identity
    source_id: Mapped[str | None] = mapped_column(String(64), index=True)  # board-crawl `id`
    board_name: Mapped[str | None] = mapped_column(String(255))
    school_code: Mapped[str | None] = mapped_column(String(64))

    # Contact / location
    address: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(255), index=True)
    municipality: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(64))
    phone2: Mapped[str | None] = mapped_column(String(64))
    fax: Mapped[str | None] = mapped_column(String(64))
    website_url: Mapped[str | None] = mapped_column(String(512))
    grade_range: Mapped[str | None] = mapped_column(String(255))
    boundary_pdf_url: Mapped[str | None] = mapped_column(String(512))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)

    # Board-crawl staff/extras (present on a subset)
    principal: Mapped[str | None] = mapped_column(String(255))
    vice_principal: Mapped[str | None] = mapped_column(String(255))
    superintendent: Mapped[str | None] = mapped_column(String(255))
    trustee: Mapped[str | None] = mapped_column(String(255))
    bell_times: Mapped[dict | None] = mapped_column(JSONB)

    # HouseSigma identity + latest score snapshot (denormalized for fast filters)
    hs_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)
    hs_name: Mapped[str | None] = mapped_column(String(512))
    hs_board_type: Mapped[str | None] = mapped_column(String(32))   # Public|Catholic
    hs_school_type: Mapped[str | None] = mapped_column(String(32))  # Elementary|Secondary
    hs_score: Mapped[float | None] = mapped_column(Float, index=True)
    hs_score_year: Mapped[int | None] = mapped_column(Integer)
    hs_score_average: Mapped[float | None] = mapped_column(Float)
    hs_rank: Mapped[int | None] = mapped_column(Integer, index=True)
    hs_rank_total: Mapped[int | None] = mapped_column(Integer)
    hs_rank_year: Mapped[int | None] = mapped_column(Integer)

    # Curated extras (the few hand-built schools)
    feeder_schools: Mapped[dict | None] = mapped_column(JSONB)
    extra: Mapped[dict | None] = mapped_column(JSONB)  # academic_info, directories, anything new

    # Provenance / versioning
    current_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_snapshot.id"))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    province: Mapped["Province"] = relationship()
    board: Mapped["SchoolBoard | None"] = relationship(back_populates="schools")
    scores: Mapped[list["SchoolScore"]] = relationship(
        back_populates="school", cascade="all, delete-orphan")
    eqao: Mapped[list["SchoolEqao"]] = relationship(
        back_populates="school", cascade="all, delete-orphan")
    boundaries: Mapped[list["SchoolBoundary"]] = relationship(
        back_populates="school", cascade="all, delete-orphan")
    versions: Mapped[list["SchoolVersion"]] = relationship(
        back_populates="school", cascade="all, delete-orphan")


class SchoolVersion(Base):
    """SCD-2 history: a new row whenever a school's content hash changes."""

    __tablename__ = "school_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="true", index=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_snapshot.id"))
    attrs: Mapped[dict] = mapped_column(JSONB)  # full snapshot of mutable school fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    school: Mapped["School"] = relationship(back_populates="versions")


# ── Facts / time-series ─────────────────────────────────────────────────────
class SchoolScore(Base):
    __tablename__ = "school_score"
    __table_args__ = (UniqueConstraint("school_id", "year", "source", name="uq_score_school_year"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rank: Mapped[int | None] = mapped_column(Integer)
    rank_total: Mapped[int | None] = mapped_column(Integer)
    rank_score: Mapped[float | None] = mapped_column(Float)
    avg_exam_mark: Mapped[float | None] = mapped_column(Float)
    year_label: Mapped[str | None] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32), server_default="housesigma")
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_snapshot.id"))

    school: Mapped["School"] = relationship(back_populates="scores")


class SchoolEqao(Base):
    __tablename__ = "school_eqao"
    __table_args__ = (UniqueConstraint("school_id", "grade", "year_mark", name="uq_eqao_school_grade"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)  # 3, 6, 9
    year_mark: Mapped[str | None] = mapped_column(String(16))
    rank: Mapped[int | None] = mapped_column(Integer)
    total: Mapped[int | None] = mapped_column(Integer)
    last5_avg: Mapped[int | None] = mapped_column(Integer)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_snapshot.id"))

    school: Mapped["School"] = relationship(back_populates="eqao")


class SchoolBoundary(Base):
    """One polygon per row (a school may have several = multi-campus)."""

    __tablename__ = "school_boundary"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True)
    polygon_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based in the MultiPolygon
    geojson: Mapped[dict] = mapped_column(JSONB)                          # raw GeoJSON Polygon
    geom = mapped_column(Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False))
    source: Mapped[str | None] = mapped_column(String(64))               # housesigma|extracted
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_snapshot.id"))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    school: Mapped["School"] = relationship(back_populates="boundaries")
