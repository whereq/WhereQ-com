from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserSettings(Base):
    """One row per user — the account-scoped preferences.

    The map's nearby-events search (its radius and the categories the user kept)
    lives here so the choice follows the account across devices. The row is
    created lazily on the first read or write, because the local ``users`` row
    itself is only provisioned on the first authenticated request.

    Anonymous visitors get the same defaults; the browser keeps theirs until
    they sign in, and the frontend then syncs them up.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    #: Radius of the nearby search, in kilometres.
    radius_km: Mapped[float] = mapped_column(
        Float, nullable=False, default=5.0, server_default="5.0"
    )
    #: The categories the user kept in the nearby filter. Empty = every category.
    categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
