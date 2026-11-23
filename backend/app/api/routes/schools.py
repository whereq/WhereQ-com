"""Schools read API — list/filter, detail, map pins, taxonomy, point-in-catchment.

WHERE THE ROWS COME FROM
------------------------
Three modes, switched by ``SCHOOL_READ_MODE`` — see the migration guide:

* ``local``  — this app's own ``school*`` tables. Today's behaviour.
* ``dual``   — both. The two answers are compared and the comparison is
  written down, and the **local** answer is what the caller gets. The app
  behaves exactly as it did, and the ledger fills up with the evidence.
* ``cloud``  — whereq.cloud directly. The local tables are no longer read
  here.

In ``dual`` mode an upstream failure must not fail the request: the caller
still gets the local answer, and the failed comparison is recorded as a
failure — never as a clean one. And the comparison runs **after** the
response: the window must not make the app wait on the upstream, because
that would make the app's speed and its availability depend on the very
thing the window is testing.

THE KEY IS THE UID
------------------
A school is identified by its **uid** — ``ycdsb/0158`` — the board's slug
and the school's own code, joined by a slash. It is the key whereq.cloud
and this app agree on, and it is what whereq.cloud's own routes take.

The uid carries a slash, and a slash cannot be a path parameter: the
router would see two path segments and match neither. So the routes use a
converter that is told one slash is part of the id.

The **row id** is still the join key between the two copies — the import
preserved this app's integers — but it is not an identifier, and it is not
what the API returns.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, case, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.convertors import Convertor, register_url_convertor

from app.core.config import settings
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
from app.services import cloud_parity
from app.services.cloud_school_parity import (
    AT_FIELDS,
    BOUNDARY_FIELDS,
    DETAIL_FIELDS,
    at_to_read,
    boundary_to_read,
    compare_stats,
    compare_taxonomies,
    detail_to_read,
)
from app.services.cloud_schools import (
    COMPARABLE_FIELDS,
    fetch_cloud_school,
    fetch_cloud_school_boundary,
    fetch_cloud_schools,
    fetch_cloud_schools_at,
    fetch_cloud_taxonomy,
    school_to_read,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schools", tags=["schools"])

SORT_COLUMNS = {
    "name": School.name,
    "hs_score": School.hs_score,
    "hs_rank": School.hs_rank,
    "grade_range": School.grade_range,
    "type": School.type,
    "city": School.city,
}


class _SchoolUidConvertor(Convertor):
    """A school uid: **at most** one slash.

    The uid is ``<board>/<code>`` — or ``<board>/<slug>`` — so it carries
    exactly one slash, and a slash cannot be a path parameter: the router
    would see two path segments and match neither route.

    **At most** one, not any number. ``a/b/c`` is not a uid, and letting it
    through would make a mistyped URL look like a school that does not
    exist.
    """

    regex = r"[^/]+(?:/[^/]+)?"

    def convert(self, value: str) -> str:
        return value


register_url_convertor("school_uid", _SchoolUidConvertor())


def _mode() -> str:
    """Which copy of the schools this API reads: local | dual | cloud."""
    return (settings.SCHOOL_READ_MODE or "local").strip().lower()


# ── the upstream, off the event loop ──────────────────────────────────
#
# The SDK is **synchronous**, so every upstream call is put on a thread.
# The crawler's own service calls it inline, which is fine there — one job
# at a time in a container of its own — but this is the API server, and
# blocking the event loop on an upstream round trip would stall every other
# request the server is serving.


async def _cloud_schools(**kwargs):
    import asyncio

    return await asyncio.to_thread(fetch_cloud_schools, **kwargs)


async def _cloud_school(uid: str):
    import asyncio

    return await asyncio.to_thread(fetch_cloud_school, uid=uid)


async def _cloud_school_boundary(uid: str):
    import asyncio

    return await asyncio.to_thread(fetch_cloud_school_boundary, uid=uid)


async def _cloud_schools_at(lat: float, lng: float):
    import asyncio

    return await asyncio.to_thread(fetch_cloud_schools_at, lat=lat, lng=lng)


async def _cloud_taxonomy():
    import asyncio

    return await asyncio.to_thread(fetch_cloud_taxonomy)


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
        uid=s.uid, name=s.name, type=s.type, province=s.province.code if s.province else None,
        region=s.board.region if s.board else None, city=s.city, lat=s.lat, lng=s.lng,
        hs_score=s.hs_score, hs_rank=s.hs_rank, hs_rank_total=s.hs_rank_total,
        grade_range=s.grade_range,
        board=BoardOut.model_validate(s.board) if s.board else None,
        programs=sorted(progs.get(s.id, [])), has_boundary=s.id in bnd,
    )


def _read(s: School, progs, bnd) -> dict:
    """A local school in the flat shape the comparison uses.

    The same shape ``cloud_schools.school_to_read`` produces for the
    upstream's row, so the two are comparable field by field.
    """
    board = s.board
    return {
        "uid": s.uid,
        "id": s.id,
        "name": s.name,
        "type": s.type,
        "status": s.status,
        "province": s.province.code if s.province else None,
        "region": board.region if board else None,
        "city": s.city,
        "municipality": s.municipality,
        "grade_range": s.grade_range,
        "programs": sorted(progs.get(s.id, [])),
        "has_boundary": s.id in bnd,
        "lat": s.lat,
        "lng": s.lng,
        "hs_score": s.hs_score,
        "hs_rank": s.hs_rank,
        "hs_rank_total": s.hs_rank_total,
        "hs_school_type": s.hs_school_type,
        "board_slug": board.slug if board else None,
        "board_name": board.name if board else None,
        "board_type": board.type if board else None,
        "board_region": board.region if board else None,
    }


async def _local_read_rows(db, conds) -> list[dict]:
    """Every local school matching the filters, in the comparison's shape.

    The comparison needs **whole** populations: a page of rows cannot be
    compared with a page of rows, because the two pages are not the same
    rows. So this is the same query without the limit.
    """
    rows = (await db.execute(
        _base_query(conds).options(selectinload(School.board), selectinload(School.province))
    )).scalars().all()
    progs, bnd = await _programs_and_boundaries(db, [s.id for s in rows])
    return [_read(s, progs, bnd) for s in rows]


async def _record_list_parity(
    surface: str,
    filters: dict,
    local_rows: list[dict],
) -> None:
    """Compare the local directory with the upstream's, and write it down.

    Runs after the response. A failure is recorded as a failure — never as
    a clean comparison.
    """
    from app.core.database import AsyncSessionLocal

    try:
        cloud = await _cloud_schools(limit=5000, **filters)
        # The upstream's **raw** rows, not the re-shaped summary: the
        # summary drops fields the comparison looks at, and a dropped field
        # would read as "the upstream lost it".
        cloud_rows = [school_to_read(row) for row in cloud.raw]
    except Exception as exc:  # noqa: BLE001 — a failed comparison is a fact
        logger.warning("cloud parity: %s could not be compared — %s", surface, exc)
        async with AsyncSessionLocal() as db:
            await cloud_parity.record_error(db, surface, str(exc), params=filters)
        return

    async with AsyncSessionLocal() as db:
        await cloud_parity.record(
            db, surface, local_rows, cloud_rows,
            params=filters,
            local_complete=True,
            cloud_complete=cloud.complete,
            fields=COMPARABLE_FIELDS,
        )


# ── the other surfaces ───────────────────────────────────────────────────
#
# The directory list is one surface. The app also serves a school's detail,
# its catchment outline, the catchments that cover a point and the whole
# taxonomy — and a cut that only proves the list is not a cut that is proven.
#
# Each of these runs **after** the response, like the list does: the window
# must not make the app wait on the upstream, and an upstream failure must
# not fail the request. A failed comparison is recorded as a failure — never
# as a clean one.


async def _record_detail_parity(uid: str, local: dict | None) -> None:
    """Compare one school's detail with the upstream's."""
    from app.core.database import AsyncSessionLocal

    try:
        cloud = await _cloud_school(uid)
    except Exception as exc:  # noqa: BLE001 — a failed comparison is a fact
        logger.warning("cloud parity: school_detail %s could not be compared — %s", uid, exc)
        async with AsyncSessionLocal() as db:
            await cloud_parity.record_error(db, "school_detail", str(exc), params={"uid": uid})
        return

    cloud_read = detail_to_read(cloud)
    async with AsyncSessionLocal() as db:
        await cloud_parity.record(
            db, "school_detail",
            [detail_to_read(local)] if local else [],
            [cloud_read] if cloud_read else [],
            params={"uid": uid},
            local_complete=local is not None,
            # The upstream answered with "I do not have this school" — that is
            # a whole answer, and the local copy holding it is a difference.
            cloud_complete=True,
            fields=DETAIL_FIELDS,
        )


async def _record_boundary_parity(uid: str, local: dict | None) -> None:
    """Compare one school's catchment outline with the upstream's."""
    from app.core.database import AsyncSessionLocal

    try:
        cloud = await _cloud_school_boundary(uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: school_boundary %s could not be compared — %s", uid, exc)
        async with AsyncSessionLocal() as db:
            await cloud_parity.record_error(db, "school_boundary", str(exc), params={"uid": uid})
        return

    cloud_read = boundary_to_read(cloud, uid=uid)
    async with AsyncSessionLocal() as db:
        await cloud_parity.record(
            db, "school_boundary",
            [boundary_to_read(local, uid=uid)] if local else [],
            [cloud_read] if cloud_read else [],
            params={"uid": uid},
            local_complete=local is not None,
            cloud_complete=True,
            fields=BOUNDARY_FIELDS,
        )


async def _record_at_parity(lat: float, lng: float, local: list[dict]) -> None:
    """Compare the catchments covering a point with the upstream's.

    The two sides use different containment rules on purpose: this app's own
    query uses ``ST_Contains`` and the upstream's uses ``ST_Covers``. A point
    exactly on a catchment's edge therefore belongs to the upstream's answer
    and not to this app's — a real, rare, documented difference.
    """
    from app.core.database import AsyncSessionLocal

    try:
        cloud = await _cloud_schools_at(lat, lng)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: school_at could not be compared — %s", exc)
        async with AsyncSessionLocal() as db:
            await cloud_parity.record_error(db, "school_at", str(exc),
                                            params={"lat": lat, "lng": lng})
        return

    async with AsyncSessionLocal() as db:
        await cloud_parity.record(
            db, "school_at",
            [at_to_read(hit) for hit in local],
            [at_to_read(hit) for hit in cloud],
            params={"lat": lat, "lng": lng},
            local_complete=True,
            cloud_complete=True,
            fields=AT_FIELDS,
        )


async def _record_taxonomy_parity(local: dict) -> None:
    """Compare the whole vocabulary with the upstream's."""
    from app.core.database import AsyncSessionLocal

    try:
        cloud, _stats = await _cloud_taxonomy()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: school_taxonomy could not be compared — %s", exc)
        async with AsyncSessionLocal() as db:
            await cloud_parity.record_error(db, "school_taxonomy", str(exc))
        return

    result = compare_taxonomies(local, cloud)
    async with AsyncSessionLocal() as db:
        await cloud_parity.record_result(
            db, "school_taxonomy", result,
            local_count=sum(len(local.get(group) or []) for group in
                            ("provinces", "regions", "boards", "types", "board_types", "programs")),
            cloud_count=sum(len(cloud.get(group) or []) for group in
                            ("provinces", "regions", "boards", "types", "board_types", "programs")),
            params={},
            complete=True,
        )


