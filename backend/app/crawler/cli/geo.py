"""CLI: crawl the whereq.cloud geography feed (administrative places).

Examples:
    python -m app.crawler.cli.geo                                   # every configured target
    python -m app.crawler.cli.geo --target "bbox:-80.3,43.6,-79.2,44.2"   # one viewport
    python -m app.crawler.cli.geo --target "kind:ward" --target "kind:neighbourhood"
    python -m app.crawler.cli.geo --boundaries                      # also fetch the outlines
    python -m app.crawler.cli.geo --concepts-only                   # just refresh the vocabulary

The geography endpoints work on the public tier, so no API key is required —
but ``WHEREQ_CLOUD_API_KEY`` is used when present, because the key is what
makes the feed complete and current. The key stays on the server: it is read
from the environment and never reaches the browser.

The feed is open data (OpenStreetMap under ODbL 1.0, geoBoundaries under
CC-BY 4.0), so unlike the fuel prices it may be served publicly — with the
attribution, which travels on every row.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.core.logging_setup import configure_logging
from app.crawler.upstream.geo_places import (
    configured_targets,
    parse_target,
    run_crawl,
)

logger = logging.getLogger(__name__)


async def _run(targets, with_boundaries: bool, concepts_only: bool) -> None:
    async with AsyncSessionLocal() as db:
        if concepts_only:
            report = await run_crawl(db, [], with_boundaries=False)
            print(f"Refreshed {report['concepts']} concept(s).")
            return

        report = await run_crawl(db, targets, with_boundaries=with_boundaries)
        print("Crawling administrative geography:")
        for row in report["targets"]:
            print(f"  {row['target']:<40} {row['places']:>6} place(s)  "
                  f"{row['boundaries']:>5} boundary(ies)")
        print(f"  {'concepts':<40} {report['concepts']:>6}")
        print(f"Crawled {report['places']} place(s), {report['boundaries']} boundary(ies)")
        if report["errors"]:
            print(f"{len(report['errors'])} target(s) failed:")
            for err in report["errors"]:
                print(f"  {err['target']}: {err['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl the whereq.cloud geography feed (administrative places)")
    parser.add_argument("--target", action="append", default=[],
                        help="Coverage target: 'kind:<concept>', 'kind:<concept>:<country>', "
                             "'country:<CC>', 'source:<name>' or "
                             "'bbox:minLon,minLat,maxLon,maxLat' (repeatable). "
                             "Default: the configured GEO_CRAWL_TARGETS.")
    parser.add_argument("--boundaries", action="store_true",
                        help="also fetch each place's outline (slow: one request per place)")
    parser.add_argument("--concepts-only", action="store_true",
                        help="refresh the vocabulary only")
    parser.add_argument("--max-places", type=int, default=None,
                        help="cap the places written per target")
    args = parser.parse_args()

    if args.max_places is not None and args.max_places < 1:
        parser.error("--max-places must be at least 1")

    targets = []
    for spec in args.target:
        target = parse_target(spec)
        if target is None:
            parser.error(f"unusable --target {spec!r}")
        targets.append(target)
    if not targets and not args.concepts_only:
        targets = configured_targets()
        if not targets:
            parser.error("no coverage targets configured (set GEO_CRAWL_TARGETS)")

    configure_logging()
    if args.max_places:
        from app.core.config import settings

        settings.GEO_CRAWL_MAX_PLACES = args.max_places

    asyncio.run(_run(targets, args.boundaries, args.concepts_only))


if __name__ == "__main__":
    main()
