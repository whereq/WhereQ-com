"""Ownership and role checks for user-authored content.

Content a user creates — places, neighborhoods, routes — records the id of its
creator. Writes are restricted to that creator; a staff account may override.

Two kinds of content need different treatment:

* **User content** (``places.source == 'manual'``, neighborhoods, routes) is
  owned by whoever created it.
* **Managed content** (places crawled from OSM or whereq.cloud) is shared
  reference data that a crawl pipeline refreshes on its own schedule. A
  user edit would be silently overwritten on the next run, so only staff may
  modify it.

The status code follows the visibility of the resource:

* **403** for a resource anyone can already read (places, neighborhoods) —
  ownership is denied, but its existence is public information.
* **404** for a resource that is private by default (routes) — so neither a
  read nor a write can be used to discover which ids exist.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.core.security import Principal

#: Place sources that are refreshed by the automatic crawl. Rows
#: with these sources are reference data, not user content.
MANAGED_PLACE_SOURCES = frozenset({"osm", "whereq_cloud"})


def is_staff(principal: Principal | None) -> bool:
    """True when the caller carries a staff realm role."""
    return bool(principal and principal.is_staff)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def require_place_write_access(principal: Principal, place) -> None:
    """Raise 403 unless the caller may modify this place.

    Staff may modify anything. Everyone else may modify only the places they
    created — never a pipeline-managed row.
    """
    if principal.is_staff:
        return
    if place.source in MANAGED_PLACE_SOURCES:
        raise _forbidden(
            "This place comes from an automatic data feed and cannot be edited"
        )
    if place.user_id is None or place.user_id != principal.id:
        raise _forbidden("You can only modify places you created")


def require_neighborhood_write_access(principal: Principal, neighborhood) -> None:
    """Raise 403 unless the caller may modify this neighborhood."""
    if principal.is_staff:
        return
    if neighborhood.user_id is None or neighborhood.user_id != principal.id:
        raise _forbidden("You can only modify neighborhoods you created")


def require_place_card_write_access(principal: Principal, card) -> None:
    """Raise unless the caller may modify this card.

    A card is private until it is published, so a caller who does not own it
    gets **404**, not 403 — the same rule the read path uses, so a write
    attempt cannot be used to discover which card ids exist.
    """
    if principal.is_staff:
        return
    if card.user_id != principal.id:
        raise HTTPException(status_code=404, detail="Card not found")


def require_route_write_access(principal: Principal, route) -> None:
    """Raise unless the caller may modify this route.

    A route is private unless it was published, so a caller who does not own
    it gets **404**, not 403 — the same rule the read path uses, so a write
    attempt cannot be used to discover which route ids exist.
    """
    if principal.is_staff:
        return
    if route.user_id != principal.id:
        raise HTTPException(status_code=404, detail="Route not found")


def can_read_route(principal: Principal | None, route) -> bool:
    """True when the caller may see this route.

    A route is visible to its owner, to staff, and to anyone when it has been
    published (``is_public``).
    """
    if route.is_public:
        return True
    if principal is None:
        return False
    if principal.is_staff:
        return True
    return route.user_id == principal.id
