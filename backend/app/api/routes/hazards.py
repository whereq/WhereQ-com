"""Hazards / community reports API.

Viewing (map) is public; reporting and confirming require a signed-in user.
Reports expire automatically per type, and confirmations extend the window.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.hazard import Hazard
from app.models.user import User
from app.schemas.hazard import HazardCreate, HazardPin, HazardRead

router = APIRouter(prefix="/hazards", tags=["hazards"])

# Default lifetime per type (hours).
_TTL_HOURS = {"accident": 4, "closure": 12, "police": 2, "weather": 12, "hazard": 6, "other": 6}
_CONFIRM_EXTEND = timedelta(hours=1)
_MAX_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_bbox(bbox: str | None):
    if not bbox:
        return None
    try:
        a, b, c, d = (float(x) for x in bbox.split(","))
        return a, b, c, d
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'")


@router.get("/map", response_model=list[HazardPin])
async def hazards_map(
    bbox: str | None = None,
    types: str | None = None,
    limit: int = Query(1000, ge=1, le=4000),
    db: AsyncSession = Depends(get_db),
):
    """Active, unexpired reports in the viewport."""
    conds = [Hazard.status == "active", Hazard.expires_at > _now()]
    bb = _parse_bbox(bbox)
    if bb:
        mnlng, mnlat, mxlng, mxlat = bb
        conds.append(func.ST_Intersects(
            Hazard.geom, func.ST_MakeEnvelope(mnlng, mnlat, mxlng, mxlat, 4326)))
    if types:
        wanted = [t.strip() for t in types.split(",") if t.strip()]
        if wanted:
            conds.append(Hazard.type.in_(wanted))
    rows = (await db.execute(
        select(Hazard).where(*conds).order_by(Hazard.created_at.desc()).limit(limit))).scalars().all()
    return [HazardPin(id=h.id, type=h.type, severity=h.severity, title=h.title,
                      lat=h.latitude, lng=h.longitude, confirmations=h.confirmations,
                      created_at=h.created_at, expires_at=h.expires_at) for h in rows]


@router.post("", response_model=HazardRead, status_code=201)
async def create_hazard(
    data: HazardCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ttl = timedelta(hours=_TTL_HOURS.get(data.type, 6))
    h = Hazard(
        type=data.type, severity=data.severity, title=data.title.strip(),
        description=data.description, latitude=data.latitude, longitude=data.longitude,
        reporter_id=user.id, status="active", expires_at=_now() + ttl,
    )
    h.geom = func.ST_SetSRID(func.ST_MakePoint(data.longitude, data.latitude), 4326)
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


@router.post("/{hazard_id}/confirm", response_model=HazardRead)
async def confirm_hazard(
    hazard_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a report still applies — bumps the count and extends its life."""
    h = await db.get(Hazard, hazard_id)
    if not h or h.status != "active":
        raise HTTPException(status_code=404, detail="Hazard not found")
    h.confirmations += 1
    horizon = _now() + _MAX_TTL
    h.expires_at = min(h.expires_at + _CONFIRM_EXTEND, horizon)
    await db.commit()
    await db.refresh(h)
    return h
