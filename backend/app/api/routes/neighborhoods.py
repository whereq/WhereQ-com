import math

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2 import Geography
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_neighborhood_write_access
from app.core.security import Principal, get_principal
from app.models.neighborhood import Neighborhood
from app.models.place import Place
from app.schemas.neighborhood import NeighborhoodCreate, NeighborhoodRead, NeighborhoodUpdate

router = APIRouter(prefix="/neighborhoods", tags=["neighborhoods"])


def _saturating_score(count: int, k: float) -> int:
    """Map a raw nearby-feature count to 0–100 on a saturating curve."""
    return round(100 * (1 - math.exp(-count / k)))


@router.get("/insights")
async def neighborhood_insights(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Walk / Transit / Bike / Greenery scores for a point, computed from our own
    crawled POIs (PostGIS distance), not an external API."""
    pt = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)

    async def _count(conds: list, radius_m: int) -> int:
        within = func.ST_DWithin(func.cast(Place.geom, Geography), func.cast(pt, Geography), radius_m)
        return (await db.execute(
            select(func.count()).where(Place.geom.isnot(None), within, *conds))).scalar_one()

    walkable = or_(
        Place.kind.in_(["pharmacy", "clinic", "library", "plaza"]),
        and_(Place.kind == "poi", Place.category.in_(["food", "coffee", "stays"])),
    )
    walk = await _count([walkable], 1000)
    transit = await _count([Place.kind == "transit"], 800)
    bike = await _count([Place.kind == "bike"], 1000)
    greenery = await _count([Place.kind == "park"], 1200)

    return {
        "walk": _saturating_score(walk, 25),
        "transit": _saturating_score(transit, 8),
        "bike": _saturating_score(bike, 6),
        "greenery": _saturating_score(greenery, 4),
        "counts": {"walk": walk, "transit": transit, "bike": bike, "greenery": greenery},
    }


@router.get("", response_model=list[NeighborhoodRead])
async def list_neighborhoods(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    city: str | None = None,
    country: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Neighborhood)
    if city:
        q = q.where(Neighborhood.city.ilike(f"%{city}%"))
    if country:
        q = q.where(Neighborhood.country.ilike(f"%{country}%"))
    q = q.offset(skip).limit(limit).order_by(Neighborhood.overall_score.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{neighborhood_id}", response_model=NeighborhoodRead)
async def get_neighborhood(neighborhood_id: int, db: AsyncSession = Depends(get_db)):
    nb = await db.get(Neighborhood, neighborhood_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Neighborhood not found")
    return nb


@router.post("", response_model=NeighborhoodRead, status_code=201)
async def create_neighborhood(
    data: NeighborhoodCreate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    """Create a neighborhood. The creator becomes its owner — only they (or
    staff) may edit or delete it afterwards."""
    nb = Neighborhood(**data.model_dump())
    nb.user_id = principal.id
    db.add(nb)
    await db.commit()
    await db.refresh(nb)
    return nb


@router.patch("/{neighborhood_id}", response_model=NeighborhoodRead)
async def update_neighborhood(
    neighborhood_id: int,
    data: NeighborhoodUpdate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    nb = await db.get(Neighborhood, neighborhood_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Neighborhood not found")
    require_neighborhood_write_access(principal, nb)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(nb, field, value)
    await db.commit()
    await db.refresh(nb)
    return nb


@router.delete("/{neighborhood_id}", status_code=204)
async def delete_neighborhood(
    neighborhood_id: int,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    nb = await db.get(Neighborhood, neighborhood_id)
    if not nb:
        raise HTTPException(status_code=404, detail="Neighborhood not found")
    require_neighborhood_write_access(principal, nb)
    await db.delete(nb)
    await db.commit()
