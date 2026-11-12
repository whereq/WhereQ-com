"""Per-user settings — the account-scoped preferences.

Protected: the whole router needs a session. There is no id in the path — the
row is always the caller's own, so the ownership check is the query itself
(scoping every read and write by ``current_user.id``, like ``saved_places``).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.user_settings import UserSettingsRead, UserSettingsUpdate

router = APIRouter(prefix="/user-settings", tags=["user-settings"])

#: A sane ceiling on how many category keys one row may carry.
MAX_CATEGORIES = 40


def _normalize(categories: list[str]) -> list[str]:
    """Lower-case, trimmed, de-duplicated — order preserved."""
    out: list[str] = []
    for c in categories[:MAX_CATEGORIES]:
        c = c.strip().lower()
        if c and c not in out:
            out.append(c)
    return out


async def _get_or_create(db: AsyncSession, user_id: int) -> UserSettings:
    """The caller's settings row, created with the defaults if it is the first
    time we are asked for it (the ``users`` row is itself created lazily on the
    first authenticated request, so the settings row cannot pre-exist it)."""
    row = (await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )).scalar_one_or_none()
    if row is None:
        row = UserSettings(
            user_id=user_id,
            radius_km=settings.nearby_default_radius_km,
            categories=[],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


@router.get("", response_model=UserSettingsRead)
async def read_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The caller's settings — created with the defaults on the first read."""
    row = await _get_or_create(db, current_user.id)
    return UserSettingsRead.model_validate(row)


@router.patch("", response_model=UserSettingsRead)
async def update_settings(
    data: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the caller's settings. Omitted fields are left as they are."""
    row = await _get_or_create(db, current_user.id)
    if data.radius_km is not None:
        row.radius_km = data.radius_km
    if data.categories is not None:
        row.categories = _normalize(data.categories)
    await db.commit()
    await db.refresh(row)
    return UserSettingsRead.model_validate(row)
