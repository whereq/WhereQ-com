"""Read the schools from whereq.cloud instead of from whereq.com's own tables.

THE TWO COPIES
--------------
whereq.com holds twelve ``school*`` tables, filled by its own board crawl
and its own HouseSigma import. whereq.cloud holds the same rows — and
**more of them, and fresher**: the platform collects the boards live now,
so its copy moves, while this app's crawler has been cut and its tables
are frozen. At the time of writing, whereq.cloud holds 2 647 schools
against this app's 2 528, and its ``school_version`` history is 822 rows
longer.

This app's tables are therefore the **legacy mirror**: kept, not deleted,
and no longer read for a response in production (``SCHOOL_READ_MODE`` is
``cloud`` there). This module reads the **platform's** copy.

THE KEY IS THE UID
------------------
A school's uid is ``<board-slug>/<school-code>`` — ``ycdsb/0158`` — and it
is the only identifier both systems agree on. The platform's uid always
carries a slash: the board's slug, or the province's code for a school with
no board. The uid is what the platform's own routes take, so a detail
lookup is one call with no translation.

**The row id is the join key, not the identifier.** The import preserved
whereq.com's own integers, so id 5 is ``dcdsb/austin`` in both databases.
That is what lets the local layer be seeded from the platform and what
lets the dual-read window know that the school it holds locally is the
school the platform holds. It is *not* what a caller keys on: the id
changes if the dataset is reloaded, the uid does not.

THE SHAPES ARE NOT THE SAME
----------------------------
The upstream's school is a flat row with a nested board; whereq.com's
``SchoolSummary`` is a flatter row with a nested board that carries an
integer id the upstream does not have. The upstream's taxonomy calls the
programmes ``program_categories`` and counts them ``count``; whereq.com's
taxonomy calls them ``programs`` and counts them ``school_count``. The
upstream's pagination carries ``offset``; whereq.com's routes take
``page`` and ``page_size``.

So this module is a **translator**, not a proxy: it re-shapes the
upstream's answer into the shapes this app's routes already return. The
app's own API contract does not change because the upstream's does.

WHAT THE UPSTREAM DOES NOT HAVE
--------------------------------
* **A country.** The schools are all Canadian; the upstream's province
  filter is the province code, which is what whereq.com's own routes
  already use.
* **The HouseSigma board type on the summary.** It is on the *detail*, and
  whereq.com's own summary did not carry it either — its detail did, and
  so does the upstream's.

THE QUOTA IS THE REASON THIS IS CAREFUL
----------------------------------------
The API allows 30 requests a minute and whereq.com's own throttle shares
that budget with the fuel feed. The school directory is 2 528 rows, so it
fits in **one** call — the whole point of the upstream's 5 000-row limit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import whereq_cloud

from app.services.whereq_cloud_client import (
    call_with_retry,
    client as _client,
    shared_throttle,
)

logger = logging.getLogger(__name__)

#: The upstream's own cap on one page. The whole directory is 2 528 rows,
#: so one call can carry all of them — which is the point.
MAX_LIMIT = 5000


@dataclass
class CloudSchools:
    """The upstream's answer to a schools request.

    ``complete`` is the field that matters: it says whether the **whole**
    upstream population for the filters was fetched. A comparison against a
    truncated answer cannot tell "upstream lost this school" from "the
    page stopped here", so a truncated answer is never evidence — not a
    defect, and not a clean match either.

    ``rows`` is the answer in this app's summary shape; ``raw`` is the
    upstream's own rows. The comparison is made against the **raw** rows,
    because the summary is a re-shaping and a re-shaping drops fields — and
    a field the summary drops would read as "the upstream lost it".
    """

    rows: list[dict] = field(default_factory=list)
    #: The upstream's rows, untouched.
    raw: list[dict] = field(default_factory=list)
    #: The upstream's own count of the rows matching the filters, when it
    #: told us. ``None`` means it did not, and the answer is not evidence.
    total: int | None = None
    #: True when every matching upstream row was fetched.
    complete: bool = False


#: The fields the comparison looks at, flat on purpose. The board is
#: compared by its slug, name, type and region rather than as a nested
#: object, because a nested object compares by identity and would report a
#: difference for every school.
COMPARABLE_FIELDS = (
    "name", "type", "status", "province", "region", "city", "municipality",
    "grade_range", "programs", "has_boundary", "lat", "lng",
    "hs_score", "hs_rank", "hs_rank_total", "hs_school_type",
    "board_slug", "board_name", "board_type", "board_region",
)


def school_to_read(row: dict) -> dict:
    """An upstream school in the flat shape the comparison uses.

    This is the same shape the local side produces, so the two are
    comparable field by field.
    """
    board = row.get("board") or {}
    return {
        "uid": row.get("uid"),
        "id": row.get("id"),
        "name": row.get("name"),
        "type": row.get("type"),
        "status": row.get("status"),
        "province": row.get("province"),
        "region": row.get("region"),
        "city": row.get("city"),
        "municipality": row.get("municipality"),
        "grade_range": row.get("grade_range"),
        # Sorted: the programmes come back from the upstream in code order
        # and from the local database in whatever order the join produced,
        # and a comparison that is sensitive to the order would report a
        # difference for every school with more than one programme.
        "programs": sorted(row.get("programs") or []),
        "has_boundary": bool(row.get("has_boundary")),
        "lat": row.get("latitude"),
        "lng": row.get("longitude"),
        "hs_score": row.get("hs_score"),
        "hs_rank": row.get("hs_rank"),
        "hs_rank_total": row.get("hs_rank_total"),
        "hs_school_type": row.get("hs_school_type"),
        "board_slug": board.get("slug"),
        "board_name": board.get("name"),
        "board_type": board.get("type"),
        "board_region": board.get("region"),
    }


def _board(board: dict | None) -> dict | None:
    """The board block, in this app's shape.

    The upstream's board has no integer id — its slug is the key — so the
    app's board block carries the slug where it used to carry the id. The
    frontend never used the id; it used the name and the type.
    """
    if not board:
        return None
    return {
        "slug": board.get("slug"),
        "name": board.get("name"),
        "type": board.get("type"),
        "region": board.get("region"),
    }


def school_to_summary(row: dict) -> dict:
    """An upstream school as this app's summary shape."""
    return {
        "uid": row.get("uid"),
        "name": row.get("name"),
        "type": row.get("type"),
        "province": row.get("province"),
        # The board's region — the upstream's own `region` field is the
        # board's, and it is what the app's region filter matches.
        "region": row.get("region"),
        "city": row.get("city"),
        "lat": row.get("latitude"),
        "lng": row.get("longitude"),
        "hs_score": row.get("hs_score"),
        "hs_rank": row.get("hs_rank"),
        "hs_rank_total": row.get("hs_rank_total"),
        "grade_range": row.get("grade_range"),
        "board": _board(row.get("board")),
        "programs": list(row.get("programs") or []),
        "has_boundary": bool(row.get("has_boundary")),
    }


