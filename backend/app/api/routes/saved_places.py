from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.saved_place import SavedPlace
from app.models.user import User
from app.schemas.saved_place import SavedPlaceCreate, SavedPlaceRead

router = APIRouter(prefix="/saved-places", tags=["saved-places"])


@router.get("", response_model=list[SavedPlaceRead])
async def list_saved_places(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(SavedPlace).where(SavedPlace.user_id == current_user.id).order_by(SavedPlace.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=SavedPlaceRead, status_code=201)
async def save_place(
    data: SavedPlaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check if already saved
    q = select(SavedPlace).where(
        SavedPlace.user_id == current_user.id,
        SavedPlace.place_id == data.place_id,
    )
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Place already saved")

    sp = SavedPlace(user_id=current_user.id, **data.model_dump())
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    return sp


@router.delete("/{place_id}", status_code=204)
async def unsave_place(
    place_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = delete(SavedPlace).where(
        SavedPlace.user_id == current_user.id,
        SavedPlace.place_id == place_id,
    )
    result = await db.execute(q)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Saved place not found")
    await db.commit()
