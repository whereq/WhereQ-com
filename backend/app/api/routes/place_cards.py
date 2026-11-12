"""The user's own cards.

Protected: every route needs a session, and the list is always the caller's
own. A card is **private by default** — it belongs to its owner until it is
published — so a card that is not yours answers **404**, not 403: neither a
read nor a write may be used to discover which ids exist.

A card is not a place: it never enters the ``places`` table, so it never
becomes a map pin and never inflates the category counts.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_place_card_write_access
from app.core.security import Principal, get_principal
from app.models.place_card import PlaceCard
from app.schemas.place_card import PlaceCardCreate, PlaceCardRead, PlaceCardUpdate

router = APIRouter(prefix="/place-cards", tags=["place-cards"])

#: How many cards one account may hold. A card is cheap, but a pile of them
#: is noise — the cap keeps "My cards" a place, not a dump.
MAX_CARDS_PER_USER = 50


def _not_found() -> HTTPException:
    """A card that is not yours is a 404 — it is private until it is published."""
    return HTTPException(status_code=404, detail="Card not found")


async def _own_card(db: AsyncSession, card_id: int, principal: Principal) -> PlaceCard:
    """The card, if the caller may see it — otherwise a 404."""
    card = await db.get(PlaceCard, card_id)
    if card is None:
        raise _not_found()
    require_place_card_write_access(principal, card)
    return card


@router.get("", response_model=list[PlaceCardRead])
async def list_cards(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    """The caller's own cards. There is no id in the path — the list is always
    yours, by construction."""
    rows = (
        await db.execute(
            select(PlaceCard)
            .where(PlaceCard.user_id == principal.id)
            .order_by(PlaceCard.updated_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post("", response_model=PlaceCardRead, status_code=201)
async def create_card(
    data: PlaceCardCreate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    """Make a card. The creator owns it; only they (or staff) may edit it."""
    count = len(
        (
            await db.execute(
                select(PlaceCard.id).where(PlaceCard.user_id == principal.id)
            )
        ).scalars().all()
    )
    if count >= MAX_CARDS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"You already have {MAX_CARDS_PER_USER} cards",
        )

    card = PlaceCard(**data.model_dump())
    card.user_id = principal.id
    # A card starts as a draft. The publication phase mints the token.
    card.status = "draft"
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


@router.get("/{card_id}", response_model=PlaceCardRead)
async def get_card(
    card_id: int,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    return await _own_card(db, card_id, principal)


@router.patch("/{card_id}", response_model=PlaceCardRead)
async def update_card(
    card_id: int,
    data: PlaceCardUpdate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    card = await _own_card(db, card_id, principal)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(card, field, value)
    await db.commit()
    await db.refresh(card)
    return card


@router.delete("/{card_id}", status_code=204)
async def delete_card(
    card_id: int,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    card = await _own_card(db, card_id, principal)
    await db.delete(card)
    await db.commit()