async def _record_stats_parity(local: dict) -> None:
    """Compare the headline counts with the upstream's."""
    from app.core.database import AsyncSessionLocal

    try:
        _tax, cloud = await _cloud_taxonomy()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud parity: school_stats could not be compared — %s", exc)
        async with AsyncSessionLocal() as db:
            await cloud_parity.record_error(db, "school_stats", str(exc))
        return

    result = compare_stats(local, cloud)
    async with AsyncSessionLocal() as db:
        await cloud_parity.record_result(
            db, "school_stats", result,
            local_count=local.get("total") or 0,
            cloud_count=cloud.get("total") or 0,
            params={},
            complete=True,
        )


@router.get("", response_model=PaginatedSchools)
async def list_schools(
    background_tasks: BackgroundTasks,
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
    """The school directory.

    The upstream's page size goes to 5 000 — the map needs a whole viewport
    in one call — but this route's own page size stays where it was: the
    app's pagination is a product decision, not a platform limit.
    """
    bb = _parse_bbox(bbox)
    conds = _filter_conditions(country, province, board, board_type, region, type, q, bb, has_boundary, program)
    mode = _mode()

    filters = {
        "q": q, "board": board, "board_type": board_type, "region": region,
        "city": None, "province": province, "type": type, "program": program,
        "bbox": bbox, "has_boundary": has_boundary, "sort": sort,
        "order": order, "rank": rank,
    }

    if mode == "cloud":
        cloud = await _cloud_schools(
            limit=page_size, offset=(page - 1) * page_size, **filters)
        items = [SchoolSummary(**row) for row in cloud.rows]
        return PaginatedSchools(total=cloud.total or len(items), page=page,
                                page_size=page_size, items=items)

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
    items = [_summary(s, progs, bnd) for s in rows]

    if mode == "dual":
        # The comparison is over the WHOLE population on both sides — a page
        # of rows cannot be compared with a page of rows, because the two
        # pages are not the same rows.
        local_rows = await _local_read_rows(db, conds)
        background_tasks.add_task(_record_list_parity, "school_list", filters, local_rows)

    return PaginatedSchools(total=total, page=page, page_size=page_size, items=items)


@router.get("/map", response_model=list[MapPin])
async def map_pins(
    background_tasks: BackgroundTasks,
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
    """The map's school pins.

    The upstream's limit goes to 5 000; the whole directory is 2 528
    schools, so one call can carry every pin there is.
    """
    bb = _parse_bbox(bbox)
    conds = _filter_conditions(country, province, board, board_type, region, type, q, bb, has_boundary, program)
    mode = _mode()
    filters = {
        "q": q, "board": board, "board_type": board_type, "region": region,
        "city": None, "province": province, "type": type, "program": program,
        "bbox": bbox, "has_boundary": has_boundary,
    }

    if mode == "cloud":
        cloud = await _cloud_schools(limit=min(limit, 5000), **filters)
        return [
            MapPin(uid=row["uid"], name=row["name"], lat=row["lat"], lng=row["lng"],
                   type=row["type"], board_type=(row["board"] or {}).get("type"),
                   hs_score=row["hs_score"], has_boundary=row["has_boundary"])
            for row in cloud.rows
            if row["lat"] is not None and row["lng"] is not None
        ]

    conds += [School.lat.is_not(None), School.lng.is_not(None)]
    bnd_sub = exists().where(and_(SchoolBoundary.school_id == School.id, SchoolBoundary.is_current.is_(True)))
    rows = (await db.execute(
        select(School.uid, School.name, School.lat, School.lng, School.type,
               SchoolBoard.type, School.hs_score, bnd_sub.label("has_boundary"))
        .select_from(School)
        .outerjoin(SchoolBoard, School.board_id == SchoolBoard.id)
        .join(Province, School.province_id == Province.id)
        .outerjoin(Country, Province.country_id == Country.id)
        .where(*conds).limit(limit))).all()
    return [MapPin(uid=r[0], name=r[1], lat=r[2], lng=r[3], type=r[4],
                   board_type=r[5], hs_score=r[6], has_boundary=bool(r[7])) for r in rows]


@router.get("/at", response_model=list[CatchmentHit])
async def schools_at_point(
    background_tasks: BackgroundTasks,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Which school catchments contain this point.

    Catchment/boundary data is gated — requires a signed-in user.

    **The upstream covers the edge.** This app's own query uses
    ``ST_Contains`` — a point exactly on a catchment's edge belongs to
    nobody — while the upstream uses ``ST_Covers``, which includes the
    edge. The upstream's rule is the correct one, so the difference is a
    real (and rare) difference: a point exactly on a boundary.
    """
    mode = _mode()
    if mode == "cloud":
        hits = await _cloud_schools_at(lat, lng)
        return [CatchmentHit(**hit) for hit in hits]

    pt = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    rows = (await db.execute(
        select(School.uid, School.name, School.type, SchoolBoard.name, SchoolBoundary.polygon_index)
        .join(SchoolBoundary, SchoolBoundary.school_id == School.id)
        .outerjoin(SchoolBoard, School.board_id == SchoolBoard.id)
        .where(SchoolBoundary.is_current.is_(True), func.ST_Contains(SchoolBoundary.geom, pt)))).all()
    hits = [CatchmentHit(uid=r[0], name=r[1], type=r[2], board=r[3], polygon_index=r[4])
            for r in rows]

    if mode == "dual":
        background_tasks.add_task(
            _record_at_parity, lat, lng,
            [{"uid": h.uid, "name": h.name, "type": h.type, "board": h.board,
              "polygon_index": h.polygon_index} for h in hits],
        )

    return hits


async def _local_taxonomy_rows(db: AsyncSession) -> dict:
    """The local vocabulary, in the shape the comparison uses.

    The same rows the route returns, as plain dictionaries — so the two sides
    can be compared group by group instead of as two pydantic objects.
    """
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
    boards = [{"slug": s, "name": n, "type": t, "region": rg, "province": pc, "school_count": cnt}
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
        .group_by(Program.code, Program.label)
        .order_by(func.count(SchoolProgram.school_id).desc()))).all()
    programs = [{"id": code, "name": label or code, "school_count": c} for code, label, c in prog]

    return {
        "provinces": provinces, "regions": regions, "boards": boards,
        "types": types, "board_types": board_types, "programs": programs,
    }


@router.get("/taxonomy", response_model=Taxonomy)
async def taxonomy(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """The whole vocabulary in one call — the provinces, the boards' regions,
    the boards, the levels, the board types and the programmes."""
    mode = _mode()
    if mode == "cloud":
        local, _stats = await _cloud_taxonomy()
        return Taxonomy(**local)

    rows = await _local_taxonomy_rows(db)

    if mode == "dual":
        background_tasks.add_task(_record_taxonomy_parity, rows)

    return Taxonomy(**rows)


@router.get("/stats", response_model=SchoolStats)
async def stats(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """The headline counts and their breakdowns."""
    mode = _mode()
    if mode == "cloud":
        _tax, cloud_stats = await _cloud_taxonomy()
        return SchoolStats(**cloud_stats)

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

    local = {"total": total, "with_boundary": with_b, "by_province": by_prov,
             "by_board_type": by_bt, "by_type": by_type}

    if mode == "dual":
        background_tasks.add_task(_record_stats_parity, local)

    return SchoolStats(**local)


def _count_points(coords) -> int:
    """How many positions a stored GeoJSON geometry holds.

    A stored row is a GeoJSON **Polygon**: ``coordinates`` is a list of rings,
    and a ring is a list of ``[lng, lat]`` positions. So the number of points
    is the sum of the ring lengths — *not* the sum of the position lengths
    (that would count every point twice and report 72 for a 36-point ring).
    """
    return sum(len(ring) for ring in coords)


@router.get("/{school_uid:school_uid}/boundary", response_model=SchoolBoundaryOut)
async def school_boundary(
    school_uid: str,
    background_tasks: BackgroundTasks,
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
    mode = _mode()
    if mode == "cloud":
        cloud = await _cloud_school_boundary(school_uid)
        if not cloud:
            raise HTTPException(status_code=404, detail="This school has no boundary")
        return SchoolBoundaryOut(
            school_uid=cloud["uid"], name=cloud["name"],
            geometry=cloud["geometry"],
            polygon_count=cloud["polygon_count"],
            point_count=cloud["point_count"],
        )

    row = (await db.execute(
        select(School.name).where(School.uid == school_uid))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="School not found")

    school_id = (await db.execute(
        select(School.id).where(School.uid == school_uid))).scalar_one()
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

    geometry = {"type": "MultiPolygon", "coordinates": polys}

    if mode == "dual":
        background_tasks.add_task(
            _record_boundary_parity, school_uid,
            {"uid": school_uid, "name": row, "geometry": geometry,
             "polygon_count": len(polys), "point_count": points},
        )

    return SchoolBoundaryOut(
        school_uid=school_uid,
        name=row,
        geometry=geometry,
        polygon_count=len(polys),
        point_count=points,
    )


@router.get("/{school_uid:school_uid}", response_model=SchoolDetail)
async def get_school(
    school_uid: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    """One school, in full."""
    mode = _mode()
    if mode == "cloud":
        cloud = await _cloud_school(school_uid)
        if not cloud:
            raise HTTPException(status_code=404, detail="School not found")
        detail = dict(cloud)
        # The catchment outline is gated: only a signed-in user gets the
        # polygons. The upstream serves them from their own endpoint.
        detail["boundary_geojson"] = None
        if user is not None:
            boundary = await _cloud_school_boundary(school_uid)
            detail["boundary_geojson"] = boundary["geometry"] if boundary else None
        return SchoolDetail(**detail)

    s = (await db.execute(
        select(School).where(School.uid == school_uid).options(
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

    detail = SchoolDetail(
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

    if mode == "dual":
        # The principal is compared too: both copies carry it, and a cut that
        # dropped it would be a cut the ledger would not have noticed.
        background_tasks.add_task(
            _record_detail_parity, school_uid,
            {**detail.model_dump(), "principal": s.principal},
        )

    return detail
