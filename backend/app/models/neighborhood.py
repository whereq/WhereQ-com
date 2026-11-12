from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User


class Neighborhood(Base):
    __tablename__ = "neighborhoods"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(128), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    # Creator of this neighborhood (null for rows that predate ownership
    # tracking). Writes are restricted to this user; staff may override.
    # ON DELETE SET NULL so removing a user never deletes the dataset.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Scores (0–100)
    safety_score: Mapped[int | None] = mapped_column(Integer)
    walkability_score: Mapped[int | None] = mapped_column(Integer)
    transit_score: Mapped[int | None] = mapped_column(Integer)
    food_score: Mapped[int | None] = mapped_column(Integer)
    schools_score: Mapped[int | None] = mapped_column(Integer)
    overall_score: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="neighborhoods", lazy="select")
