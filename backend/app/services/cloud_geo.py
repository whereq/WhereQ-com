"""Read the geography from whereq.cloud instead of from the local mirror.

THE MIRROR
----------
whereq.com keeps its own ``geo_places`` table, filled by its own crawler
from whereq.cloud's ``/v1/geo/places``. It is a **copy**: the same rows,
under the same uids, from the same upstream. The migration's job is to stop
keeping the copy and start reading the original.

THE SHAPES ARE THE SAME
-----------------------
The upstream place carries the same field names the local table's columns
carry, because whereq.com's own ``place_to_row()`` copied them from there.
So the join key is the **uid** — ``osm:r188972``, ``wb:…`` — and it is the
same string on both sides. That is what makes the comparison possible.

Two filters do not line up one-to-one, and the reader has to bridge them:

* ``kind`` and ``source`` are single values upstream and comma-separated
  lists here. Upstream has no "in" filter, so the reader issues one request
  per combination and merges the answers — which is exactly the same set the
  local ``IN (...)`` filter selects.
* The upstream page size is 200 (the SDK's own cap), so a larger answer is
  paged.

The quota is the reason this is careful rather than quick: the API allows
30 requests a minute, and whereq.com's own throttle already shares that
budget with the fuel feed.

COMPLETENESS IS THE POINT
-------------------------
A comparison is only evidence when both sides were fetched **whole**. The
upstream holds 32 954 places; the mirror holds the 304 of them that fall
inside whereq.com's coverage targets. Comparing the mirror against the
upstream's *first* 500 rows compares two different populations, and every
mirror row outside that page looks like a place the upstream lost — 294
false defects out of 304.

So the reader reports whether it got the whole upstream answer, and the
comparator refuses to call a difference when it did not. A truncated answer
is **inconclusive**, never a defect and never a clean match.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

import whereq_cloud

from app.services.whereq_cloud_client import (
    call_with_retry,
    client as _client,
    shared_throttle,
)

logger = logging.getLogger(__name__)

#: The upstream page size — the SDK's own maximum per request.
PAGE_SIZE = 200

#: The most rows one reader call will ask for. whereq.com's own route
#: allows 5000, but 5000 rows is 25 upstream requests, and at 30 requests a
#: minute that is most of a minute of latency. The reader does not refuse a
#: larger limit — it asks for what it can get, in pages, and stops.
MAX_ROWS = 2000


@dataclass
class CloudPlaces:
    """The upstream's answer to a places request.

    ``complete`` is the field that matters: it says whether the **whole**
    upstream population for the filters was fetched. A comparison against a
    truncated answer cannot tell "upstream lost this place" from "the page
    stopped here", so a truncated answer is never evidence — not a defect,
    and not a clean match either.
    """

    rows: list[dict] = field(default_factory=list)
    #: The upstream's own count of the rows matching the filters, when it
    #: told us. ``None`` means it did not, and the answer is not evidence.
    total: int | None = None
    #: True when every matching upstream row was fetched.
    complete: bool = False


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def _combinations(kinds: list[str], sources: list[str]) -> list[tuple[str | None, str | None]]:
    """The (kind, source) pairs to ask upstream for.

    An empty list on either side means "unfiltered", which upstream
    expresses by omitting the parameter.
    """
    kind_list: Iterable[str | None] = kinds or [None]
    source_list: Iterable[str | None] = sources or [None]
    return [(k, s) for k in kind_list for s in source_list]


def _place_to_read(place: dict) -> dict:
    """An upstream place as the shape this app's reader returns.

    The field names are the same on both sides — that is the whole point of
    ``place_to_row()`` having copied them — so this is a shape fix, not a
    translation.
    """
    return {
        "uid": place.get("uid"),
        "kind": place.get("kind"),
        "name": place.get("name"),
        "name_en": place.get("name_en"),
        "name_zh": place.get("name_zh"),
        "name_local": place.get("name_local"),
        "official_name": place.get("official_name"),
        "source": place.get("source"),
        "source_url": place.get("source_url"),
        "license": place.get("license"),
        "country_code": place.get("country_code"),
        "province_code": place.get("province_code"),
        "population": place.get("population"),
        "area_km2": place.get("area_km2"),
        "centroid_lon": place.get("centroid_lon"),
        "centroid_lat": place.get("centroid_lat"),
        "has_boundary": bool(place.get("has_boundary")),
    }


#: The fields the detail route returns beyond the listing's.
DETAIL_FIELDS = (
    "kind_source", "source_id", "raw_admin_level", "raw_place", "raw_boundary",
    "iso_code", "ref", "population_date", "wikidata", "wikipedia", "website",
    "capital", "bbox_min_lon", "bbox_min_lat", "bbox_max_lon", "bbox_max_lat",
)


def place_to_detail(place: dict) -> dict:
    """An upstream place as the shape this app's detail route returns."""
    out = _place_to_read(place)
    for field in DETAIL_FIELDS:
        out[field] = place.get(field)
    return out


