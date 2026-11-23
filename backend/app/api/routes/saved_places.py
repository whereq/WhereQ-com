from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.saved_place import SavedPlace
from app.models.user import User
from app.schemas.saved_place import SavedPlaceCreate, SavedPlaceRead
from app.services.fuel_stations import (
    CURRENCY_BY_COUNTRY,
    FUEL_CATEGORY,
    FUEL_SOURCE,
    UNIT_BY_COUNTRY,
)

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
    """Save a place.

    **A negative place id is a live fuel station.** When the stations are read
    from whereq.cloud, the map's fuel pins carry the negative of the
    upstream's station id, and there is no local row for them to point at. So
    saving one **materialises** it: whereq.com writes a row of its own — the
    station's identity, not its prices — and saves that.

    The row is whereq.com's own data (the user's saved place); the prices
    stay upstream and are read live when the card is opened. The map's pin
    then carries this row's id, so the saved state and the map agree.
    """
    place_id = data.place_id
    if place_id < 0:
        place_id = await _materialise_station(db, -place_id)

    # Check if already saved
    q = select(SavedPlace).where(
        SavedPlace.user_id == current_user.id,
        SavedPlace.place_id == place_id,
    )
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Place already saved")

    sp = SavedPlace(user_id=current_user.id, place_id=place_id, label=data.label)
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    return sp


def _station_meta(station: dict, country: str | None) -> dict:
    """The metadata of a materialised station — **identity only**.

    The licensed part of the row (the prices and when they were observed) is
    deliberately **not** here: it is read from whereq.cloud when the card is
    opened, so no copy of it is kept in whereq.com's database.
    """
    return {k: v for k, v in {
        "brand": station.get("brand"),
        "state": station.get("state"),
        "state_iso": station.get("state_iso"),
        "municipality": station.get("municipality"),
        "currency": CURRENCY_BY_COUNTRY.get(country),
        "unit": UNIT_BY_COUNTRY.get(country),
        "data_source": station.get("source"),
        "station_id": station.get("id"),
        "saved_from_cloud": True,
    }.items() if v is not None}


async def _materialise_station(db: AsyncSession, station_id: int) -> int:
    """Write whereq.com's own row for a fuel station, and return its id.

    The row carries the station's **identity** — where it is and what it is
    called — and nothing licensed: the prices are read from whereq.cloud when
    the card is opened, so no copy of them is kept here.

    The upsert is on ``(source, external_id)``, the key the mirror used, so a
    station that was mirrored before the cut is *updated* rather than
    duplicated.
    """
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.place import Place
    from app.services.cloud_fuel import fetch_station, station_external_id

    try:
        payload = await asyncio.to_thread(fetch_station, station_id=station_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Fuel station is unavailable") from exc

    station = (payload or {}).get("station") or (payload or {}).get("data") or {}
    if not station:
        raise HTTPException(status_code=404, detail="Place not found")

    country = (station.get("country") or "").upper() or None
    external_id = station_external_id(station)
    row = {
        "name": (station.get("name") or station.get("brand") or "Fuel station")[:255],
        "description": None,
        "latitude": float(station["lat"]),
        "longitude": float(station["lon"]),
        "address": None,
        "city": station.get("municipality"),
        "country": country,
        "category": FUEL_CATEGORY,
        "kind": "poi",
        "sub": station.get("brand"),
        # Identity only. The prices are licensed upstream data and are read
        # live; they are never written here.
        "metadata_json": _station_meta(station, country),
        "source": FUEL_SOURCE,
        "external_id": external_id,
        "geom": func.ST_SetSRID(func.ST_MakePoint(station["lon"], station["lat"]), 4326),
    }
    stmt = pg_insert(Place).values([row])
    stmt = stmt.on_conflict_do_update(
        index_elements=[Place.source, Place.external_id],
        index_where=Place.external_id.isnot(None),
        set_={
            "name": stmt.excluded.name,
            "latitude": stmt.excluded.latitude,
            "longitude": stmt.excluded.longitude,
            "city": stmt.excluded.city,
            "country": stmt.excluded.country,
            "geom": stmt.excluded.geom,
            # The metadata is replaced, not merged: the row the mirror wrote
            # before the cut carries the prices, and those are read live now.
            "metadata_json": stmt.excluded.metadata_json,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()

    place_id = (await db.execute(
        select(Place.id).where(
            Place.source == FUEL_SOURCE, Place.external_id == external_id)
    )).scalar_one()
    return place_id


@router.delete("/{place_id}", status_code=204)
async def unsave_place(
    place_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unsave a place.

    A **negative** id is a live fuel station: it is resolved to the row
    whereq.com materialised for it when it was saved, so the unsave works
    even before the map has refreshed and started showing the materialised
    id.
    """
    if place_id < 0:
        place_id = await _materialised_id(db, -place_id)
        if place_id is None:
            raise HTTPException(status_code=404, detail="Saved place not found")

    q = delete(SavedPlace).where(
        SavedPlace.user_id == current_user.id,
        SavedPlace.place_id == place_id,
    )
    result = await db.execute(q)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Saved place not found")
    await db.commit()


async def _materialised_id(db: AsyncSession, station_id: int) -> int | None:
    """The id of whereq.com's row for a station, or ``None`` if it has none."""
    import asyncio

    from sqlalchemy import select

    from app.models.place import Place
    from app.services.cloud_fuel import fetch_station, station_external_id

    try:
        payload = await asyncio.to_thread(fetch_station, station_id=station_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Fuel station is unavailable") from exc
    station = (payload or {}).get("station") or (payload or {}).get("data") or {}
    if not station:
        return None
    external_id = station_external_id(station)
    return (await db.execute(
        select(Place.id).where(
            Place.source == FUEL_SOURCE,
            Place.external_id == external_id,
            Place.metadata_json["saved_from_cloud"].astext == "true",
        )
    )).scalar_one_or_none()