def school_to_detail(row: dict) -> dict:
    """An upstream school as this app's detail shape.

    The upstream's score history carries the EQAO marks **inside** each
    year; this app's detail carries them as their own list. So they are
    flattened here — one EQAO row per mark, with the year it belongs to.
    """
    detail = school_to_summary(row)
    detail.update({
        "status": row.get("status"),
        "address": row.get("address"),
        "municipality": row.get("municipality"),
        "phone": row.get("phone"),
        "phone2": row.get("phone2"),
        "fax": row.get("fax"),
        "website_url": row.get("website_url"),
        "boundary_pdf_url": row.get("boundary_pdf_url"),
        "principal": row.get("principal"),
        "feeder_schools": row.get("feeder_schools"),
        "hs_name": row.get("hs_name"),
        "hs_board_type": row.get("hs_board_type"),
        "hs_school_type": row.get("hs_school_type"),
        "hs_score_year": row.get("hs_score_year"),
        "hs_score_average": row.get("hs_score_average"),
        "hs_rank_year": row.get("hs_rank_year"),
    })

    scores: list[dict] = []
    eqao: list[dict] = []
    for score in row.get("scores") or []:
        scores.append({
            "year": score.get("year"),
            "rank": score.get("rank"),
            "rank_total": score.get("rank_total"),
            "rank_score": score.get("rank_score"),
            "avg_exam_mark": score.get("avg_exam_mark"),
        })
        for mark in score.get("eqao") or []:
            eqao.append({
                "grade": mark.get("grade"),
                "year_mark": mark.get("year_mark"),
                "rank": mark.get("rank"),
                "total": mark.get("total"),
                "last5_avg": mark.get("last5_avg"),
            })
    detail["scores"] = scores
    detail["eqao"] = eqao
    return detail