def fetch_cloud_places(
    *,
    bbox: str | None = None,
    kinds: list[str] | None = None,
    sources: list[str] | None = None,
    q: str | None = None,
    has_boundary: bool | None = None,
    limit: int = 500,
) -> CloudPlaces:
    """The upstream's answer to a places request, merged and paged.

    Returns the rows in the shape this app's reader returns, plus whether the
    whole upstream population was fetched. Raises
    ``whereq_cloud.WhereqError`` if upstream cannot be read — the caller
    decides whether that is a failure or a reason to fall back.
    """
    limit = max(1, min(limit, MAX_ROWS))
    kinds = kinds or []
    sources = sources or []
    pairs = _combinations(kinds, sources)

    client = _client()
    rows: list[dict] = []
    seen: set[str] = set()
    totals: list[int] = []
    complete = True
    try:
        for kind, source in pairs:
            offset = 0
            pair_total: int | None = None
            while len(rows) < limit:
                page = min(PAGE_SIZE, limit - len(rows))
                shared_throttle.wait()
                payload = call_with_retry(
                    client.geo_places,
                    kind=kind, source=source, q=q, bbox=bbox,
                    has_boundary=has_boundary, limit=page, offset=offset,
                )
                items = (payload or {}).get("data") or []
                if pair_total is None:
                    # The upstream's count of everything matching these
                    # filters — the number the pages add up to.
                    pair_total = (payload or {}).get("count")
                if not items:
                    break
                for place in items:
                    row = _place_to_read(place)
                    uid = row.get("uid")
                    if uid and uid not in seen:
                        seen.add(uid)
                        rows.append(row)
                offset += len(items)
                if len(items) < page:
                    break          # the last page
            if pair_total is None:
                # The upstream did not say how big its answer is, so we cannot
                # know whether we got all of it. Not evidence.
                complete = False
            else:
                totals.append(int(pair_total))
                if offset < int(pair_total):
                    complete = False
    finally:
        client.close()

    return CloudPlaces(
        rows=rows[:limit],
        total=sum(totals) if totals else None,
        complete=complete,
    )


def fetch_cloud_place(uid: str) -> dict | None:
    """One place from upstream, in this app's detail shape.

    ``None`` means **upstream does not have this place** — which is a real
    difference (the mirror has something the original lost), not an error.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.geo_place, uid=uid)
    except whereq_cloud.WhereqError as exc:
        if exc.status == 404:
            return None
        raise
    finally:
        client.close()
    place = (payload or {}).get("place") or {}
    return place_to_detail(place) if place else None


def fetch_cloud_boundary(uid: str) -> dict | None:
    """One place's outline from upstream, at full resolution.

    Full resolution on purpose: the outline is compared against the mirror's
    own full-resolution outline, and a simplified shape would differ from it
    for reasons that have nothing to do with the data.

    ``None`` means upstream has no outline for this place.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.geo_boundary, uid=uid, simplify=0)
    except whereq_cloud.WhereqError as exc:
        if exc.status == 404:
            return None
        raise
    finally:
        client.close()
    features = (payload or {}).get("features") or []
    if not features:
        return None
    feature = features[0]
    return {
        "geometry": feature.get("geometry") or {},
        "properties": feature.get("properties") or {},
    }


