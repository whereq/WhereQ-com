from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Keycloak `sub` — the stable external identity. Null only for legacy rows
    # that have not yet been linked on first Keycloak login.
    keycloak_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Null for Keycloak-managed users (passwords live in Keycloak).
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    theme: Mapped[str] = mapped_column(String(8), default="dark")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    routes: Mapped[list["Route"]] = relationship(back_populates="user", lazy="select")
    stories: Mapped[list["Story"]] = relationship(back_populates="author", lazy="select")
    places: Mapped[list["Place"]] = relationship(back_populates="owner", lazy="select")
    neighborhoods: Mapped[list["Neighborhood"]] = relationship(back_populates="owner", lazy="select")
    place_cards: Mapped[list["PlaceCard"]] = relationship(
        back_populates="owner", lazy="select", cascade="all, delete-orphan"
    )
