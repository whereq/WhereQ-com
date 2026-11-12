from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.story import Story
from app.models.user import User
from app.schemas.story import StoryCreate, StoryRead, StoryUpdate

router = APIRouter(prefix="/stories", tags=["stories"])


@router.get("", response_model=list[StoryRead])
async def list_stories(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    place_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Story).where(Story.is_published == True)
    if place_id is not None:
        q = q.where(Story.place_id == place_id)
    q = q.offset(skip).limit(limit).order_by(Story.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{story_id}", response_model=StoryRead)
async def get_story(story_id: int, db: AsyncSession = Depends(get_db)):
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("", response_model=StoryRead, status_code=201)
async def create_story(
    data: StoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story = Story(
        **data.model_dump(),
        author_id=current_user.id,
    )
    db.add(story)
    await db.commit()
    await db.refresh(story)
    return story


@router.patch("/{story_id}", response_model=StoryRead)
async def update_story(
    story_id: int,
    data: StoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only edit your own stories")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(story, field, value)
    await db.commit()
    await db.refresh(story)
    return story


@router.delete("/{story_id}", status_code=204)
async def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only delete your own stories")
    await db.delete(story)
    await db.commit()
