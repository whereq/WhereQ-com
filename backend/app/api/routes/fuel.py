"""Fuel price data (whereq.cloud) — signed-in users only.

The whereq.cloud API key stays on the server: the browser calls these
endpoints, which serve rows already crawled from whereq.cloud into the
database. Nothing here spends metered quota at request time.

The data itself is licensed and metered upstream, so the whole router
requires a session (Keycloak token). Anonymous visitors still see the fuel
stations on the map — the prices are stripped from the place payloads instead.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.fuel import (
    FuelAveragesRead,
    FuelRegionRead,
    FuelSeriesRead,
    FuelStationRead,
)
from app.crawler.upstream.fuel_prices import list_regions, list_series, series_to_dict, viewport_averages
from app.crawler.upstream.fuel_stations import find_stations

router = APIRouter(prefix="/fuel", tags=["fuel"], dependencies=[Depends(get_current_user)])


@router.get("/prices", response_model=list[FuelSeriesRead])
async def fuel_prices(
    region: str | None = Query(None, description="Region slug: ca, us, mx"),
    geo: str | None = Query(None, description="Place label, e.g. 'Toronto, Ontario' or 'CALIFORNIA'"),
    q: str | None = Query(None, description="Search the product/item name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated fuel price averages (state / national / metro)."""
    rows = await list_series(db, region=region, geo=geo, q=q, limit=limit, offset=offset)
    return [series_to_dict(r) for r in rows]


@router.get("/stations", response_model=list[FuelStationRead])
async def fuel_stations(
    q: str | None = Query(None, description="Station, brand or city name"),
    lat: float | None = Query(None, description="Latitude to measure distance from"),
    lng: float | None = Query(None, description="Longitude to measure distance from"),
    radius_km: float | None = Query(None, ge=0.1, le=500, description="Search radius (km)"),
    bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat of the viewport"),
    product: str = Query("regular", description="Product used for the price sort"),
    sort: str = Query("distance", pattern="^(distance|price)$"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Gas stations with their prices — nearest first, or cheapest first.

    Served from the rows already crawled from whereq.cloud, so it never spends
    metered quota and the API key stays on the server.
    """
    return await find_stations(db, q=q, lat=lat, lng=lng, radius_km=radius_km,
                               bbox=bbox, product=product, sort=sort, limit=limit)


@router.get("/averages", response_model=FuelAveragesRead)
async def fuel_averages(
    bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat of the map viewport"),
    db: AsyncSession = Depends(get_db),
):
    """Fuel averages for the area the map is showing.

    The region is resolved from the fuel stations inside the viewport, so the
    average always matches what the user is looking at (a Canadian metro, a
    US state, …) and falls back to the national figure when the exact region
    has no series.
    """
    return await viewport_averages(db, bbox)


@router.get("/regions", response_model=list[FuelRegionRead])
async def fuel_regions(db: AsyncSession = Depends(get_db)):
    """The region/geo pairs that have price series (for a picker)."""
    return await list_regions(db)
