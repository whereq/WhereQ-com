from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.newsletter import NewsletterSubscriber

router = APIRouter(prefix="/newsletter", tags=["newsletter"])


class SubscribeRequest(BaseModel):
    email: EmailStr


@router.post("/subscribe", status_code=201)
async def subscribe(data: SubscribeRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == data.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already subscribed")

    sub = NewsletterSubscriber(email=data.email)
    db.add(sub)
    await db.commit()
    return {"detail": "Subscribed successfully"}