def fetch_cloud_boundaries(
    bbox: str | None = None,
    kinds: list[str] | None = None,
    excluded_kinds: list[str] | None = None,
    sources: list[str] | None = None,
    simplify_m: float = 50.0,
    limit: int = 200,
) -> dict:
    """Every outline in a viewport, from upstream — in one request.

    This is the surface that lets the outlines be cut over. The upstream
    used to serve them one place at a time, so a map pan would have cost
    one request per polygon; it now serves a whole viewport's worth in one
    answer, with the simplification already applied.

    The upstream's item carries the same field names this app's
    ``GeoBoundaryRead`` carries — ``uid``, ``name``, ``kind``, ``source``,
    ``license``, ``source_url``, ``area_km2``, the centroid, and the
    geometry — so the answer is re-shaped by name, not by guessing.

    The **attribution travels with the shapes**: ``license`` and
    ``source_url`` are on every item, because the open licences require
    them and the local copy carried them too.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(
            client.geo_boundaries,
            bbox=bbox,
            kind=",".join(kinds) if kinds else None,
            exclude_kind=",".join(excluded_kinds) if excluded_kinds else None,
            source=",".join(sources) if sources else None,
            simplify_m=simplify_m,
            limit=limit,
        )
    finally:
        client.close()
    return payload or {}


def boundaries_to_read(payload: dict) -> list[dict]:
    """The upstream's outlines, in this app's reader shape.

    The field names already line up; this is the place where the licence
    and the attribution are made sure to be carried, because a reader that
    drops them would serve shapes nobody can attribute.
    """
    out: list[dict] = []
    for item in (payload or {}).get("items") or []:
        out.append({
            "uid": item.get("uid"),
            "name": item.get("name"),
            "kind": item.get("kind"),
            "source": item.get("source"),
            "license": item.get("license"),
            "source_url": item.get("source_url"),
            "area_km2": item.get("area_km2"),
            "centroid_lon": item.get("centroid_lon"),
            "centroid_lat": item.get("centroid_lat"),
            "simplified_m": item.get("simplified_m"),
            "geometry": item.get("geometry") or {},
        })
    return out


def fetch_cloud_at(lon: float, lat: float) -> dict:
    """Every place containing a point, from upstream.

    Upstream answers ``{lon, lat, count, places}``; this app's reader
    returns the same stack in its own shape.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.geo_at, lon=lon, lat=lat)
    finally:
        client.close()
    return payload or {}


def at_places_to_read(payload: dict) -> list[dict]:
    """The upstream's containment stack, in this app's reader shape."""
    out = []
    for place in (payload or {}).get("places") or []:
        out.append({
            "uid": place.get("uid"),
            "kind": place.get("kind"),
            "name": place.get("name"),
            "source": place.get("source"),
            "license": place.get("license"),
            "centroid_lon": place.get("centroid_lon"),
            "centroid_lat": place.get("centroid_lat"),
        })
    return out


def fetch_cloud_concepts() -> dict:
    """The upstream's concept vocabulary.

    Upstream answers ``{count, concepts, sources}``; this app's concept
    reader also carries *our own* count of the places it holds, which is
    not upstream's to know. So the vocabulary comes from upstream and the
    local count stays local.
    """
    client = _client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.geo_concepts)
    finally:
        client.close()
    return payload or {}


def concepts_to_read(payload: dict) -> list[dict]:
    """The upstream's vocabulary, in this app's reader shape.

    ``places`` is the upstream's own count: in cloud mode the app draws the
    upstream's places, so the upstream's count is the number it can draw.
    """
    out = []
    for concept in (payload or {}).get("concepts") or []:
        count = int(concept.get("places") or 0)
        out.append({
            "kind": concept.get("kind"),
            "name": concept.get("name"),
            "name_cn": concept.get("name_cn"),
            "description": concept.get("description"),
            "description_cn": concept.get("description_cn"),
            "rank": int(concept.get("rank") or 0),
            "places": count,
            "upstream_places": count,
        })
    return out


def csv_list(value: str | None) -> list[str]:
    """The comma-separated filter values, as a list."""
    return _csv(value)


__all__ = [
    "fetch_cloud_places", "fetch_cloud_place", "fetch_cloud_boundary",
    "fetch_cloud_at", "fetch_cloud_concepts",
    "place_to_detail", "at_places_to_read", "concepts_to_read",
    "csv_list", "CloudPlaces", "PAGE_SIZE", "MAX_ROWS", "DETAIL_FIELDS",
]
