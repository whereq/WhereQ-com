"""The I/O for a card — what the user may write, and what the app reads back."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.place_card import CARD_KINDS

#: The category keys a card may filter by. The same vocabulary the nearby
#: search uses — a card's list is that search, with the card's own radius and
#: categories.
MAX_CATEGORIES = 40

#: A card's logo is an external URL, not an upload: the backend hosts no user
#: binaries. http(s) only.
ALLOWED_LOGO_SCHEMES = ("http://", "https://")


def _normalize_categories(categories: list[str]) -> list[str]:
    """Lower-case, trimmed, de-duplicated — order preserved."""
    out: list[str] = []
    for c in categories[:MAX_CATEGORIES]:
        c = c.strip().lower()
        if c and c not in out:
            out.append(c)
    return out


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("a card needs a name")
    return v


def _clean_kind(v: str) -> str:
    v = v.strip().lower()
    if v not in CARD_KINDS:
        raise ValueError(f"kind must be one of {', '.join(CARD_KINDS)}")
    return v


def _clean_logo(v: str | None) -> str | None:
    """A card's logo is an external URL, not an upload."""
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not v.startswith(ALLOWED_LOGO_SCHEMES):
        raise ValueError("the logo must be an http(s) URL")
    return v


def _clean_accent(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not (v.startswith("#") and len(v) in (4, 7)):
        raise ValueError("the accent must be a hex colour")
    return v


class PlaceCardBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    kind: str = "business"
    category: str | None = Field(default=None, max_length=64)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = Field(default=None, max_length=512)
    city: str | None = Field(default=None, max_length=128)
    country: str | None = Field(default=None, max_length=128)
    radius_km: float = Field(default=5.0, ge=0.1, le=50)
    categories: list[str] = Field(default_factory=list)
    logo_url: str | None = Field(default=None, max_length=2048)
    accent: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        return _clean_name(v)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        return _clean_kind(v)

    @field_validator("categories")
    @classmethod
    def _clean_categories(cls, v: list[str]) -> list[str]:
        return _normalize_categories(v)

    @field_validator("logo_url")
    @classmethod
    def _logo_is_a_url(cls, v: str | None) -> str | None:
        return _clean_logo(v)

    @field_validator("accent")
    @classmethod
    def _accent_is_hex(cls, v: str | None) -> str | None:
        return _clean_accent(v)


class PlaceCardCreate(PlaceCardBase):
    """What a user sends to make a card."""


class PlaceCardUpdate(BaseModel):
    """A partial update — omitted fields are left alone."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    kind: str | None = None
    category: str | None = Field(default=None, max_length=64)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, max_length=512)
    city: str | None = Field(default=None, max_length=128)
    country: str | None = Field(default=None, max_length=128)
    radius_km: float | None = Field(default=None, ge=0.1, le=50)
    categories: list[str] | None = None
    logo_url: str | None = Field(default=None, max_length=2048)
    accent: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        return None if v is None else _clean_name(v)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str | None) -> str | None:
        return None if v is None else _clean_kind(v)

    @field_validator("categories")
    @classmethod
    def _clean_categories(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _normalize_categories(v)

    @field_validator("logo_url")
    @classmethod
    def _logo_is_a_url(cls, v: str | None) -> str | None:
        return None if v is None else _clean_logo(v)

    @field_validator("accent")
    @classmethod
    def _accent_is_hex(cls, v: str | None) -> str | None:
        return None if v is None else _clean_accent(v)


class PlaceCardRead(PlaceCardBase):
    """A card, as the app reads it."""

    id: int
    user_id: int
    status: str
    publish_token: str | None = None
    published_at: datetime | None = None
    report_count: int
    view_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
