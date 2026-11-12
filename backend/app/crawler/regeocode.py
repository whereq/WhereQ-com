"""CLI: place the content that the crawler could not place.

The location extractor only ever sees a row when it is first crawled, so a row
crawled before the extractor understood it stays unplaced for ever — it keeps
its city as metadata and never gets a pin.  This walks those rows again with
the current extractor, the current geocoder and the current cross-city guard,
and writes a position only where the text names a real place.

It is idempotent: re-running it re-evaluates the same rows and writes the
same outcome.  ``--dry-run`` reports what would happen and writes nothing.

Examples:
    python -m app.crawler.regeocode --dry-run          # report only
    python -m app.crawler.regeocode --limit 200        # place at most 200 rows
    python -m app.crawler.regeocode --include-expired  # also revisit expired rows
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.logging_setup import configure_logging
# The guard constants and the placement decision live with the crawler
# pipeline so the backfill and a fresh crawl always agree on what counts as
# a valid position.
from app.crawler.pipeline import (
    _guard_for,
    _location_plans,
    _resolve_position,
)
from app.models.local_content import LocalContent
from app.services.classify import classify
from app.services.geo_gazetteer import city_center, detect_city
from app.services.geocoding import geocode
from app.services.location_extract import is_self_locating

logger = logging.getLogger("regeocode")

# Rows are written in batches so a long run commits its progress.
_BATCH = 25

# The curated list is mostly Ontario, but a place in another province needs
# its own province in the query — "Montreal, ON" is a contradiction, and for a
# city whose name is also an Ontario place the province is what disambiguates.
_PROVINCE_BY_CITY: dict[str, str] = {
    "Montreal": "QC",
}


def _province_for(city: str) -> str:
    """The province to query a curated place in."""
    return _PROVINCE_BY_CITY.get(city, "ON")


def _point(lng: float, lat: float):
    return func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)


@dataclass
class Placed:
    """The outcome for one row."""
    query: str
    lat: float
    lng: float
    status: str
    source: str | None
    city: str | None


async def _process(db, row: LocalContent, *, dry_run: bool, max_plans: int) -> Placed | None:
    """Try to place one row. Returns the placement, or None."""
    # The city the story is about: title first, then the dateline at the top
    # of the wire story.  The full description is not used here — it is full
    # of places merely mentioned.
    detected = detect_city(row.title, row.summary or row.description)
    city = detected or row.city
    cls = classify(row.title, row.summary or row.description or "")

    plans = _location_plans(
        row.title, row.summary, row.description,
        city=city, province=row.province, country=row.country or "Canada",
    )[:max_plans]
    for plan in plans:
        # With no city detected the story's location is unknown, so only
        # evidence that stands on its own may place it.
        if not detected and not is_self_locating(plan):
            continue
        center, guard_km = _guard_for(
            plan, detected=detected, story_city=city)
        geo = await geocode(
            db, plan.query,
            region=(row.country or "CA").lower(),
            country=row.country or "CA",
        )
        lat, lng, status, source, confidence = _resolve_position(
            geo, center, guard_km, plan.confidence, cls.confidence)
        if lat is None:
            continue

        if not dry_run:
            row.latitude = lat
            row.longitude = lng
            row.geom = _point(lng, lat)
            row.geocode_status = status
            row.geocode_source = source
            row.confidence_score = confidence
        return Placed(plan.query, lat, lng, status, source, city)
    return None


async def _check_places() -> None:
    """Geocode every curated place name and report the ones that do not
    resolve inside the municipality the list claims.

    The curated list is hand-written, so it needs checking against the real
    geocoder: a name that resolves to the wrong city (or nowhere) would put a
    pin in the wrong place.
    """
    from app.services.gta_places import PLACES
    from app.services.geo_gazetteer import haversine_km

    bad: list[tuple[str, str, str]] = []
    async with AsyncSessionLocal() as db:
        for name, city in sorted(PLACES.items()):
            query = f"{name}, {city}, {_province_for(city)}, Canada"
            geo = await geocode(db, query, region="ca", country="CA")
            if geo is None:
                bad.append((name, city, "unresolved"))
                continue
            center = city_center(city)
            if not center:
                bad.append((name, city, "unknown municipality"))
                continue
            km = haversine_km(center, (geo.lat, geo.lng))
            if km > 25:
                bad.append((name, city, f"{km:.0f} km away "
                                        f"({geo.lat:.4f},{geo.lng:.4f})"))
    print(f"Checked {len(PLACES)} curated places, {len(bad)} questionable:")
    for name, city, why in bad:
        print(f"  {name!r} ({city}): {why}")


async def _run(limit: int | None, dry_run: bool, include_expired: bool,
               max_plans: int, recheck: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        if recheck:
            # Rows that already have a position, re-judged with the current
            # rules.  A row the extractor can no longer place loses its
            # pin rather than keeping a stale one.
            stmt = select(LocalContent).where(LocalContent.latitude.isnot(None))
            if not include_expired:
                stmt = stmt.where(LocalContent.status == "active")
        else:
            stmt = select(LocalContent).where(LocalContent.latitude.is_(None))
            if not include_expired:
                stmt = stmt.where(LocalContent.status == "active")
        stmt = stmt.order_by(LocalContent.id)
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        print(f"Candidates: {len(rows)} {'placed' if recheck else 'unplaced'} rows"
              f"{' (dry run)' if dry_run else ''}")

        placed = 0
        kinds = Counter()
        by_city = Counter()
        unplaced_now = 0
        shown = 0
        for i, row in enumerate(rows, 1):
            hit = await _process(db, row, dry_run=dry_run, max_plans=max_plans)
            if hit:
                placed += 1
                kinds[hit.status] += 1
                by_city[hit.city] += 1
                if shown < 400:
                    shown += 1
                    print(f"  [{row.id}] {row.title[:66]!r}\n"
                          f"        -> {hit.query}\n"
                          f"           {hit.lat:.4f},{hit.lng:.4f} "
                          f"({hit.source}, city={hit.city})")
            elif recheck:
                # The rules can no longer place it: the pin it carries was
                # placed by an older extractor and is no longer defensible.
                unplaced_now += 1
                if shown < 400:
                    shown += 1
                    print(f"  [{row.id}] {row.title[:66]!r}\n"
                          f"        -> no longer placeable "
                          f"(was {row.latitude:.4f},{row.longitude:.4f})")
                if not dry_run:
                    row.latitude = None
                    row.longitude = None
                    row.geom = None
                    row.geocode_status = "none"
                    row.geocode_source = None
            if not dry_run and i % _BATCH == 0:
                await db.commit()
        if not dry_run:
            await db.commit()

    print(f"\nPlaced {placed}/{len(rows)}")
    for status, n in kinds.items():
        print(f"  {status}: {n}")
    print("  by story city:", dict(by_city.most_common()))
    if recheck:
        print(f"  no longer placeable: {unplaced_now}")
    if dry_run:
        print("(dry run — nothing was written)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-extract locations for unplaced content and place it")
    parser.add_argument("--limit", type=int, help="stop after N rows")
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument("--include-expired", action="store_true",
                        help="also revisit expired rows")
    parser.add_argument("--max-plans", type=int, default=3,
                        help="location candidates to try per row (default 3)")
    parser.add_argument("--recheck", action="store_true",
                        help="re-judge rows that already have a position; a row "
                             "the current rules cannot place loses its pin")
    parser.add_argument("--check-places", action="store_true",
                        help="verify the curated place list against the geocoder "
                             "and exit")
    args = parser.parse_args()

    configure_logging()
    if args.check_places:
        asyncio.run(_check_places())
        return
    asyncio.run(_run(args.limit, args.dry_run, args.include_expired,
                     args.max_plans, args.recheck))


if __name__ == "__main__":
    main()