def taxonomy_to_local(payload: dict) -> dict:
    """The upstream's taxonomy in this app's shape.

    The upstream calls the programmes ``program_categories`` and counts
    everything ``count``; this app calls them ``programs`` and counts them
    ``school_count``. The province rows also carry an ``enabled`` flag,
    which the app's own taxonomy has always had.
    """
    payload = payload or {}
    provinces = [
        {"id": p.get("id"), "name": p.get("name"),
         "school_count": p.get("count") or 0, "enabled": True}
        for p in payload.get("provinces") or []
    ]
    regions = [
        {"id": r.get("id"), "name": r.get("name"), "province": r.get("province"),
         "school_count": r.get("count") or 0}
        for r in payload.get("regions") or []
    ]
    boards = [
        {"slug": b.get("slug"), "name": b.get("name"), "type": b.get("type"),
         "region": b.get("region"), "province": b.get("province"),
         "school_count": b.get("school_count") or 0}
        for b in payload.get("boards") or []
    ]
    types = [
        {"id": t.get("id"), "name": (t.get("name") or t.get("id") or "").title(),
         "school_count": t.get("count") or 0}
        for t in payload.get("types") or []
    ]
    board_types = [
        {"id": t.get("id"), "name": (t.get("name") or t.get("id") or "").title(),
         "school_count": t.get("count") or 0}
        for t in payload.get("board_types") or []
    ]
    programs = [
        {"id": p.get("id"), "name": p.get("name") or p.get("id"),
         "school_count": p.get("count") or 0}
        for p in payload.get("program_categories") or []
    ]
    return {
        "provinces": provinces,
        "regions": regions,
        "boards": boards,
        "types": types,
        "board_types": board_types,
        "programs": programs,
    }


def stats_to_local(payload: dict) -> dict:
    """The upstream's stats block in this app's shape."""
    stats = (payload or {}).get("stats") or {}
    return {
        "total": stats.get("total_schools") or 0,
        "with_boundary": stats.get("schools_with_boundary") or 0,
        "by_province": [
            {"id": r.get("id"), "count": r.get("count") or 0}
            for r in stats.get("by_province") or []
        ],
        "by_board_type": [
            {"id": r.get("id"), "count": r.get("count") or 0}
            for r in stats.get("by_board_type") or []
        ],
        "by_type": [
            {"id": r.get("id"), "count": r.get("count") or 0}
            for r in stats.get("by_type") or []
        ],
    }


def _filters(
    *, q=None, board=None, board_type=None, region=None, city=None,
    province=None, type=None, program=None, bbox=None, has_boundary=None,
    sort=None, order=None, rank=None,
) -> dict:
    """The upstream's parameters for this app's filters.

    The province goes up upper-cased: this app's own route upper-cases it
    (``Province.code == province.upper()``), and the upstream matches the
    code exactly. Sending ``on`` must find Ontario on both sides.
    """
    out: dict[str, Any] = {}
    if q:
        out["q"] = q
    if board:
        out["board"] = board
    if board_type:
        out["board_type"] = board_type
    if region:
        out["region"] = region
    if city:
        out["city"] = city
    if province:
        out["province"] = province.upper()
    if type:
        out["type"] = type
    if program:
        out["program"] = program
    if bbox:
        out["bbox"] = bbox
    if has_boundary is not None:
        out["has_boundary"] = has_boundary
    if sort:
        out["sort"] = sort
    if order:
        out["order"] = order
    if rank:
        out["rank"] = True
    return out


