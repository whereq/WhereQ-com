"""Compare the local mirror with whereq.cloud, and write the comparison down.

WHY A LEDGER
-------------
The cut is decided by **reading** the differences, not by assuming there are
none. So every comparison is recorded — the counts, the identities that
differ, and the request that produced them — in ``cloud_parity_checks``.

A comparison that is not written down is a comparison nobody can read a week
later, when the question is "was it clean?".

WHAT COUNTS AS A DIFFERENCE
---------------------------
The local mirror is a **copy** of upstream, restricted to the targets this
installation syncs. So upstream holds at least as many places as the mirror
does, and a row only upstream has is not a defect — it is the mirror's
coverage. The two things that ARE defects:

* **only_local** — the mirror holds a row upstream does not. The mirror has
  something the original no longer has.
* **differing** — both sides hold the row, and the values disagree.

The fields compared are the ones the reader actually returns, so the ledger
describes what a user would see rather than what the tables happen to hold.

A DIFFERENCE NEEDS A WHOLE POPULATION
--------------------------------------
The upstream holds 32 954 places; the mirror holds the 304 of them inside
whereq.com's coverage targets. Comparing the mirror against the upstream's
*first* N rows compares two different populations, and every mirror row
outside that page looks like a place the upstream lost — 294 false defects
out of 304, measured against the live API.

So a comparison is only allowed to call a difference when **both** sides were
fetched whole. A truncated answer is recorded as ``partial``: inconclusive,
not a defect, and not a clean match either. A window full of partials is a
window with no evidence in it — which is not the same as a window that is
clean, and the report says so.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cloud_parity import CloudParityCheck

logger = logging.getLogger(__name__)

#: The fields a reader returns, and so the fields compared. Two numbers are
#: compared with a tolerance — a coordinate that differs in the fifteenth
#: decimal is the same coordinate, and a ledger that says "differs" about
#: every row teaches the reader to ignore the ledger.
COMPARABLE_FIELDS = (
    "kind", "name", "name_en", "name_zh", "name_local", "official_name",
    "source", "source_url", "license", "country_code", "province_code",
    "population", "area_km2", "centroid_lon", "centroid_lat", "has_boundary",
)

#: The extra fields the *detail* route returns. They are compared the same
#: way — these are the fields a user sees when they open a place.
DETAIL_FIELDS = (
    "kind_source", "source_id", "raw_admin_level", "raw_place", "raw_boundary",
    "iso_code", "ref", "population_date", "wikidata", "wikipedia", "website",
    "capital", "bbox_min_lon", "bbox_min_lat", "bbox_max_lon", "bbox_max_lat",
)

#: The fields compared as numbers, with the tolerance below.
_NUMERIC_FIELDS = ("population", "area_km2", "centroid_lon", "centroid_lat")

#: How much two coordinates may differ and still be "the same point". One
#: centimetre of latitude is about 1.1e-7 degrees.
COORDINATE_TOLERANCE = 1e-6

#: How much two *areas* may differ and still be "the same outline". The
#: mirror's area was copied from the upstream's own figure, so any real
#: difference is a whole number; the tolerance is here for a recomputation
#: rounding, not for a shape that changed.
AREA_RELATIVE_TOLERANCE = 0.001


def _canonical(value: Any) -> str:
    """A stable text form of a value, for values that are not scalars.

    A JSONB document on one side and the same document on the other do not
    have the same text: JSONB does not preserve key order, and a float
    written as ``8.40`` comes back as ``8.4``. Comparing the two as text
    would report a difference for every row that has a nested block.

    So a nested value is compared by its **canonical** form — the JSON with
    its keys sorted — and a list is compared in the order it arrives, which
    is why every caller sorts a list before handing it over.
    """
    return json.dumps(value, sort_keys=True, default=str)


def same(field: str, left: Any, right: Any) -> bool:
    """Do two values agree?

    ``field`` is only used to pick the comparison rule: the fields listed in
    ``_NUMERIC_FIELDS`` are compared as numbers, with a tolerance.
    """
    if field in _NUMERIC_FIELDS:
        if left is None or right is None:
            return left is None and right is None
        try:
            return abs(float(left) - float(right)) <= COORDINATE_TOLERANCE
        except (TypeError, ValueError):
            return False
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        # A boolean is compared as a boolean, not as its truthiness: `True`
        # and "yes" are both truthy, and a ledger that calls them the same
        # would miss a flag that came back wrong.
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (dict, list, tuple)) or isinstance(right, (dict, list, tuple)):
        return _canonical(left) == _canonical(right)
    return str(left).strip() == str(right).strip()


#: The old private name, kept so nothing that reached for it breaks.
_same = same


def compare(
    local_rows: Sequence[dict],
    cloud_rows: Sequence[dict],
    fields: Sequence[str] = COMPARABLE_FIELDS,
) -> dict:
    """Compare two answers and return the difference.

    The result is what a ``cloud_parity_checks`` row holds:

    * ``only_local`` — the uids the mirror has and upstream does not.
    * ``only_cloud`` — the uids upstream has and the mirror does not. This is
      the mirror's coverage, not a defect.
    * ``differing`` — the uids both sides hold, with the fields that
      disagree.
    """
    local_by_uid = {r.get("uid"): r for r in local_rows if r.get("uid")}
    cloud_by_uid = {r.get("uid"): r for r in cloud_rows if r.get("uid")}

    only_local = sorted(set(local_by_uid) - set(cloud_by_uid))
    only_cloud = sorted(set(cloud_by_uid) - set(local_by_uid))

    differing: dict[str, dict] = {}
    for uid in sorted(set(local_by_uid) & set(cloud_by_uid)):
        left = local_by_uid[uid]
        right = cloud_by_uid[uid]
        fields_out = {}
        for field in fields:
            if not same(field, left.get(field), right.get(field)):
                fields_out[field] = {"local": left.get(field), "cloud": right.get(field)}
        if fields_out:
            differing[uid] = fields_out

    return {
        "only_local": only_local,
        "only_cloud": only_cloud,
        "differing": differing,
    }


def is_clean(result: dict) -> bool:
    """Did the two answers agree?

    Only the mirror's own rows matter: a row upstream has and the mirror
    does not is the mirror's coverage, not a disagreement.
    """
    return not result.get("only_local") and not result.get("differing")


def decide(result: dict, complete: bool = True) -> tuple[str, dict]:
    """The status of a comparison, and the result as it may be written.

    A comparison that was not made over whole populations is **inconclusive**:
    it is recorded as ``partial``, with no difference written. A truncated
    answer cannot tell "upstream lost this row" from "the page stopped
    here", and a ledger that reports the first as the second teaches its
    reader to ignore it.

    A partial is neither a defect nor a clean match — it is the absence of
    evidence, and the report says so.
    """
    if not complete:
        return "partial", {
            "only_local": [],
            "only_cloud": result.get("only_cloud") or [],
            "differing": {},
        }
    return ("match" if is_clean(result) else "differ"), result


# ── the geometry ────────────────────────────────────────────────────────────
#
# The outline is compared by its extent, its size and its vertex count — not
# by a digest of the raw JSON. The mirror stores the outline in a JSONB
# column, and JSONB does not preserve key order or number formatting, so two
# identical shapes have two different digests. Comparing the shape's
# measurements compares the shape.

def _rings(geometry: dict | None) -> list[list]:
    """Every ring of a GeoJSON Polygon or MultiPolygon."""
    geometry = geometry or {}
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return [ring for ring in coords if ring]
    if kind == "MultiPolygon":
        out: list[list] = []
        for polygon in coords or []:
            out.extend(ring for ring in (polygon or []) if ring)
        return out
    return []


def geometry_points(geometry: dict | None) -> int:
    """How many coordinate positions the outline has.

    A closed ring repeats its first point at the end, so a GeoJSON ring has
    one more position than the polygon has vertices.
    """
    return sum(len(ring) for ring in _rings(geometry))


def geometry_rings(geometry: dict | None) -> int:
    """How many rings the outline has."""
    return len(_rings(geometry))


def geometry_bbox(geometry: dict | None) -> tuple[float, float, float, float] | None:
    """The outline's extent — (min_lon, min_lat, max_lon, max_lat) — or None."""
    lons: list[float] = []
    lats: list[float] = []
    for ring in _rings(geometry):
        for position in ring:
            if not position or len(position) < 2:
                continue
            try:
                lons.append(float(position[0]))
                lats.append(float(position[1]))
            except (TypeError, ValueError):
                continue
    if not lons:
        return None
    return (min(lons), min(lats), max(lons), max(lats))


