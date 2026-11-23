"""Compare whereq.com's schools with whereq.cloud's, one surface at a time.

THE WINDOW NEEDS EVIDENCE ON EVERY SURFACE
-------------------------------------------
The directory list is one surface. The app also serves a school's **detail**,
its **catchment outline**, the catchments that cover a **point** and the whole
**taxonomy** — and a cut that only proves the list is not a cut that is proven.

Each surface is compared **like with like**: the two answers are put in the
same shape first, and only then compared field by field. A surface whose two
shapes cannot be put in the same shape is not compared at all — comparing two
different shapes reports differences that are not differences, and a ledger
full of those teaches its reader to ignore it.

THE BOUNDARY IS COMPARED BY ITS MEASUREMENTS
---------------------------------------------
A catchment outline is a JSONB document on one side and a GeoJSON document on
the other, and JSONB does not preserve key order or number formatting, so two
identical shapes have two different texts. The two outlines are therefore
compared by **what they are** — how many polygons, how many vertices, and how
large an area they cover — and not by a digest of their bytes.

THE POINT-IN-CATCHMENT SURFACE HAS A KNOWN DIFFERENCE
-----------------------------------------------------
This app's own query uses ``ST_Contains`` — a point exactly on a catchment's
edge belongs to nobody — while the upstream uses ``ST_Covers``, which
includes the edge. The upstream's rule is the correct one, so a point exactly
on a boundary is a **real** difference, and it is recorded as one rather than
smoothed away.

THE KEY IS THE UID
------------------
A school is identified by its **uid** — ``ycdsb/0158`` — and the uid is the
key the two systems agree on. A catchment can be several polygons, so the
point-in-catchment comparison keys on the uid **and** the polygon index:
``ycdsb/0158#0`` and ``ycdsb/0158#1`` are two shapes, not one.
"""

from __future__ import annotations

from typing import Any

from app.services.cloud_parity import geometry_bbox, geometry_points, geometry_rings, same

#: The fields a school detail shows, and so the fields the detail comparison
#: looks at. ``boundary_geojson`` is not here: the outline has its own
#: surface, and comparing it twice would report the same difference twice.
DETAIL_FIELDS = (
    "name", "type", "status", "province", "region", "city", "municipality",
    "grade_range", "programs", "has_boundary", "lat", "lng",
    "hs_score", "hs_rank", "hs_rank_total", "hs_school_type",
    "address", "phone", "phone2", "fax", "website_url", "boundary_pdf_url",
    "principal", "hs_name", "hs_board_type", "hs_score_year",
    "hs_score_average", "hs_rank_year", "feeder_schools", "scores", "eqao",
    "board",
)

#: The fields one catchment hit shows.
AT_FIELDS = ("name", "type", "board", "polygon_index")

#: The fields one catchment outline shows, and the two measurements that say
#: whether two outlines are the same shape.
BOUNDARY_FIELDS = (
    "name", "polygon_count", "point_count", "vertex_count", "bbox",
)

#: The taxonomy's groups, and the field each group is keyed on. The boards
#: are keyed by their **slug**; everything else is keyed by its id.
TAXONOMY_GROUPS = ("provinces", "regions", "boards", "types", "board_types", "programs")
TAXONOMY_KEY = {"boards": "slug"}

#: The fields compared inside each taxonomy group.
TAXONOMY_FIELDS = {
    "provinces": ("name", "school_count"),
    "regions": ("name", "province", "school_count"),
    "boards": ("name", "type", "region", "province", "school_count"),
    "types": ("name", "school_count"),
    "board_types": ("name", "school_count"),
    "programs": ("name", "school_count"),
}

#: The stats' groups, and the field each is keyed on.
STATS_GROUPS = ("by_province", "by_board_type", "by_type")

#: The stats' own headline numbers, which sit beside the groups.
STATS_SCALARS = ("total", "with_boundary")

#: The fields compared inside each stats group.
STATS_FIELDS = ("count",)


def _sorted_programmes(value: Any) -> Any:
    """The programmes, in code order.

    The programmes come back from the upstream in code order and from the
    local database in whatever order the join produced, and a comparison
    that was sensitive to the order would report a difference for every
    school with more than one programme.
    """
    if isinstance(value, (list, tuple)):
        return sorted(value)
    return value


def _sorted_scores(value: Any) -> Any:
    """The score history, oldest first."""
    if not isinstance(value, (list, tuple)):
        return value
    return sorted(
        (dict(row) for row in value),
        key=lambda row: (row.get("year") is None, row.get("year")),
    )


def _sorted_eqao(value: Any) -> Any:
    """The EQAO marks, by grade and then by the year they belong to."""
    if not isinstance(value, (list, tuple)):
        return value
    return sorted(
        (dict(row) for row in value),
        key=lambda row: (row.get("grade") is None, row.get("grade"),
                         row.get("year_mark") or ""),
    )


def _board(value: Any) -> Any:
    """The board block, flattened to the four fields it has.

    The board is compared as its own fields rather than as a nested object:
    a nested object compares by identity, and two copies of the same board
    are two different objects.
    """
    if not isinstance(value, dict):
        return value
    return {key: value.get(key) for key in ("slug", "name", "type", "region")}


