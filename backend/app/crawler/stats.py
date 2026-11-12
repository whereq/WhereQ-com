"""Crawler / local-content statistics report.

Run inside the crawler (or api) container so it reuses the app's DATABASE_URL:
    python -m app.crawler.stats

Prints: source health, collected-content counts (by status/type/category,
geocoded ratio, last 24h), today's geocoding-provider usage vs quota, and
geocode-cache stats. Read-only.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.local_content import (
    GeocodeCache, GeocodeProviderUsage, LocalContent, NewsSource,
)

# provider -> (quota, window) for the usage report
_PROVIDER_QUOTAS = {
    "geocode_maps_co": (lambda: settings.GEOCODE_MAPS_CO_DAILY_QUOTA, "day"),
    "locationiq": (lambda: settings.LOCATIONIQ_DAILY_QUOTA, "day"),
    "geocodio": (lambda: settings.GEOCODIO_DAILY_QUOTA, "day"),
    "nominatim": (lambda: settings.NOMINATIM_DAILY_QUOTA, "day"),
    "positionstack": (lambda: settings.POSITIONSTACK_MONTHLY_QUOTA, "month"),
    "google": (lambda: settings.GOOGLE_GEOCODE_DAILY_QUOTA, "day"),
}


def _h(title: str) -> None:
    print(f"\n\033[1;36m{title}\033[0m")
    print("─" * len(title))


async def _report() -> None:
    now = datetime.now(timezone.utc)
    day_key = now.strftime("%Y-%m-%d")
    month_key = now.strftime("%Y-%m")

    async with AsyncSessionLocal() as db:
        # ── Sources ──────────────────────────────────────────────────────
        _h("Sources")
        rows = (await db.execute(select(
            NewsSource.slug, NewsSource.enabled, NewsSource.kind,
            NewsSource.last_status, NewsSource.last_crawled_at,
            NewsSource.crawl_interval_minutes,
        ).order_by(NewsSource.slug))).all()
        if not rows:
            print("  (none — run `python -m app.crawler.run --seed`)")
        for slug, enabled, kind, status, last, interval in rows:
            last_s = last.strftime("%Y-%m-%d %H:%M") if last else "never"
            flag = "on " if enabled else "OFF"
            print(f"  {slug:<22} {flag} {kind:<5} {str(status or '-'):<6} "
                  f"every {interval}m   last: {last_s}")

        # ── Content totals ───────────────────────────────────────────────
        _h("Collected content")
        by_status = dict((await db.execute(
            select(LocalContent.status, func.count()).group_by(LocalContent.status))).all())
        total = sum(by_status.values())
        print(f"  total: {total}   " + "  ".join(f"{k}={v}" for k, v in sorted(by_status.items())))

        geo = (await db.execute(select(
            func.count().filter(LocalContent.geom.is_not(None)),
            func.count().filter(LocalContent.geom.is_(None)),
        ).where(LocalContent.status == "active"))).one()
        print(f"  active geocoded: {geo[0]}   not-geocoded: {geo[1]}")

        last24_n = (await db.execute(
            select(func.count()).select_from(LocalContent)
            .where(LocalContent.created_at >= now - _interval_24h()))).scalar_one()
        newest = (await db.execute(select(func.max(LocalContent.publish_time)))).scalar_one()
        print(f"  added (last 24h): {last24_n}   newest publish: "
              f"{newest.strftime('%Y-%m-%d %H:%M') if newest else '-'}")

        # ── By type / category ───────────────────────────────────────────
        _h("Active by type")
        for t, c in (await db.execute(
            select(LocalContent.type, func.count()).where(LocalContent.status == "active")
            .group_by(LocalContent.type).order_by(func.count().desc()))).all():
            print(f"  {t:<10} {c}")

        _h("Active by category")
        for cat, c in (await db.execute(
            select(LocalContent.category, func.count()).where(LocalContent.status == "active")
            .group_by(LocalContent.category).order_by(func.count().desc()))).all():
            print(f"  {cat:<16} {c}")

        # ── Per source ───────────────────────────────────────────────────
        _h("Active content by source")
        for slug, c in (await db.execute(
            select(NewsSource.slug, func.count(LocalContent.id))
            .join(LocalContent, (LocalContent.source_id == NewsSource.id)
                  & (LocalContent.status == "active"), isouter=True)
            .group_by(NewsSource.slug).order_by(func.count(LocalContent.id).desc()))).all():
            print(f"  {slug:<22} {c}")

        # ── Geocoding usage today vs quota ───────────────────────────────
        _h("Geocoding usage (current window) vs quota")
        usage = dict(((p, per), n) for p, per, n in (await db.execute(
            select(GeocodeProviderUsage.provider, GeocodeProviderUsage.period,
                   GeocodeProviderUsage.count)
            .where(GeocodeProviderUsage.period.in_([day_key, month_key])))).all())
        order = [p.strip() for p in settings.GEOCODE_PROVIDER_ORDER.split(",") if p.strip()]
        for p in order:
            quota_fn, window = _PROVIDER_QUOTAS.get(p, (lambda: 0, "day"))
            key = month_key if window == "month" else day_key
            used = usage.get((p, key), 0)
            quota = quota_fn()
            pct = f"{(100 * used / quota):.0f}%" if quota else "-"
            print(f"  {p:<18} {used:>7} / {quota:<7} ({pct}) [{window}]")

        # ── Geocode cache ────────────────────────────────────────────────
        _h("Geocode cache")
        cache = (await db.execute(select(
            func.count(), func.count().filter(GeocodeCache.latitude.is_not(None)),
            func.coalesce(func.sum(GeocodeCache.hit_count), 0),
        ))).one()
        print(f"  entries: {cache[0]}   resolved: {cache[1]}   total cache hits: {cache[2]}")
        print()


def _interval_24h():
    from datetime import timedelta
    return timedelta(hours=24)


def main() -> None:
    asyncio.run(_report())


if __name__ == "__main__":
    main()
