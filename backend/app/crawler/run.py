"""The content crawler — one crawl, by hand.

Discovers local news / events / stories / topics from the registered
``news_source`` definitions, normalizes them, places them on the map,
classifies them and upserts ``local_content`` rows.

The long-running loop that does this on a timer is
``python -m app.crawler.scheduler`` (the ``crawler`` container). This module
is the same crawl, started by hand — useful for a first run, a one-off
source, or a cron of your own.

Examples:
    python -m app.crawler.run --seed                # bootstrap default sources
    python -m app.crawler.run --list                # list configured sources
    python -m app.crawler.run                        # crawl all sources that are due
    python -m app.crawler.run --source citynews-toronto --limit 20
    python -m app.crawler.run --all                  # crawl every enabled source now
    python -m app.crawler.run --retention            # expire stale rows
    python -m app.crawler.run --source blogto --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.logging_setup import configure_logging
from app.crawler.pipeline import process_item, retention_expiry
from app.crawler.seed_sources import seed_default_sources
from app.crawler.sources import get_source
from app.models.local_content import NewsSource

logger = logging.getLogger("crawler")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_due(source: NewsSource) -> bool:
    if source.last_crawled_at is None:
        return True
    due_at = source.last_crawled_at + timedelta(minutes=source.crawl_interval_minutes or 60)
    return _now() >= due_at


async def _crawl_source(db, source: NewsSource, *, limit: int | None, dry_run: bool) -> dict:
    counts = {"created": 0, "updated": 0, "duplicate": 0, "skipped": 0, "error": 0}
    try:
        plugin = get_source(source)
        items = await plugin.fetch()
    except Exception as exc:
        logger.error("Fetch failed for %s: %s", source.slug, exc)
        source.last_status, source.last_error, source.last_crawled_at = "error", str(exc)[:500], _now()
        if not dry_run:
            await db.commit()
        counts["error"] += 1
        return counts

    if limit:
        items = items[:limit]

    for raw in items:
        try:
            result = await process_item(db, source, raw, dry_run=dry_run)
            counts[result] = counts.get(result, 0) + 1
        except Exception as exc:
            logger.exception("Item failed (%s): %s", raw.url, exc)
            await db.rollback()
            counts["error"] += 1

    source.last_status, source.last_error, source.last_crawled_at = "ok", None, _now()
    if not dry_run:
        await db.commit()
    logger.info("Source %s: %s", source.slug, counts)
    return counts


async def _run(args) -> None:
    async with AsyncSessionLocal() as db:
        if args.seed:
            created, updated = await seed_default_sources(db)
            logger.info("Seeded sources: %d created, %d updated", created, updated)
            return

        if args.retention:
            n = await retention_expiry(db)
            logger.info("Retention sweep: %d rows expired", n)
            return

        q = select(NewsSource).where(NewsSource.enabled.is_(True))
        if args.source:
            q = select(NewsSource).where(NewsSource.slug == args.source)
        sources = (await db.execute(q.order_by(NewsSource.slug))).scalars().all()

        if args.list:
            for s in sources:
                logger.info("%-20s %-5s enabled=%s interval=%dm last=%s url=%s",
                            s.slug, s.kind, s.enabled, s.crawl_interval_minutes,
                            s.last_crawled_at, s.url)
            return

        if not sources:
            logger.warning("No sources found (run --seed first?)")
            return

        totals = {"created": 0, "updated": 0, "duplicate": 0, "skipped": 0, "error": 0}
        for s in sources:
            if not (args.source or args.all or _is_due(s)):
                logger.info("Skipping %s (not due)", s.slug)
                continue
            counts = await _crawl_source(db, s, limit=args.limit, dry_run=args.dry_run)
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
        logger.info("TOTAL: %s%s", totals, " (dry-run)" if args.dry_run else "")


def main() -> None:
    configure_logging()
    p = argparse.ArgumentParser(description="WhereQ local-content crawler")
    p.add_argument("--source", help="crawl only this source slug (forces, ignores interval)")
    p.add_argument("--all", action="store_true", help="crawl every enabled source now (ignore interval)")
    p.add_argument("--limit", type=int, help="max items per source")
    p.add_argument("--seed", action="store_true", help="upsert default sources and exit")
    p.add_argument("--list", action="store_true", help="list configured sources and exit")
    p.add_argument("--retention", action="store_true", help="expire stale rows and exit")
    p.add_argument("--dry-run", action="store_true", help="process without writing to the DB")
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
