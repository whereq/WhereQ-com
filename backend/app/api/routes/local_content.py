"""Local-content read API — map (viewport) query, detail, taxonomy.

Public (anonymous browsing). Viewport queries use the PostGIS GiST index on
``local_content.geom`` via ST_Intersects(geom, ST_MakeEnvelope(...)).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.local_content import LocalContent, NewsSource
from app.schemas.local_content import (
    LocalContentDetail, LocalPin, LocalSearchItem, LocalSearchResponse,
    LocalTaxonomy, SourceItem, TaxItem,
)

router = APIRouter(prefix="/local", tags=["local"])

MAP_CAP = 2000
CATEGORY_LABELS = {
    "accident": "Accident", "crime": "Crime", "fire": "Fire", "weather": "Weather",
    "transportation": "Transportation", "construction": "Construction",
    "festival": "Festival", "event": "Event", "business": "Business",
    "education": "Education", "government": "Government", "community": "Community",
    "health": "Health", "other": "Other",
}
TYPE_LABELS = {"news": "News", "event": "Events", "story": "Stories", "topic": "Topics"}


def _parse_bbox(bbox: str | None):
    if not bbox:
        return None
    try:
        a, b, c, d = (float(x) for x in bbox.split(","))
        return a, b, c, d
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'")


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",")] if value else []


def _common_filters(types, categories, sources, date_from, date_to, q):
    """Shared WHERE conditions for active, on-map content."""
    conds = [LocalContent.status == "active", LocalContent.geom.is_not(None)]
    tl, cl, sl = _csv(types), _csv(categories), _csv(sources)
    if tl:
        conds.append(LocalContent.type.in_(tl))
    if cl:
        conds.append(LocalContent.category.in_(cl))
    if sl:
        conds.append(NewsSource.slug.in_(sl))
    if date_from:
        conds.append(LocalContent.publish_time >= date_from)
    if date_to:
        conds.append(LocalContent.publish_time <= date_to)
    if q:
        conds.append(LocalContent.title.ilike(f"%{q}%"))
    return conds, bool(sl)


@router.get("/map", response_model=list[LocalPin])
async def local_map(
    bbox: str | None = None,
    types: str | None = Query(None, description="comma-separated: news,event,story,topic"),
    categories: str | None = Query(None, description="comma-separated category codes"),
    sources: str | None = Query(None, description="comma-separated source slugs"),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    q: str | None = None,
    limit: int = Query(MAP_CAP, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    conds, needs_source_join = _common_filters(types, categories, sources, date_from, date_to, q)
    bb = _parse_bbox(bbox)
    if bb:
        mnlng, mnlat, mxlng, mxlat = bb
        conds.append(func.ST_Intersects(
            LocalContent.geom, func.ST_MakeEnvelope(mnlng, mnlat, mxlng, mxlat, 4326)))

    stmt = select(
        LocalContent.id, LocalContent.type, LocalContent.category,
        LocalContent.latitude, LocalContent.longitude, LocalContent.title,
        LocalContent.source_name, LocalContent.event_time, LocalContent.publish_time,
        LocalContent.image_url,
    )
    if needs_source_join:
        stmt = stmt.join(NewsSource, LocalContent.source_id == NewsSource.id)
    stmt = stmt.where(*conds).order_by(LocalContent.publish_time.desc().nullslast()).limit(limit)

    rows = (await db.execute(stmt)).all()
    return [LocalPin(id=r[0], type=r[1], category=r[2], lat=r[3], lng=r[4], title=r[5],
                     source_name=r[6], event_time=r[7], publish_time=r[8], image_url=r[9])
            for r in rows]


@router.get("/taxonomy", response_model=LocalTaxonomy)
async def local_taxonomy(db: AsyncSession = Depends(get_db)):
    """Counts by type/category/source for the filter panel (active content only)."""
    base = (LocalContent.status == "active", LocalContent.geom.is_not(None))

    type_rows = (await db.execute(
        select(LocalContent.type, func.count()).where(*base)
        .group_by(LocalContent.type))).all()
    cat_rows = (await db.execute(
        select(LocalContent.category, func.count()).where(*base)
        .group_by(LocalContent.category))).all()
    src_rows = (await db.execute(
        select(NewsSource.id, NewsSource.slug, NewsSource.name, func.count(LocalContent.id))
        .join(LocalContent, LocalContent.source_id == NewsSource.id)
        .where(*base)
        .group_by(NewsSource.id, NewsSource.slug, NewsSource.name)
        .order_by(func.count(LocalContent.id).desc()))).all()

    return LocalTaxonomy(
        types=[TaxItem(id=t, name=TYPE_LABELS.get(t, t.title()), count=c)
               for t, c in sorted(type_rows, key=lambda r: -r[1])],
        categories=[TaxItem(id=c, name=CATEGORY_LABELS.get(c, c.title()), count=n)
                    for c, n in sorted(cat_rows, key=lambda r: -r[1])],
        sources=[SourceItem(id=i, slug=s, name=n, count=cnt) for i, s, n, cnt in src_rows],
    )


@router.get("/search", response_model=LocalSearchResponse)
async def local_search(
    q: str = Query(..., min_length=2, description="text query (title + summary)"),
    types: str | None = None,
    categories: str | None = None,
    sources: str | None = None,
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Full-text-ish search over active content (not restricted to geocoded rows)."""
    conds = [LocalContent.status == "active",
             or_(LocalContent.title.ilike(f"%{q}%"), LocalContent.summary.ilike(f"%{q}%"))]
    tl, cl, sl = _csv(types), _csv(categories), _csv(sources)
    if tl:
        conds.append(LocalContent.type.in_(tl))
    if cl:
        conds.append(LocalContent.category.in_(cl))
    if date_from:
        conds.append(LocalContent.publish_time >= date_from)
    if date_to:
        conds.append(LocalContent.publish_time <= date_to)

    join_source = bool(sl)
    if sl:
        conds.append(NewsSource.slug.in_(sl))

    count_stmt = select(func.count(LocalContent.id))
    if join_source:
        count_stmt = count_stmt.join(NewsSource, LocalContent.source_id == NewsSource.id)
    total = (await db.execute(count_stmt.where(*conds))).scalar_one()

    rows_stmt = select(
        LocalContent.id, LocalContent.type, LocalContent.category, LocalContent.title,
        LocalContent.summary, LocalContent.source_name, LocalContent.source_url,
        LocalContent.latitude, LocalContent.longitude, LocalContent.city,
        LocalContent.event_time, LocalContent.publish_time, LocalContent.image_url,
    )
    if join_source:
        rows_stmt = rows_stmt.join(NewsSource, LocalContent.source_id == NewsSource.id)
    rows = (await db.execute(
        rows_stmt.where(*conds)
        .order_by(LocalContent.publish_time.desc().nullslast())
        .limit(limit).offset(offset))).all()

    results = [LocalSearchItem(
        id=r[0], type=r[1], category=r[2], title=r[3], summary=r[4],
        source_name=r[5], source_url=r[6], lat=r[7], lng=r[8], city=r[9],
        event_time=r[10], publish_time=r[11], image_url=r[12],
    ) for r in rows]
    return LocalSearchResponse(total=total, results=results)


@router.get("/{content_id}", response_model=LocalContentDetail)
async def local_detail(content_id: int, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(
        select(LocalContent).where(LocalContent.id == content_id)
        .options(selectinload(LocalContent.tags)))).scalar_one_or_none()
    if c is None or c.status in ("hidden",):
        raise HTTPException(status_code=404, detail="Content not found")
    return LocalContentDetail(
        id=c.id, type=c.type, category=c.category, title=c.title,
        summary=c.summary, description=c.description,
        source_name=c.source_name, source_url=c.source_url,
        event_time=c.event_time, event_end_time=c.event_end_time, publish_time=c.publish_time,
        lat=c.latitude, lng=c.longitude, address=c.address, city=c.city,
        province=c.province, country=c.country, image_url=c.image_url,
        confidence_score=c.confidence_score, tags=[t.tag for t in c.tags],
        created_at=c.created_at,
    )
