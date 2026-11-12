"""Pydantic schemas for the schools read API."""

from typing import Any

from pydantic import BaseModel


class BoardOut(BaseModel):
    id: int
    slug: str
    name: str
    type: str | None = None
    region: str | None = None

    model_config = {"from_attributes": True}


class SchoolSummary(BaseModel):
    id: int
    name: str
    type: str | None = None
    province: str | None = None        # province code, e.g. "ON"
    region: str | None = None          # board.region
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    hs_score: float | None = None
    hs_rank: int | None = None
    hs_rank_total: int | None = None
    grade_range: str | None = None
    board: BoardOut | None = None
    programs: list[str] = []
    has_boundary: bool = False


class PaginatedSchools(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SchoolSummary]


class ScoreOut(BaseModel):
    year: int
    rank: int | None = None
    rank_total: int | None = None
    rank_score: float | None = None
    avg_exam_mark: float | None = None

    model_config = {"from_attributes": True}


class EqaoOut(BaseModel):
    grade: int
    year_mark: str | None = None
    rank: int | None = None
    total: int | None = None
    last5_avg: int | None = None

    model_config = {"from_attributes": True}


class SchoolDetail(SchoolSummary):
    status: str | None = None
    address: str | None = None
    municipality: str | None = None
    phone: str | None = None
    phone2: str | None = None
    fax: str | None = None
    website_url: str | None = None
    boundary_pdf_url: str | None = None
    hs_name: str | None = None
    hs_board_type: str | None = None
    hs_school_type: str | None = None
    hs_score_year: int | None = None
    hs_score_average: float | None = None
    hs_rank_year: int | None = None
    feeder_schools: Any | None = None
    scores: list[ScoreOut] = []
    eqao: list[EqaoOut] = []
    boundary_geojson: dict | None = None   # GeoJSON MultiPolygon


class MapPin(BaseModel):
    id: int
    name: str
    lat: float
    lng: float
    type: str | None = None
    board_type: str | None = None
    hs_score: float | None = None
    has_boundary: bool = False


class SchoolBoundaryOut(BaseModel):
    """The catchment outline of one school, as GeoJSON.

    A school has several polygons (a catchment can be split in two), so the
    geometry is a **MultiPolygon** — the same shape the schools app draws.
    """
    school_id: int
    name: str
    geometry: dict | None = None      # GeoJSON MultiPolygon
    polygon_count: int = 0
    point_count: int = 0


class CatchmentHit(BaseModel):
    id: int
    name: str
    type: str | None = None
    board: str | None = None
    polygon_index: int


class TaxonomyBoard(BaseModel):
    slug: str
    name: str
    type: str | None = None
    region: str | None = None
    province: str
    school_count: int


class Taxonomy(BaseModel):
    provinces: list[dict]
    regions: list[dict]
    boards: list[TaxonomyBoard]
    types: list[dict]
    board_types: list[dict]
    programs: list[dict]


class SchoolStats(BaseModel):
    total: int
    with_boundary: int
    by_province: list[dict]
    by_board_type: list[dict]
    by_type: list[dict]
