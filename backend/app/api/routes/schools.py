"""Schools read API — list/filter, detail, map pins, taxonomy, point-in-catchment."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user, get_optional_user
from app.models.school import (
    Country, Program, Province, School, SchoolBoard, SchoolBoundary,
    SchoolProgram,
)
from app.schemas.school import (
    BoardOut, CatchmentHit, EqaoOut, MapPin, PaginatedSchools, ScoreOut,
    SchoolBoundaryOut, SchoolDetail, SchoolStats, SchoolSummary, Taxonomy,
    TaxonomyBoard,
)

router = APIRouter(prefix="/schools", tags=["schools"])

SORT_COLUMNS = {
    "name": School.name,
    "hs_score": School.hs_score,
    "hs_rank": School.hs_rank,
    "grade_range": School.grade_range,
    "type": School.type,
    "city": School.city,
}


def _parse_bbox(bbox: str | None):
    """bbox = 'minLng,minLat,maxLng,maxLat' → (minLng,minLat,maxLng,maxLat) or None."""
    if not bbox:
        return None
    try:
        a, b, c, d = (float(x) for x in bbox.split(","))
        return a, b, c, d
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'")


def _filter_conditions(country, province, board, board_type, region, type, q, bbox, has_boundary, program):
    """Build (conditions, needs_country_join, needs_program) for the school query."""
    conds = []
    if province:
        conds.append(Province.code == province.upper())
    if country:
        conds.append(Country.iso2 == country.upper())
    if board:
        conds.append(SchoolBoard.slug == board)
    if board_type:
        conds.append(SchoolBoard.type == board_type)
    if region:
        conds.append(SchoolBoard.region.ilike(f"%{region}%"))
    if type:
        conds.append(School.type == type)
    if q:
        conds.append(School.name.ilike(f"%{q}%"))
    if has_boundary is not None:
        sub = exists().where(and_(SchoolBoundary.school_id == School.id, SchoolBoundary.is_current.is_(True)))
        conds.append(sub if has_boundary else ~sub)
    if program:
        conds.append(exists().where(and_(
            SchoolProgram.school_id == School.id,
            SchoolProgram.program_id == Program.id,
            Program.code == program)))
    if bbox:
        mnlng, mnlat, mxlng, mxlat = bbox
        conds.append(and_(School.lat >= mnlat, School.lat <= mxlat,
                          School.lng >= mnlng, School.lng <= mxlng))
    return conds


def _base_query(conds):
    """School query with the joins the filters reference."""
    return (select(School)
            .outerjoin(SchoolBoard, School.board_id == SchoolBoard.id)
            .join(Province, School.province_id == Province.id)
            .outerjoin(Country, Province.country_id == Country.id)
            .where(*conds))


async def _programs_and_boundaries(db, ids):
    """Return ({school_id: [program_code]}, {school_id with boundary})."""
    if not ids:
        return {}, set()
    prog_rows = (await db.execute(
        select(SchoolProgram.school_id, Program.code)
        .join(Program, SchoolProgram.program_id == Program.id)
        .where(SchoolProgram.school_id.in_(ids)))).all()
    progs: dict[int, list[str]] = {}
    for sid, code in prog_rows:
        progs.setdefault(sid, []).append(code)
    bnd = set((await db.execute(
        select(distinct(SchoolBoundary.school_id))
        .where(SchoolBoundary.school_id.in_(ids), SchoolBoundary.is_current.is_(True)))).scalars().all())
    return progs, bnd


def _summary(s: School, progs, bnd) -> SchoolSummary:
    return SchoolSummary(
        id=s.id, name=s.name, type=s.type, province=s.province.code if s.province else None,
        region=s.board.region if s.board else None, city=s.city, lat=s.lat, lng=s.lng,
        hs_score=s.hs_score, hs_rank=s.hs_rank, hs_rank_total=s.hs_rank_total,
        grade_range=s.grade_range,
        board=BoardOut.model_validate(s.board) if s.board else None,
        programs=progs.get(s.id, []), has_boundary=s.id in bnd,
    )


@router.get("", response_model=PaginatedSchools)
async def list_schools(
    country: str | None = None,
    province: str | None = None,
    board: str | None = None,
    board_type: str | None = None,
    region: str | None = None,
    type: str | None = None,
    program: str | None = None,
    q: str | None = None,
    bbox: str | None = None,
    has_boundary: bool | None = None,
    sort: str = Query("name"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    rank: bool = Query(False, description="Order name matches by relevance (for search suggestions)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    bb = _parse_bbox(bbox)
    conds = _filter_conditions(country, province, board, board_type, region, type, q, bb, has_boundary, program)

    total = (await db.execute(
        select(func.count()).select_from(_base_query(conds).subquery()))).scalar_one()

    if rank and q:
        # Relevance ranking for typeahead: exact name, then prefix, then a
        # word starting with the query, then any substring — alphabetical within
        # each tier. Surfaces e.g. "St. Robert CHS" for "robert" regardless of
        # its alphabetical position.
        relevance = case(
            (School.name.ilike(q), 0),
            (School.name.ilike(f"{q}%"), 1),
            (School.name.ilike(f"% {q}%"), 2),
            else_=3,
        )
        order_by = [relevance, School.name.asc().nullslast(), School.id]
    else:
        col = SORT_COLUMNS.get(sort, School.name)
        col = col.desc().nullslast() if order == "desc" else col.asc().nullslast()
        order_by = [col, School.id]

    rows = (await db.execute(
        _base_query(conds).options(selectinload(School.board), selectinload(School.province))
        .order_by(*order_by)
        .offset((page - 1) * page_size).limit(page_size))).scalars().all()

    progs, bnd = await _programs_and_boundaries(db, [s.id for s in rows])
    return PaginatedSchools(total=total, page=page, page_size=page_size,
                            items=[_summary(s, progs, bnd) for s in rows])


@router.get("/map", response_model=list[MapPin])
async def map_pins(
    country: str | None = None,
    province: str | None = None,
    board: str | None = None,
    board_type: str | None = None,
    region: str | None = None,
    type: str | None = None,
    program: str | None = None,
    q: str | None = None,
    bbox: str | None = None,
    has_boundary: bool | None = None,
    limit: int = Query(3000, ge=1, le=8000),
    db: AsyncSession = Depends(get_db),
):
    bb = _parse_bbox(bbox)
    conds = _filter_conditions(country, province, board, board_type, region, type, q, bb, has_boundary, program)
    conds += [School.lat.is_not(None), School.lng.is_not(None)]
    bnd_sub = exists().where(and_(SchoolBoundary.school_id == School.id, SchoolBoundary.is_current.is_(True)))
    rows = (await db.execute(
        select(School.id, School.name, School.lat, School.lng, School.type,
               SchoolBoard.type, School.hs_score, bnd_sub.label("has_boundary"))
        .select_from(School)
        .outerjoin(SchoolBoard, School.board_id == SchoolBoard.id)
        .join(Province, School.province_id == Province.id)
        .outerjoin(Country, Province.country_id == Country.id)
        .where(*conds).limit(limit))).all()
    return [MapPin(id=r[0], name=r[1], lat=r[2], lng=r[3], type=r[4],
                   board_type=r[5], hs_score=r[6], has_boundary=bool(r[7])) for r in rows]


@router.get("/at", response_model=list[CatchmentHit])
async def schools_at_point(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Which school catchments contain this point (PostGIS ST_Contains).

    Catchment/boundary data is gated — requires a signed-in user.
    """
    pt = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    rows = (await db.execute(
        select(School.id, School.name, School.type, SchoolBoard.name, SchoolBoundary.polygon_index)
        .join(SchoolBoundary, SchoolBoundary.school_id == School.id)
        .outerjoin(SchoolBoard, School.board_id == SchoolBoard.id)
        .where(SchoolBoundary.is_current.is_(True), func.ST_Contains(SchoolBoundary.geom, pt)))).all()
    return [CatchmentHit(id=r[0], name=r[1], type=r[2], board=r[3], polygon_index=r[4]) for r in rows]


