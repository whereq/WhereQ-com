"""CLI: crawl whereq.cloud fuel stations (+ prices) into the places table.

Examples:
    python -m app.crawler.cli.fuel                                   # every configured target
    python -m app.crawler.cli.fuel --target "CA:Ontario"              # one state
    python -m app.crawler.cli.fuel --target "CA" --target "US"        # two countries
    python -m app.crawler.cli.fuel --target "bbox:-79.7,43.4,-79.3,43.9"   # a map viewport
    python -m app.crawler.cli.fuel --prices                           # aggregated price series
    python -m app.crawler.cli.fuel --allow-demo                      # public preview rows (testing)

Live/full data is metered — set WHEREQ_CLOUD_API_KEY (a whereq.cloud wq_live_…
key). Without it the API returns a 100-row demo preview, which is skipped
unless --allow-demo is given. The key stays on the server: it is read from the
environment and never reaches the browser.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.crawler.upstream.fuel_prices import crawl_price_series
from app.crawler.upstream.fuel_stations import (
    configured_targets,
    has_api_key,
    parse_target,
    crawl_target,
)


from app.core.logging_setup import configure_logging

async def _run(targets, allow_demo: bool, max_stations: int | None, prices: bool) -> None:
    async with AsyncSessionLocal() as db:
        if prices:
            results = await crawl_price_series(db)
            total = sum(results.values())
            print(f"Crawled {total} fuel price series (api_key={'yes' if has_api_key() else 'no'}):")
            for key, n in results.items():
                print(f"  {key:<20} {n}")
            return

        total = 0
        print(f"Crawling fuel stations (api_key={'yes' if has_api_key() else 'no'}):")
        for target in targets:
            count = await crawl_target(db, target, allow_demo=allow_demo,
                                      max_stations=max_stations)
            total += count
            print(f"  {target.label:<30} {count}")
        print(f"Crawled {total} fuel stations")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl whereq.cloud fuel stations into places")
    parser.add_argument("--target", action="append", default=[],
                        help="Coverage target: 'CC', 'CC:State', 'CC:State:Municipality' "
                             "or 'bbox:minLon,minLat,maxLon,maxLat' (repeatable). "
                             "Default: the configured FUEL_CRAWL_TARGETS.")
    parser.add_argument("--prices", action="store_true",
                        help="crawl the aggregated price series instead of stations")
    parser.add_argument("--allow-demo", action="store_true",
                        help="crawl the public demo preview even without an API key")
    parser.add_argument("--max-stations", type=int, default=None,
                        help="cap the stations written per target")
    args = parser.parse_args()

    targets = []
    for spec in args.target:
        target = parse_target(spec)
        if target is None:
            parser.error(f"unusable --target {spec!r}")
        targets.append(target)
    if not targets:
        targets = configured_targets()
    if not targets:
        parser.error("no coverage targets configured (set FUEL_CRAWL_TARGETS)")

    configure_logging()
    asyncio.run(_run(targets, args.allow_demo, args.max_stations, args.prices))


if __name__ == "__main__":
    main()
