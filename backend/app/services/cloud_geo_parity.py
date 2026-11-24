"""Compare whereq.com's geography outlines with whereq.cloud's.

THE OUTLINE IS COMPARED BY ITS MEASUREMENTS
--------------------------------------------
An outline is a shape, not a row, and the two sides' shapes do not have the
same text: the local copy comes out of a PostGIS column and the upstream's
comes out of PostGIS too, but through a different simplification and a
different serialiser. Two identical shapes have two different texts, so a
digest of the bytes would report differences that are not differences.

They are therefore compared by **what they are**:

* how many polygons the shape has,
* how many vertices it has,
* how large an area it covers,
* and where it is.

THE ATTRIBUTION IS COMPARED TOO
------------------------------
The open licences require the attribution to travel with the data, and the
local copy carried ``license`` and ``source_url`` on every outline. The
upstream does too. A difference here is a real difference — it means one
side cannot be attributed — so it is compared like any other field.

THE LARGE KINDS ARE EXCLUDED ON BOTH SIDES
-------------------------------------------
This app's own rule is that a viewport's worth of outlines leaves out the
country, the province and the state: those cover the whole viewport and are
never what a map draws. The upstream is asked for the same exclusion, so the
two answers are the same set of rows and the comparison is like with like.
"""

from __future__ import annotations

from typing import Any

from app.services.cloud_parity import (
    compare,
    geometry_bbox,
    geometry_points,
    geometry_rings,
)

#: The fields two outlines are compared on.
BOUNDARY_FIELDS = (
    "kind",
    "polygon_count",
    "vertex_count",
    "area_km2",
    "bbox",
    "license",
    "source_url",
)

#: The concepts this app leaves out of a viewport's worth of outlines.
LARGE_KINDS = ("country", "province", "state")


def boundary_to_read(item: dict | None) -> dict | None:
    """One outline, in the shape the comparison uses.

    The vertex count is the position count minus the ring count: a GeoJSON
    ring repeats its first position, so counting positions would count the
    closing point twice.
    """
    if not item:
        return None
    geometry = item.get("geometry") or {}
    return {
        "uid": item.get("uid"),
        "kind": item.get("kind"),
        "polygon_count": len(geometry.get("coordinates") or [])
        if geometry.get("type") == "MultiPolygon" else (1 if geometry.get("coordinates") else 0),
        "vertex_count": geometry_points(geometry) - geometry_rings(geometry),
        "area_km2": item.get("area_km2"),
        "bbox": list(geometry_bbox(geometry) or ()),
        "license": item.get("license"),
        "source_url": item.get("source_url"),
    }


def boundaries_to_read(items: list[dict] | None) -> list[dict]:
    """Every outline, in the shape the comparison uses."""
    out = []
    for item in items or []:
        read = boundary_to_read(item)
        if read:
            out.append(read)
    return out


def compare_boundaries(local: list[dict], cloud: list[dict]) -> dict:
    """The difference between two sets of outlines.

    The result is the shape a ``cloud_parity_checks`` row holds: the uids
    only one side has, and the fields that disagree within the uids both
    sides have.
    """
    return compare(
        boundaries_to_read(local),
        boundaries_to_read(cloud),
        fields=BOUNDARY_FIELDS,
    )


__all__ = [
    "BOUNDARY_FIELDS",
    "LARGE_KINDS",
    "boundary_to_read",
    "boundaries_to_read",
    "compare_boundaries",
]
