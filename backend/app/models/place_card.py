"""The user's own card — a customised view of a place.

A card is **not** a place. The ``places`` table is the app's reference data:
the OSM and whereq.cloud rows that make the map worth looking at. The map
endpoint filters on ``kind``/``category`` and never on ``source``, and the
counts endpoint counts the same rows — so a user-authored row in ``places``
becomes a pin for everybody and inflates the category counts.

A card therefore has its own table. It is a *published view of a place*: an
anchor (the address the user named), the two things that make it personal
(the radius and the categories of the aggregation under it), the user's own
words, and — from the publishing phase — a revocable public identity.

See ``docs/ARCHITECTURE.md`` for how it sits in the app.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User

#: The two field sets behind one card shell. The shape is the same; the
#: profile differs (a business carries hours/phone/website, a person carries
#: a photo and a bio).
CARD_KINDS = ("business", "person")

#: The lifecycle. A card is a draft until it is published, and a published
#: card can be revoked (by the owner, by staff, or automatically once it is
#: reported enough times).
CARD_STATUSES = ("draft", "published", "revoked")


class PlaceCard(Base):
    """One card — the user's own, anchored at an address they named."""

    __tablename__ = "place_cards"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    #: The owner. Deleting the account takes its cards with it.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: "business" or "person" — the profile, not the shape.
    kind: Mapped[str] = mapped_column(String(16), default="business", index=True)
    #: What kind of place a business card is about ("food", "coffee", "clinic",
    #: …). It is a **label** for the reader — the taxonomy the map filters by
    #: is the app's own, and a card never joins it (a card is not a place, so
    #: it is never counted and never appears in the map's categories).
    category: Mapped[str | None] = mapped_column(String(64))

    # ── the anchor ──────────────────────────────────────────────────────────
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    #: Denormalised from the geocode, so the card still renders if the
    #: geocoder's answer changes tomorrow.
    address: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(128))

    # ── the live query under the card ───────────────────────────────────────
    #: The radius of the aggregation, in kilometres. The list is evaluated at
    #: view time — the card stores the question, not the answer.
    radius_km: Mapped[float] = mapped_column(
        Float, nullable=False, default=5.0, server_default="5.0"
    )
    #: The categories the aggregation is filtered by. Empty = every category.
    categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}"
    )

    # ── the user's own dressing ─────────────────────────────────────────────
    #: An external URL. There is no upload endpoint in the backend, and
    #: hosting user-supplied binaries would be the biggest abuse surface in
    #: the feature.
    logo_url: Mapped[str | None] = mapped_column(Text)
    #: The card's own colour (hex).
    accent: Mapped[str | None] = mapped_column(String(16))

    # ── publication ─────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    #: The public identity. Minted when the card is published; null while it
    #: is a draft, and kept after a revoke so the old link resolves to
    #: "no longer published" instead of a random 404.
    publish_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: How many times this card has been reported. The safety net: publishing
    #: is immediate, so the queue is the report, not a review.
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="place_cards", lazy="select")