@router.get("/taxonomy", response_model=Taxonomy)
async def taxonomy(db: AsyncSession = Depends(get_db)):
    prov = (await db.execute(
        select(Province.code, Province.name, func.count(School.id))
        .join(School, School.province_id == Province.id)
        .group_by(Province.code, Province.name).order_by(Province.code))).all()
    provinces = [{"id": c, "name": n, "school_count": cnt, "enabled": True} for c, n, cnt in prov]

    reg = (await db.execute(
        select(Province.code, SchoolBoard.region, func.count(School.id))
        .join(SchoolBoard, SchoolBoard.province_id == Province.id)
        .join(School, School.board_id == SchoolBoard.id)
        .where(SchoolBoard.region.is_not(None))
        .group_by(Province.code, SchoolBoard.region).order_by(SchoolBoard.region))).all()
    regions = [{"id": rg, "name": rg, "province": pc, "school_count": cnt} for pc, rg, cnt in reg]

    brd = (await db.execute(
        select(SchoolBoard.slug, SchoolBoard.name, SchoolBoard.type, SchoolBoard.region,
               Province.code, func.count(School.id))
        .join(Province, SchoolBoard.province_id == Province.id)
        .outerjoin(School, School.board_id == SchoolBoard.id)
        .group_by(SchoolBoard.slug, SchoolBoard.name, SchoolBoard.type, SchoolBoard.region, Province.code)
        .order_by(SchoolBoard.name))).all()
    boards = [TaxonomyBoard(slug=s, name=n, type=t, region=rg, province=pc, school_count=cnt)
              for s, n, t, rg, pc, cnt in brd]

    typ = (await db.execute(
        select(School.type, func.count()).where(School.type.is_not(None))
        .group_by(School.type).order_by(School.type))).all()
    types = [{"id": t, "name": t.title(), "school_count": c} for t, c in typ]

    bt = (await db.execute(
        select(SchoolBoard.type, func.count(School.id))
        .join(School, School.board_id == SchoolBoard.id)
        .where(SchoolBoard.type.is_not(None))
        .group_by(SchoolBoard.type).order_by(SchoolBoard.type))).all()
    board_types = [{"id": t, "name": t.title(), "school_count": c} for t, c in bt]

    prog = (await db.execute(
        select(Program.code, Program.label, func.count(SchoolProgram.school_id))
        .join(SchoolProgram, SchoolProgram.program_id == Program.id)
        .group_by(Program.code, Program.label).order_by(func.count(SchoolProgram.school_id).desc()))).all()
    programs = [{"id": code, "name": label or code, "school_count": c} for code, label, c in prog]

    return Taxonomy(provinces=provinces, regions=regions, boards=boards,
                    types=types, board_types=board_types, programs=programs)