def compare_boundary(local: dict, cloud: dict) -> dict:
    """Compare the mirror's outline with the upstream's.

    ``local`` is the mirror's row (with its full-resolution outline) and
    ``cloud`` is the upstream's boundary payload — the geometry and the
    properties.

    The comparison is deliberately about *measurements* rather than bytes: the
    extent, the area, and the number of vertices. Two different algorithms
    that produce the same shape produce the same measurements, which is what
    makes this comparison worth making.
    """
    fields: dict[str, dict] = {}

    properties = (cloud or {}).get("properties") or {}
    geometry = (cloud or {}).get("geometry") or {}

    for field in ("name", "kind", "source", "license"):
        left = local.get(field)
        right = properties.get(field)
        if not same(field, left, right):
            fields[field] = {"local": left, "cloud": right}

    # The area. The mirror's figure was copied from the upstream's own, so
    # they are the same number; a relative tolerance covers a recomputation.
    left_area = local.get("area_km2")
    right_area = properties.get("area_km2")
    if left_area is None or right_area is None:
        if (left_area is None) != (right_area is None):
            fields["area_km2"] = {"local": left_area, "cloud": right_area}
    else:
        try:
            span = max(abs(float(left_area)), abs(float(right_area)), 1e-9)
            if abs(float(left_area) - float(right_area)) / span > AREA_RELATIVE_TOLERANCE:
                fields["area_km2"] = {"local": left_area, "cloud": right_area}
        except (TypeError, ValueError):
            fields["area_km2"] = {"local": left_area, "cloud": right_area}

    # The vertices. Both sides are counted the same way — from their own
    # geometry — so the comparison is between two shapes and not between a
    # shape and a number the upstream happens to report. A GeoJSON ring
    # repeats its first point, so the ring count comes off first.
    local_vertices = geometry_points(local.get("geometry")) - geometry_rings(local.get("geometry"))
    cloud_vertices = geometry_points(geometry) - geometry_rings(geometry)
    if local_vertices != cloud_vertices:
        fields["vertex_count"] = {"local": local_vertices, "cloud": cloud_vertices}

    # The extent.
    local_bbox = geometry_bbox(local.get("geometry"))
    cloud_bbox = geometry_bbox(geometry)
    if (local_bbox is None) != (cloud_bbox is None):
        fields["bbox"] = {"local": local_bbox, "cloud": cloud_bbox}
    elif local_bbox is not None and cloud_bbox is not None:
        if any(abs(a - b) > COORDINATE_TOLERANCE for a, b in zip(local_bbox, cloud_bbox)):
            fields["bbox"] = {"local": list(local_bbox), "cloud": list(cloud_bbox)}

    return {"only_local": [], "only_cloud": [], "differing": fields}


