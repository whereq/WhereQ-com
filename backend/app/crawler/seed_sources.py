"""Default crawler sources (Toronto/GTA to start).

Idempotent: upserts ``news_source`` rows by slug. Operators can add/disable
sources directly in the DB; this just bootstraps a useful default set.
RSS URLs may change over time — the crawler is resilient to a dead feed and
records ``last_status='error'`` rather than failing the whole run.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.local_content import NewsSource

DEFAULT_SOURCES: list[dict] = [
    {
        "slug": "blogto",
        "name": "BlogTO",
        "kind": "rss",
        "url": "https://www.blogto.com/rss/",
        "homepage_url": "https://www.blogto.com",
        "default_type": "story",
        "default_city": "Toronto", "default_province": "ON", "default_country": "CA",
        # Disabled: BlogTO's public RSS returns 404. Find a working feed URL and
        # re-enable in the DB (UPDATE news_source SET enabled=true ...).
        "enabled": False,
        "crawl_interval_minutes": 120,
        "config": {"item_limit": 60, "fetch_article": True},
    },
    {
        "slug": "citynews-toronto",
        "name": "CityNews Toronto",
        "kind": "rss",
        "url": "https://toronto.citynews.ca/feed/",
        "homepage_url": "https://toronto.citynews.ca",
        "default_type": "news",
        "default_city": "Toronto", "default_province": "ON", "default_country": "CA",
        "crawl_interval_minutes": 30,
        "config": {"item_limit": 80, "fetch_article": True},
    },
    {
        "slug": "cbc-toronto",
        "name": "CBC Toronto",
        "kind": "rss",
        "url": "https://www.cbc.ca/webfeed/rss/rss-canada-toronto",
        "homepage_url": "https://www.cbc.ca/news/canada/toronto",
        "default_type": "news",
        "default_city": "Toronto", "default_province": "ON", "default_country": "CA",
        # Disabled: this feed URL is not reachable from every network. Find a
        # working feed and re-enable it in the DB.
        "enabled": False,
        "crawl_interval_minutes": 30,
        "config": {"item_limit": 80},
    },
    {
        "slug": "cp24",
        "name": "CP24",
        "kind": "rss",
        "url": "https://www.cp24.com/rss",
        "homepage_url": "https://www.cp24.com",
        "default_type": "news",
        "default_city": "Toronto", "default_province": "ON", "default_country": "CA",
        # Disabled: CP24's RSS endpoint returns 404.
        "enabled": False,
        "crawl_interval_minutes": 20,
        "config": {"item_limit": 80},
    },
    {
        "slug": "global-news-toronto",
        "name": "Global News Toronto",
        "kind": "rss",
        "url": "https://globalnews.ca/toronto/feed/",
        "homepage_url": "https://globalnews.ca/toronto/",
        "default_type": "news",
        "default_city": "Toronto", "default_province": "ON", "default_country": "CA",
        "crawl_interval_minutes": 30,
        "config": {"item_limit": 80, "fetch_article": True},
    },
    {
        "slug": "toronto-star-gta",
        "name": "Toronto Star — GTA",
        "kind": "rss",
        "url": "https://www.thestar.com/feeds.articles.news.gta.rss",
        "homepage_url": "https://www.thestar.com/news/gta/",
        "default_type": "news",
        "default_city": "Toronto", "default_province": "ON", "default_country": "CA",
        # Disabled: the Star's feed URL now returns HTML, not RSS. Find a valid
        # feed and re-enable in the DB.
        "enabled": False,
        "crawl_interval_minutes": 30,
        "config": {"item_limit": 80, "fetch_article": True},
    },
    {
        # Events feed — drives explicit event start/end parsing. Disabled by
        # default until the feed URL is confirmed; enable in the DB to activate.
        "slug": "blogto-events",
        "name": "BlogTO Events",
        "kind": "rss",
        "url": "https://www.blogto.com/events/feed/",
        "homepage_url": "https://www.blogto.com/events/",
        "default_type": "event",
        "default_category": "event",
        "default_city": "Toronto", "default_province": "ON", "default_country": "CA",
        "enabled": False,
        "crawl_interval_minutes": 360,
        "config": {"item_limit": 60, "fetch_article": True},
    },
]


async def seed_default_sources(db: AsyncSession) -> tuple[int, int]:
    """Upsert the default sources. Returns (created, updated)."""
    created = updated = 0
    for spec in DEFAULT_SOURCES:
        existing = (await db.execute(
            select(NewsSource).where(NewsSource.slug == spec["slug"]))).scalar_one_or_none()
        if existing is None:
            db.add(NewsSource(**spec))
            created += 1
        else:
            # refresh non-identity fields without clobbering enabled/last_* state
            for k in ("name", "kind", "url", "homepage_url", "default_type",
                      "default_city", "default_province", "default_country",
                      "crawl_interval_minutes", "config"):
                setattr(existing, k, spec.get(k))
            updated += 1
    await db.commit()
    return created, updated