@router.get("/stats", response_model=SchoolStats)
async def stats(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(School))).scalar_one()
    with_b = (await db.execute(
        select(func.count(distinct(SchoolBoundary.school_id)))
        .where(SchoolBoundary.is_current.is_(True)))).scalar_one()
    by_prov = [{"id": c, "count": n} for c, n in (await db.execute(
        select(Province.code, func.count(School.id)).join(School, School.province_id == Province.id)
        .group_by(Province.code).order_by(Province.code))).all()]
    by_bt = [{"id": t, "count": n} for t, n in (await db.execute(
        select(SchoolBoard.type, func.count(School.id)).join(School, School.board_id == SchoolBoard.id)
        .where(SchoolBoard.type.is_not(None)).group_by(SchoolBoard.type))).all()]
    by_type = [{"id": t, "count": n} for t, n in (await db.execute(
        select(School.type, func.count()).where(School.type.is_not(None)).group_by(School.type))).all()]
    return SchoolStats(total=total, with_boundary=with_b, by_province=by_prov,
                       by_board_type=by_bt, by_type=by_type)


def _count_points(coords) -> int:
    """How many positions a stored GeoJSON geometry holds.

    A stored row is a GeoJSON **Polygon**: ``coordinates`` is a list of rings,
    and a ring is a list of ``[lng, lat]`` positions. So the number of points
    is the sum of the ring lengths — *not* the sum of the position lengths
    (that would count every point twice and report 72 for a 36-point ring).
    """
    return sum(len(ring) for ring in coords)