def fetch_cloud_schools(
    *,
    q: str | None = None,
    board: str | None = None,
    board_type: str | None = None,
    region: str | None = None,
    city: str | None = None,
    province: str | None = None,
    type: str | None = None,
    program: str | None = None,
    bbox: str | None = None,
    has_boundary: bool | None = None,
    sort: str | None = None,
    order: str | None = None,
    rank: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CloudSchools:
    """The upstream's answer to a schools request.

    Returns the rows in this app's summary shape, plus whether the whole
    upstream population was fetched. Raises ``whereq_cloud.WhereqError`` if
    upstream cannot be read — the caller decides whether that is a failure
    or a reason to fall back.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(
            client.schools,
            limit=limit, offset=offset,
            **_filters(q=q, board=board, board_type=board_type, region=region,
                       city=city, province=province, type=type, program=program,
                       bbox=bbox, has_boundary=has_boundary, sort=sort,
                       order=order, rank=rank),
        )
    finally:
        client.close()

    payload = payload or {}
    items = payload.get("data") or []
    pagination = payload.get("pagination") or {}
    total = pagination.get("total")
    rows = [school_to_summary(item) for item in items]
    # The answer is whole when the upstream's own count says so: it counted
    # the rows that match, and we asked for as many as it is willing to
    # give, so if we got its count, we got them all.
    complete = total is not None and len(items) >= int(total)
    return CloudSchools(rows=rows, raw=list(items),
                        total=int(total) if total is not None else None,
                        complete=complete)


def fetch_cloud_school(uid: str) -> dict | None:
    """One school from upstream, in this app's detail shape.

    ``None`` means **upstream does not have this school** — which is a real
    difference (the local copy has something the original lost), not an
    error.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.school, uid=uid)
    except whereq_cloud.WhereqError as exc:
        if exc.status == 404:
            return None
        raise
    finally:
        client.close()
    school = (payload or {}).get("data") or payload or {}
    if not school:
        return None
    return school_to_detail(school)


def fetch_cloud_school_boundary(uid: str) -> dict | None:
    """One school's catchment outline from upstream.

    ``None`` means upstream has no outline for this school — which the
    local route answers with a 404, not with an empty shape.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.school_boundary, uid=uid)
    except whereq_cloud.WhereqError as exc:
        if exc.status == 404:
            return None
        raise
    finally:
        client.close()
    payload = payload or {}
    geometry = payload.get("geometry")
    if not geometry:
        return None
    return {
        "uid": payload.get("uid"),
        "name": payload.get("name"),
        "geometry": geometry,
        "polygon_count": payload.get("polygon_count") or 0,
        "point_count": payload.get("point_count") or 0,
    }


def fetch_cloud_schools_at(lat: float, lng: float) -> list[dict]:
    """The catchments that cover a point, from upstream.

    **Licensed.** The upstream's route needs the ``school_licensed`` scope,
    which this app's key holds.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.schools_at, lat=lat, lng=lng, limit=100)
    finally:
        client.close()
    items = (payload or {}).get("data") or []
    return [
        {
            "uid": item.get("uid"),
            "name": item.get("name"),
            "type": item.get("type"),
            "board": item.get("board"),
            "polygon_index": item.get("polygon_index") or 0,
        }
        for item in items
    ]


def fetch_cloud_taxonomy() -> tuple[dict, dict]:
    """The upstream's taxonomy: this app's taxonomy shape, and its stats."""
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.school_taxonomy)
    finally:
        client.close()
    payload = payload or {}
    return taxonomy_to_local(payload), stats_to_local(payload)


__all__ = [
    "CloudSchools", "COMPARABLE_FIELDS", "MAX_LIMIT",
    "school_to_read", "school_to_summary", "school_to_detail",
    "taxonomy_to_local", "stats_to_local",
    "fetch_cloud_schools", "fetch_cloud_school", "fetch_cloud_school_boundary",
    "fetch_cloud_schools_at", "fetch_cloud_taxonomy",
]