# ── writing it down ─────────────────────────────────────────────────────────

async def record(
    db: AsyncSession,
    surface: str,
    local_rows: Sequence[dict],
    cloud_rows: Sequence[dict],
    params: dict | None = None,
    *,
    local_complete: bool = True,
    cloud_complete: bool = True,
    fields: Sequence[str] = COMPARABLE_FIELDS,
) -> CloudParityCheck:
    """Compare two answers and write the comparison down.

    A comparison where either side was truncated is recorded as ``partial``:
    the difference is not written, because a truncated answer cannot tell
    "upstream lost this row" from "the page stopped here".
    """
    result = compare(local_rows, cloud_rows, fields)
    return await record_result(
        db, surface, result,
        local_count=len(local_rows), cloud_count=len(cloud_rows),
        params=params, complete=bool(local_complete and cloud_complete),
    )


async def record_result(
    db: AsyncSession,
    surface: str,
    result: dict,
    *,
    local_count: int,
    cloud_count: int,
    params: dict | None = None,
    complete: bool = True,
) -> CloudParityCheck:
    """Write a comparison that was computed elsewhere.

    The boundary comparison does not go through :func:`compare` — it
    compares shapes, not rows — so it hands its result here.
    """
    status, result = decide(result, complete)

    row = CloudParityCheck(
        surface=surface,
        status=status,
        local_count=local_count,
        cloud_count=cloud_count,
        only_local=result.get("only_local") or [],
        only_cloud=result.get("only_cloud") or [],
        differing=result.get("differing") or {},
        params=params or {},
    )
    db.add(row)
    await db.commit()
    if row.status == "differ":
        logger.warning(
            "cloud parity: %s differs — %d only-local, %d differing",
            surface, len(row.only_local), len(row.differing))
    return row


async def record_error(
    db: AsyncSession,
    surface: str,
    error: str,
    params: dict | None = None,
) -> CloudParityCheck:
    """Record a comparison that could not be made.

    A failed comparison is not a clean one. Writing it down is what stops a
    quiet upstream outage from looking like an empty ledger.
    """
    row = CloudParityCheck(
        surface=surface,
        status="error",
        local_count=0,
        cloud_count=0,
        only_local=[],
        only_cloud=[],
        differing={},
        params=params or {},
        error=error[:4000],
    )
    db.add(row)
    await db.commit()
    logger.warning("cloud parity: %s could not be compared — %s", surface, error)
    return row


__all__ = [
    "compare", "compare_boundary", "is_clean", "record", "record_error",
    "record_result", "same", "geometry_points", "geometry_rings", "geometry_bbox",
    "COMPARABLE_FIELDS", "DETAIL_FIELDS", "COORDINATE_TOLERANCE",
]