@router.get("/{school_id}/boundary", response_model=SchoolBoundaryOut)
async def school_boundary(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """The catchment outline of one school, as GeoJSON.

    The map needs the shape of a school, not its whole record: when the user
    picks a school, the outline is drawn and the map is fitted to it. So the
    boundary is its own endpoint — one small payload instead of the detail
    document with the scores, the EQAO table and the feeder list.

    **Gated like the rest of the boundary data** (see ``GET /schools/at``):
    the catchment polygons are the licensed board data, so a signed-in user is
    required. A school without a boundary answers 404 — "there is no outline
    for this one" — not an empty geometry the caller has to guess about.
    """
    row = (await db.execute(
        select(School.name).where(School.id == school_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="School not found")

    rows = (await db.execute(
        select(SchoolBoundary.geojson)
        .where(SchoolBoundary.school_id == school_id, SchoolBoundary.is_current.is_(True))
        .order_by(SchoolBoundary.polygon_index))).scalars().all()

    polys = []
    points = 0
    for g in rows:
        if not g or not g.get("coordinates"):
            continue
        coords = g["coordinates"]
        polys.append(coords)
        points += _count_points(coords)

    if not polys:
        raise HTTPException(status_code=404, detail="This school has no boundary")

    return SchoolBoundaryOut(
        school_id=school_id,
        name=row,
        geometry={"type": "MultiPolygon", "coordinates": polys},
        polygon_count=len(polys),
        point_count=points,
    )


@router.get("/{school_id}", response_model=SchoolDetail)
async def get_school(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    s = (await db.execute(
        select(School).where(School.id == school_id).options(
            selectinload(School.board), selectinload(School.province),
            selectinload(School.scores), selectinload(School.eqao),
            selectinload(School.boundaries)))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="School not found")

    progs, bnd = await _programs_and_boundaries(db, [s.id])
    base = _summary(s, progs, bnd)

    # Boundary geometry is gated: only expose the polygons to a signed-in user.
    # Anonymous callers still get all the other school detail (has_boundary tells
    # the UI a boundary exists so it can prompt sign-in).
    boundary_geojson = None
    if user is not None:
        polys = [b.geojson["coordinates"] for b in sorted(s.boundaries, key=lambda b: b.polygon_index)
                 if b.is_current and b.geojson and b.geojson.get("coordinates")]
        boundary_geojson = {"type": "MultiPolygon", "coordinates": polys} if polys else None

    return SchoolDetail(
        **base.model_dump(),
        status=s.status, address=s.address, municipality=s.municipality,
        phone=s.phone, phone2=s.phone2, fax=s.fax, website_url=s.website_url,
        boundary_pdf_url=s.boundary_pdf_url, hs_name=s.hs_name,
        hs_board_type=s.hs_board_type, hs_school_type=s.hs_school_type,
        hs_score_year=s.hs_score_year, hs_score_average=s.hs_score_average,
        hs_rank_year=s.hs_rank_year, feeder_schools=s.feeder_schools,
        scores=[ScoreOut.model_validate(x) for x in sorted(s.scores, key=lambda x: x.year)],
        eqao=[EqaoOut.model_validate(x) for x in sorted(s.eqao, key=lambda x: x.grade)],
        boundary_geojson=boundary_geojson,
    )
