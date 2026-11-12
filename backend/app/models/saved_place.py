from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SavedPlace(Base):
    __tablename__ = "saved_places"
    __table_args__ = (
        UniqueConstraint("user_id", "place_id", name="uq_saved_user_place"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
