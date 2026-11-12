from datetime import datetime

from pydantic import BaseModel


class NearbyItem(BaseModel):
    """One thing near the map centre.

    ``type`` says which table it came from (``place``, ``local``, ``school``,
    ``hazard``) and ``category`` is the filter key the UI groups by — the same
    vocabulary for every source, so the modal can filter them all at once.
    """

    id: str
    type: str
    category: str
    subcategory: str | None = None
    name: str
    meta: str | None = None
    lat: float
    lng: float
    distance_m: int
    #: The live fuel price — signed-in users only (the prices are licensed).
    price: float | None = None
    currency: str | None = None
    observed_at: str | None = None
    url: str | None = None
    image_url: str | None = None
    #: When it is happening (an event) or was published (news).
    when: datetime | None = None


class NearbyCenter(BaseModel):
    lat: float
    lng: float


class NearbyResponse(BaseModel):
    """Everything near the centre, merged into one list."""

    items: list[NearbyItem]
    #: How many items each category contributed — the badges on the filter chips.
    counts: dict[str, int]
    total: int
    radius_m: int
    center: NearbyCenter
    #: The categories actually applied (empty request = all of them).
    categories: list[str]
