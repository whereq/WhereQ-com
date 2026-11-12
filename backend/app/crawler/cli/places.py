"""CLI: crawl OpenStreetMap POIs into the places table.

Examples:
    python -m app.crawler.cli.places                         # full default GTA bbox, all categories
    python -m app.crawler.cli.places --only food,coffee      # just those categories
    python -m app.crawler.cli.places --bbox -79.6,43.58,-79.1,43.86   # custom area (minLng,minLat,maxLng,maxLat)
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.crawler.upstream.osm_places import DEFAULT_BBOX, OSM_CATEGORIES, crawl_places


from app.core.logging_setup import configure_logging

async def _run(bbox, only) -> None:
    async with AsyncSessionLocal() as db:
        results = await crawl_places(db, bbox, only=only)
    total = sum(results.values())
    print(f"Crawled {total} POIs:")
    for key, n in results.items():
        print(f"  {key:<10} {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl OSM POIs into places")
    parser.add_argument("--bbox", help="minLng,minLat,maxLng,maxLat (default: GTA)")
    parser.add_argument("--only", help="CSV of category keys: "
                                       + ",".join(c.key for c in OSM_CATEGORIES))
    args = parser.parse_args()

    bbox = DEFAULT_BBOX
    if args.bbox:
        parts = tuple(float(x) for x in args.bbox.split(","))
        if len(parts) != 4:
            parser.error("--bbox must be minLng,minLat,maxLng,maxLat")
        bbox = parts  # type: ignore[assignment]
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None

    configure_logging()
    asyncio.run(_run(bbox, only))


if __name__ == "__main__":
    main()