#: How each field of a detail is normalised before it is compared.
_DETAIL_NORMALISERS = {
    "programs": _sorted_programmes,
    "scores": _sorted_scores,
    "eqao": _sorted_eqao,
    "board": _board,
}


def detail_to_read(detail: dict | None) -> dict | None:
    """One school detail, in the shape the comparison uses.

    ``None`` in, ``None`` out: the upstream does not have this school, which
    is a difference and not an error.
    """
    if detail is None:
        return None
    out: dict[str, Any] = {}
    for field in DETAIL_FIELDS:
        value = detail.get(field)
        normaliser = _DETAIL_NORMALISERS.get(field)
        out[field] = normaliser(value) if normaliser else value
    return out


def at_to_read(hit: dict) -> dict:
    """One catchment hit, in the shape the comparison uses.

    The key carries the polygon index, because a catchment can be several
    polygons and they are several shapes.
    """
    return {
        "uid": f"{hit.get('uid')}#{hit.get('polygon_index') or 0}",
        "name": hit.get("name"),
        "type": hit.get("type"),
        "board": hit.get("board"),
        "polygon_index": hit.get("polygon_index") or 0,
    }


def boundary_to_read(boundary: dict | None, uid: str | None = None) -> dict | None:
    """One catchment outline, in the shape the comparison uses.

    The two measurements come off **each side's own geometry**, so the
    comparison is between two shapes and not between a shape and a number the
    upstream happens to report. A GeoJSON ring repeats its first position,
    so the vertex count is the position count minus the ring count.
    """
    if boundary is None:
        return None
    geometry = boundary.get("geometry") or {}
    return {
        "uid": uid or boundary.get("uid") or boundary.get("school_uid"),
        "name": boundary.get("name"),
        "polygon_count": boundary.get("polygon_count") or 0,
        "point_count": boundary.get("point_count") or 0,
        "vertex_count": geometry_points(geometry) - geometry_rings(geometry),
        "bbox": list(geometry_bbox(geometry) or ()),
    }


def _grouped_difference(
    left_groups: dict[str, list[dict]],
    right_groups: dict[str, list[dict]],
    groups: tuple[str, ...],
    key_field: str,
    fields: dict[str, tuple[str, ...]],
) -> dict:
    """Compare two sets of groups, row by row, key by key.

    Returns the difference in the shape the ledger holds: the groups that
    disagree, and inside them the rows that disagree and the fields that
    disagree within a row.
    """
    differing: dict[str, Any] = {}
    for group in groups:
        key_of = key_field.get(group, "id")
        left = {str(row.get(key_of)): row for row in (left_groups.get(group) or [])}
        right = {str(row.get(key_of)): row for row in (right_groups.get(group) or [])}

        entry: dict[str, Any] = {}
        only_local = sorted(set(left) - set(right))
        only_cloud = sorted(set(right) - set(left))
        if only_local:
            entry["only_local"] = only_local
        if only_cloud:
            entry["only_cloud"] = only_cloud

        for key in sorted(set(left) & set(right)):
            fields_out = {}
            for field in fields.get(group, ()):
                if not same(field, left[key].get(field), right[key].get(field)):
                    fields_out[field] = {
                        "local": left[key].get(field),
                        "cloud": right[key].get(field),
                    }
            if fields_out:
                entry[key] = fields_out

        if entry:
            differing[group] = entry
    return {"only_local": [], "only_cloud": [], "differing": differing}


def compare_taxonomies(local: dict | None, cloud: dict | None) -> dict:
    """Compare two taxonomies, group by group.

    A row the upstream has and the mirror does not is a **difference** here,
    not the mirror's coverage: the school copy is meant to be the whole
    directory, so a province the mirror cannot name is a hole in the copy.
    """
    return _grouped_difference(
        local or {}, cloud or {}, TAXONOMY_GROUPS, TAXONOMY_KEY, TAXONOMY_FIELDS,
    )


def compare_stats(local: dict | None, cloud: dict | None) -> dict:
    """Compare two stats blocks, group by group.

    The headline numbers are compared too: the two sides' totals are the
    one figure that says, at a glance, whether the two copies hold the same
    number of schools.
    """
    local = local or {}
    cloud = cloud or {}
    result = _grouped_difference(
        local, cloud, STATS_GROUPS, {}, {g: STATS_FIELDS for g in STATS_GROUPS},
    )
    scalars = {}
    for field in STATS_SCALARS:
        if not same(field, local.get(field), cloud.get(field)):
            scalars[field] = {"local": local.get(field), "cloud": cloud.get(field)}
    if scalars:
        result["differing"]["counts"] = scalars
    return result


__all__ = [
    "DETAIL_FIELDS", "AT_FIELDS", "BOUNDARY_FIELDS",
    "TAXONOMY_GROUPS", "TAXONOMY_FIELDS", "STATS_GROUPS",
    "detail_to_read", "at_to_read", "boundary_to_read",
    "compare_taxonomies", "compare_stats",
]
