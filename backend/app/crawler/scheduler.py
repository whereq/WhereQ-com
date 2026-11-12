"""Long-running crawler scheduler — the entry point for the whereq-crawler
container.

A self-contained asyncio loop (no host cron, no extra scheduler dependency):
  • every CRAWLER_TICK_SECONDS, crawl every enabled source that is *due*
    (per-source ``crawl_interval_minutes``);
  • every CRAWLER_RETENTION_SECONDS, expire stale rows;
  • optionally seed default sources on startup.

Run:  python -m app.crawler.scheduler
Shuts down cleanly on SIGTERM/SIGINT (so `docker stop` is graceful).
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging_setup import configure_logging
from app.crawler.pipeline import retention_expiry
from app.crawler.run import _crawl_source, _is_due
from app.crawler.seed_sources import seed_default_sources
from app.models.local_content import NewsSource
from app.models.place import Place
from app.crawler.upstream.osm_places import DEFAULT_BBOX, crawl_places
from app.crawler.upstream.fuel_prices import price_series_due, crawl_price_series
from app.crawler.upstream.fuel_stations import (
    due_targets,
    has_api_key,
    record_crawl,
    crawl_target,
)
from app.crawler.upstream.geo_places import (
    configured_targets as geo_configured_targets,
    run_crawl as geo_run_crawl,
    targets_due as geo_targets_due,
)

logger = logging.getLogger("crawler.scheduler")

_stop = asyncio.Event()


async def _ensure_seeded(db) -> None:
    """Seed default sources when the table is empty.

    Idempotent + self-healing: if the crawler started before the DB was
    migrated (so startup seeding failed), the first tick after migration finds
    an empty table and seeds it — no manual restart needed. An operator who has
    intentionally emptied/curated sources is respected (only seeds when empty).
    """
    if not settings.CRAWLER_SEED_ON_START:
        return
    count = (await db.execute(select(func.count()).select_from(NewsSource))).scalar_one()
    if count == 0:
        created, updated = await seed_default_sources(db)
        logger.info("seeded sources (table was empty): %d created", created)


async def _crawl_tick() -> None:
    async with AsyncSessionLocal() as db:
        await _ensure_seeded(db)
        sources = (await db.execute(
            select(NewsSource).where(NewsSource.enabled.is_(True)).order_by(NewsSource.slug)
        )).scalars().all()
        due = [s for s in sources if _is_due(s)]
        if not due:
            logger.debug("crawl tick: no sources due")
            return
        totals: dict[str, int] = {}
        for s in due:
            counts = await _crawl_source(db, s, limit=None, dry_run=False)
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
        logger.info("crawl tick: %d source(s) %s", len(due), totals)


async def _retention_tick() -> None:
    async with AsyncSessionLocal() as db:
        n = await retention_expiry(db)
        if n:
            logger.info("retention: %d row(s) expired", n)


async def _poi_tick() -> None:
    """Refresh OSM POIs when due. Due = no OSM rows yet, or the newest OSM row is
    older than POI_CRAWL_INTERVAL_DAYS. Runs on the first tick of a fresh DB
    (auto-populate) but skips on restarts within the interval."""
    if not settings.POI_CRAWL_ENABLED:
        return
    async with AsyncSessionLocal() as db:
        newest = (await db.execute(
            select(func.max(Place.updated_at)).where(Place.source == "osm"))).scalar_one_or_none()
        if newest is not None:
            age = datetime.now(timezone.utc) - newest
            if age < timedelta(days=settings.POI_CRAWL_INTERVAL_DAYS):
                return  # not due yet
        logger.info("POI crawl: refreshing OSM places (bbox=%s)", DEFAULT_BBOX)
        results = await crawl_places(db, DEFAULT_BBOX)
        logger.info("POI crawl: %s", results)


async def _fuel_tick() -> None:
    """Refresh whereq.cloud fuel stations for the targets that are due.

    Coverage is split into targets (a country, a state, a city or a map bbox)
    that are rotated round-robin: one tick crawls at most
    FUEL_CRAWL_TARGETS_PER_TICK of them, so the metered API is never asked
    for the whole continent at once and a full cycle still completes within
    the refresh interval. Due-ness is tracked per target in `fuel_sync_state`.
    """
    if not settings.FUEL_CRAWL_ENABLED or not has_api_key():
        return
    async with AsyncSessionLocal() as db:
        due = await due_targets(db)
        if not due:
            logger.debug("fuel crawl: no target due")
            return
        batch = due[:max(1, settings.FUEL_CRAWL_TARGETS_PER_TICK)]
        for target in batch:
            logger.info("Fuel crawl: %s", target.label)
            try:
                count = await crawl_target(db, target)
            except Exception as exc:  # noqa: BLE001 — one bad target must not
                # stop the others (or the scheduler).
                logger.warning("Fuel crawl: %s failed: %s", target.label, exc)
                await record_crawl(db, target, station_count=0, error=str(exc))
                continue
            await record_crawl(db, target, station_count=count)


async def _fuel_prices_tick() -> None:
    """Refresh the aggregated fuel price series (EIA/StatCan/CRE averages).

    The underlying series are weekly (US) or monthly (Canada/Mexico), so this
    runs on a slow cadence. Skipped without an API key.
    """
    if not settings.FUEL_PRICES_ENABLED or not has_api_key():
        return
    async with AsyncSessionLocal() as db:
        # The tick runs hourly; the crawl only happens when the stored series
        # are stale, so a failed run is retried within the hour.
        if not await price_series_due(db):
            return
        results = await crawl_price_series(db)
        logger.info("Fuel price series: %s", results)


async def _geo_tick() -> None:
    """Refresh the administrative geography for the targets that are due.

    Same round-robin shape as the fuel crawl: one tick crawls at most
    GEO_CRAWL_TARGETS_PER_TICK coverage targets, so no single tick pulls a
    whole continent's worth of outlines. Due-ness is tracked per target in
    `geo_sync_state`.

    Unlike the fuel feed this needs no API key — the geography endpoints are
    on the public tier — so the tick runs whenever the feature is enabled.
    """
    if not settings.GEO_CRAWL_ENABLED:
        return
    if not geo_configured_targets():
        logger.debug("geo crawl: no coverage targets configured")
        return
    async with AsyncSessionLocal() as db:
        due = await geo_targets_due(db)
        if not due:
            logger.debug("geo crawl: no target due")
            return
        batch = due[:max(1, settings.GEO_CRAWL_TARGETS_PER_TICK)]
        report = await geo_run_crawl(db, batch,
                                    with_boundaries=settings.GEO_CRAWL_FETCH_BOUNDARIES)
        logger.info("Geo crawl: %s place(s) over %d target(s), %d error(s)",
                    report["places"], len(report["targets"]), len(report["errors"]))


async def _periodic(make_coro, interval: int, name: str) -> None:
    """Run an async task immediately, then every ``interval`` seconds until stop."""
    while not _stop.is_set():
        try:
            await make_coro()
        except Exception:
            logger.exception("%s tick failed", name)
        try:
            await asyncio.wait_for(_stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def _main() -> None:
    if not settings.CRAWLER_ENABLED:
        logger.warning("CRAWLER_ENABLED is false — scheduler idling.")
        await _stop.wait()
        return

    if settings.CRAWLER_SEED_ON_START:
        # Best-effort at startup; if the DB isn't migrated yet this is retried
        # by _ensure_seeded() on the first successful crawl tick.
        try:
            async with AsyncSessionLocal() as db:
                created, updated = await seed_default_sources(db)
                logger.info("seeded sources: %d created, %d updated", created, updated)
        except Exception:
            logger.warning("startup seeding deferred (DB not ready?) — will retry on first tick")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop.set)
        except NotImplementedError:  # e.g. non-Unix
            pass

    logger.info("crawler scheduler started (crawl every %ds, retention every %ds, POI check every %ds)",
                settings.CRAWLER_TICK_SECONDS, settings.CRAWLER_RETENTION_SECONDS,
                settings.POI_CRAWL_CHECK_SECONDS)
    await asyncio.gather(
        _periodic(_crawl_tick, settings.CRAWLER_TICK_SECONDS, "crawl"),
        _periodic(_retention_tick, settings.CRAWLER_RETENTION_SECONDS, "retention"),
        _periodic(_poi_tick, settings.POI_CRAWL_CHECK_SECONDS, "poi"),
        _periodic(_fuel_tick, settings.FUEL_CRAWL_CHECK_SECONDS, "fuel"),
        _periodic(_fuel_prices_tick, settings.FUEL_PRICES_CHECK_SECONDS, "fuel-prices"),
        _periodic(_geo_tick, settings.GEO_CRAWL_CHECK_SECONDS, "geo"),
    )
    logger.info("crawler scheduler stopped")


def main() -> None:
    configure_logging()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
