"""Long-running scheduler — the entry point for the whereq-com-consumer
container.

A self-contained asyncio loop (no host cron, no extra scheduler dependency):
  • every CRAWLER_RETENTION_SECONDS, expire stale rows;
  • every LOCAL_CONTENT_SYNC_CHECK_SECONDS, read the newest upstream content
    rows from whereq.cloud into the local mirror;
  • every LOCAL_PLACES_SYNC_CHECK_SECONDS, read the upstream's POI catalogue
    into the local mirror, when it is due;
  • optionally seed default sources on startup.

**The collection is whereq.cloud's.** The RSS crawl and the Overpass POI
ingest are still here, but they are **off** by default — the two ticks that
read whereq.cloud do their work instead. ``LEGACY_COLLECTORS_ENABLED=true``
puts the old collectors back, and that is the rollback.

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
from app.services.cloud_local import sync_local_content, sync_local_places
from app.services.whereq_cloud_client import has_api_key
from app.services.osm_places import DEFAULT_BBOX, ingest_places
from app.services.fuel_prices import price_series_due, sync_price_series
from app.services.fuel_stations import (
    due_targets,
    has_api_key,
    record_sync,
    sync_target,
)
from app.services.geo_places import (
    configured_targets as geo_configured_targets,
    run_sync as geo_run_sync,
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
    """The legacy RSS crawl. **Off by default** — whereq.cloud collects now.

    Kept for the rollback: ``LEGACY_COLLECTORS_ENABLED=true`` brings it back,
    and it writes to the same rows the upstream sync writes, so the two are
    interchangeable.
    """
    if not settings.LEGACY_COLLECTORS_ENABLED:
        return
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


async def _local_content_sync_tick() -> None:
    """Read the newest upstream content rows into the local mirror.

    whereq.cloud collects the feeds; this reads them. Only the head of the
    feed is read — the rows behind it are already in the mirror — and every
    pass re-reads the same head, so a pass that failed costs nothing.
    """
    if not settings.LOCAL_CONTENT_SYNC_ENABLED or not has_api_key():
        return
    async with AsyncSessionLocal() as db:
        report = await sync_local_content(db)
        logger.info("Local content sync: %d written, %d skipped, %d page(s)",
                    report["written"], report["skipped"], report["pages"])


async def _local_places_sync_tick() -> None:
    """Read the upstream's POI catalogue into the local mirror.

    Due-ness uses the same rule the Overpass ingest used: the newest
    ``source='osm'`` row is the watermark, because a sync restamps the rows
    it refreshes. So the catalogue is re-read weekly — the upstream's own
    sweep runs weekly, and there is no "changed since" marker to ask for.
    """
    if not settings.LOCAL_PLACES_SYNC_ENABLED or not has_api_key():
        return
    async with AsyncSessionLocal() as db:
        newest = (await db.execute(
            select(func.max(Place.updated_at)).where(Place.source == "osm")
        )).scalar_one_or_none()
        if newest is not None:
            age = datetime.now(timezone.utc) - newest
            if age < timedelta(hours=settings.LOCAL_PLACES_SYNC_INTERVAL_HOURS):
                logger.debug("local places sync: not due yet")
                return
        report = await sync_local_places(db)
        logger.info("Local places sync: %d written, %d skipped, %d page(s)",
                    report["written"], report["skipped"], report["pages"])


async def _retention_tick() -> None:
    async with AsyncSessionLocal() as db:
        n = await retention_expiry(db)
        if n:
            logger.info("retention: %d row(s) expired", n)


async def _poi_tick() -> None:
    """The legacy Overpass POI ingest. **Off by default** — whereq.cloud
    collects the POIs now, and ``_local_places_sync_tick`` reads them.

    Kept for the rollback: ``LEGACY_COLLECTORS_ENABLED=true`` brings it back.
    """
    if not settings.LEGACY_COLLECTORS_ENABLED:
        return
    if not settings.POI_INGEST_ENABLED:
        return
    async with AsyncSessionLocal() as db:
        newest = (await db.execute(
            select(func.max(Place.updated_at)).where(Place.source == "osm"))).scalar_one_or_none()
        if newest is not None:
            age = datetime.now(timezone.utc) - newest
            if age < timedelta(days=settings.POI_INGEST_INTERVAL_DAYS):
                return  # not due yet
        logger.info("POI ingest: refreshing OSM places (bbox=%s)", DEFAULT_BBOX)
        results = await ingest_places(db, DEFAULT_BBOX)
        logger.info("POI ingest: %s", results)


async def _fuel_tick() -> None:
    """Refresh whereq.cloud fuel stations for the targets that are due.

    **Off by default** — the fuel stations are read from whereq.cloud live
    (``FUEL_READ_MODE=cloud``), so mirroring them into ``places`` is a second
    copy of data the platform already owns. ``FUEL_MIRROR_ENABLED=true`` brings
    the mirror back; it is the rollback.

    Coverage is split into targets (a country, a state, a city or a map bbox)
    that are rotated round-robin, so a single tick never pulls the whole
    continent at once.
    """
    if not settings.FUEL_MIRROR_ENABLED:
        return
    if not settings.FUEL_INGEST_ENABLED or not has_api_key():
        return
    async with AsyncSessionLocal() as db:
        due = await due_targets(db)
        if not due:
            logger.debug("fuel ingest: no target due")
            return
        batch = due[:max(1, settings.FUEL_INGEST_TARGETS_PER_TICK)]
        for target in batch:
            logger.info("Fuel ingest: syncing %s", target.label)
            try:
                count = await sync_target(db, target)
            except Exception as exc:  # noqa: BLE001 — one bad target must not
                # stop the others (or the scheduler).
                logger.warning("Fuel ingest: %s failed: %s", target.label, exc)
                await record_sync(db, target, station_count=0, error=str(exc))
                continue
            await record_sync(db, target, station_count=count)


async def _fuel_prices_tick() -> None:
    """Refresh the aggregated fuel price series (EIA/StatCan/CRE averages).

    **Off by default** — the series are read from whereq.cloud live, for the
    same reason the stations are. ``FUEL_MIRROR_ENABLED=true` is the rollback.
    """
    if not settings.FUEL_MIRROR_ENABLED:
        return
    if not settings.FUEL_PRICES_ENABLED or not has_api_key():
        return
    async with AsyncSessionLocal() as db:
        # The tick runs hourly; the sync only happens when the stored series
        # are stale, so a failed run is retried within the hour.
        if not await price_series_due(db):
            return
        results = await sync_price_series(db)
        logger.info("Fuel price series: %s", results)


async def _geo_tick() -> None:
    """Refresh the administrative geography for the targets that are due.

    Same round-robin shape as the fuel ingest: one tick syncs at most
    GEO_INGEST_TARGETS_PER_TICK coverage targets, so no single tick pulls a
    whole continent's worth of outlines. Due-ness is tracked per target in
    `geo_sync_state`.

    Unlike the fuel feed this needs no API key — the geography endpoints are
    on the public tier — so the tick runs whenever the feature is enabled.
    """
    if not settings.GEO_INGEST_ENABLED:
        return
    if not geo_configured_targets():
        logger.debug("geo ingest: no coverage targets configured")
        return
    async with AsyncSessionLocal() as db:
        due = await geo_targets_due(db)
        if not due:
            logger.debug("geo ingest: no target due")
            return
        batch = due[:max(1, settings.GEO_INGEST_TARGETS_PER_TICK)]
        report = await geo_run_sync(db, batch,
                                    with_boundaries=settings.GEO_INGEST_FETCH_BOUNDARIES)
        logger.info("Geo ingest: %s place(s) over %d target(s), %d error(s)",
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

    logger.info(
        "consumer scheduler started (local content every %ds, retention every %ds, "
        "local places every %ds, fuel every %ds, fuel prices every %ds, geo every %ds)",
        settings.LOCAL_CONTENT_SYNC_CHECK_SECONDS, settings.CRAWLER_RETENTION_SECONDS,
        settings.LOCAL_PLACES_SYNC_CHECK_SECONDS, settings.FUEL_INGEST_CHECK_SECONDS,
        settings.FUEL_PRICES_CHECK_SECONDS, settings.GEO_INGEST_CHECK_SECONDS)
    if not settings.FUEL_MIRROR_ENABLED:
        # The banner above names the schedule, not what is switched on — so
        # say which of it is not running.
        logger.info("the fuel mirror is off (FUEL_MIRROR_ENABLED=false) — the stations "
                    "and the price series are read live from whereq.cloud, so the two "
                    "fuel ticks do nothing")
    if not settings.GEO_INGEST_ENABLED:
        # Same for the geography: every geography surface reads whereq.cloud,
        # so the mirror would be a second copy of data the platform owns — and
        # the second copy is the one that goes stale.
        logger.info("the geography mirror is off (GEO_INGEST_ENABLED=false) — all six "
                    "geography surfaces read whereq.cloud live, so the geo tick does "
                    "nothing")
    if settings.LEGACY_COLLECTORS_ENABLED:
        logger.warning("LEGACY_COLLECTORS_ENABLED is true — the RSS crawl and the "
                       "Overpass POI ingest are running alongside the upstream sync.")
    await asyncio.gather(
        _periodic(_local_content_sync_tick,
                  settings.LOCAL_CONTENT_SYNC_CHECK_SECONDS, "local-content-sync"),
        _periodic(_retention_tick, settings.CRAWLER_RETENTION_SECONDS, "retention"),
        _periodic(_local_places_sync_tick,
                  settings.LOCAL_PLACES_SYNC_CHECK_SECONDS, "local-places-sync"),
        _periodic(_fuel_tick, settings.FUEL_INGEST_CHECK_SECONDS, "fuel"),
        _periodic(_fuel_prices_tick, settings.FUEL_PRICES_CHECK_SECONDS, "fuel-prices"),
        _periodic(_geo_tick, settings.GEO_INGEST_CHECK_SECONDS, "geo"),
        # The legacy collectors. Off unless the rollback is asked for.
        _periodic(_crawl_tick, settings.CRAWLER_TICK_SECONDS, "crawl"),
        _periodic(_poi_tick, settings.POI_INGEST_CHECK_SECONDS, "poi"),
    )
    logger.info("consumer scheduler stopped")


def main() -> None:
    configure_logging()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
