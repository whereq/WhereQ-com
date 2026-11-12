from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.friendship import Friendship
from app.models.user import User

router = APIRouter(prefix="/friends", tags=["friends"])


class FriendshipOut(BaseModel):
    id: int
    user_id: int
    friend_id: int
    status: str
    friend_username: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[FriendshipOut])
async def list_friends(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Friendship).where(
        or_(
            and_(Friendship.user_id == current_user.id, Friendship.status == "accepted"),
            and_(Friendship.friend_id == current_user.id, Friendship.status == "accepted"),
        )
    )
    result = await db.execute(q)
    friendships = result.scalars().all()

    out = []
    for f in friendships:
        fid = f.friend_id if f.user_id == current_user.id else f.user_id
        friend = await db.get(User, fid)
        out.append(FriendshipOut(
            id=f.id,
            user_id=f.user_id,
            friend_id=f.friend_id,
            status=f.status,
            friend_username=friend.username if friend else None,
        ))
    return out


@router.post("/{friend_id}", status_code=201)
async def send_friend_request(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if friend_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot friend yourself")

    existing = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == current_user.id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == current_user.id),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Friendship already exists")

    f = Friendship(user_id=current_user.id, friend_id=friend_id, status="pending")
    db.add(f)
    await db.commit()
    return {"detail": "Friend request sent"}


@router.patch("/{friendship_id}/accept")
async def accept_friend(
    friendship_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = await db.get(Friendship, friendship_id)
    if not f or f.friend_id != current_user.id:
        raise HTTPException(status_code=404, detail="Request not found")
    f.status = "accepted"
    await db.commit()
    return {"detail": "Friend request accepted"}


@router.delete("/{friendship_id}", status_code=204)
async def remove_friend(
    friendship_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = await db.get(Friendship, friendship_id)
    if not f or (f.user_id != current_user.id and f.friend_id != current_user.id):
        raise HTTPException(status_code=404, detail="Friendship not found")
    await db.delete(f)
    await db.commit()
