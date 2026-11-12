from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import can_read_route, require_route_write_access
from app.core.security import (
    Principal,
    get_current_user,
    get_optional_principal,
    get_principal,
)
from app.models.route import Route
from app.models.user import User
from app.schemas.route import RouteCreate, RouteRead, RouteUpdate, Waypoint

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("", response_model=list[RouteRead])
async def list_public_routes(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    q = select(Route).where(Route.is_public == True).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/mine", response_model=list[RouteRead])
async def list_my_routes(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The signed-in user's own routes, most recent first."""
    q = (select(Route).where(Route.user_id == user.id)
         .order_by(Route.created_at.desc()).limit(limit))
    return (await db.execute(q)).scalars().all()


@router.get("/user/{user_id}", response_model=list[RouteRead])
async def list_user_routes(
    user_id: int,
    principal: Principal | None = Depends(get_optional_principal),
    db: AsyncSession = Depends(get_db),
):
    """Routes belonging to a user.

    Only *published* routes are visible to anyone else — a route carries its
    full GPS trace, so an unowned route must not be readable by id or by
    walking the user ids. The owner (and staff) see their own private routes.
    """
    q = select(Route).where(Route.user_id == user_id)
    if not (principal and (principal.is_staff or principal.id == user_id)):
        q = q.where(Route.is_public == True)
    q = q.order_by(Route.created_at.desc()).limit(200)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{route_id}", response_model=RouteRead)
async def get_route(
    route_id: int,
    principal: Principal | None = Depends(get_optional_principal),
    db: AsyncSession = Depends(get_db),
):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    if not can_read_route(principal, route):
        # 404 (not 403) so an id sweep cannot tell private routes apart from
        # routes that do not exist.
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.post("", response_model=RouteRead, status_code=201)
async def create_route(
    data: RouteCreate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    route = Route(
        user_id=principal.id,
        **data.model_dump(),
    )
    db.add(route)
    await db.commit()
    await db.refresh(route)
    return route


@router.patch("/{route_id}", response_model=RouteRead)
async def update_route(
    route_id: int,
    data: RouteUpdate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    require_route_write_access(principal, route)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(route, field, value)
    await db.commit()
    await db.refresh(route)
    return route


@router.post("/{route_id}/waypoints", response_model=RouteRead)
async def append_waypoints(
    route_id: int,
    waypoints: list[Waypoint],
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    require_route_write_access(principal, route)
    existing = list(route.waypoints or [])
    existing.extend([w.model_dump() for w in waypoints])
    route.waypoints = existing
    await db.commit()
    await db.refresh(route)
    return route


@router.delete("/{route_id}", status_code=204)
async def delete_route(
    route_id: int,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    require_route_write_access(principal, route)
    await db.delete(route)
    await db.commit()
