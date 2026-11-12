from datetime import datetime

from pydantic import BaseModel


class FuelSeriesRead(BaseModel):
    """One aggregated fuel price series (state / national / metro average)."""

    id: int
    domain: str
    source: str | None = None
    region: str | None = None
    geo: str | None = None
    item: str
    # Normalised product key: regular | midgrade | premium | diesel | heating.
    product: str | None = None
    # Unit as published by the source ("Cents per litre", "$/GAL", "MXN/L").
    unit: str | None = None
    # Currency of the normalised value (CAD / USD / MXN).
    currency: str | None = None
    # The value converted to local currency per litre — the same unit the
    # station prices use, so averages and station prices can be compared.
    value_per_litre: float | None = None
    frequency: str | None = None
    latest_period: str | None = None
    latest_value: float | None = None
    prev_value: float | None = None
    points: int | None = None
    spark: list[float] | None = None
    updated_at: datetime | None = None


class FuelRegionRead(BaseModel):
    region: str | None = None
    geo: str | None = None
    unit: str | None = None


class FuelViewportRegion(BaseModel):
    """The area the averages were resolved for."""

    country: str | None = None
    state: str | None = None
    municipality: str | None = None
    geo: str | None = None
    station_count: int = 0


class FuelAveragesRead(BaseModel):
    """Regional fuel averages for the area the user is looking at."""

    region: FuelViewportRegion | None = None
    series: list[FuelSeriesRead] = []


class FuelStationRead(BaseModel):
    """One gas station with its latest prices."""

    id: int
    name: str
    brand: str | None = None
    city: str | None = None
    country: str | None = None
    lat: float
    lng: float
    # Per-product prices: { product: { price, observed_at } }.
    prices: dict[str, dict] = {}
    currency: str | None = None
    unit: str | None = None
    observed_at: str | None = None
    # The product used for the price sort ("regular").
    product: str | None = None
    price: float | None = None
    distance_km: float | None = None
