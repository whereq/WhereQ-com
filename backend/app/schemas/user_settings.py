from datetime import datetime

from pydantic import BaseModel, Field


class UserSettingsRead(BaseModel):
    """The account-scoped preferences."""

    radius_km: float
    #: The categories the user kept in the nearby filter. Empty = every category.
    categories: list[str]
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserSettingsUpdate(BaseModel):
    """A partial update — omitted fields are left alone."""

    radius_km: float | None = Field(default=None, ge=0.1, le=50)
    categories: list[str] | None = None
