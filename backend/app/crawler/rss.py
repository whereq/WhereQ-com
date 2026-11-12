"""Generic RSS/Atom source plugin.

Fetches the feed over HTTP (so we control timeouts/UA), parses it with
feedparser, and extracts a usable summary + image per entry. Optionally
fetches each article page to pull an og:image / fuller text when the feed
omits them (controlled by ``config.fetch_article``).

Most sources (BlogTO, CityNews, CP24, CBC, municipal feeds) are plain RSS and
need no code — just a ``news_source`` row. Bespoke sources subclass BaseSource.
"""

from __future__ import annotations

import logging
import re

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.crawler.base import BaseSource, RawItem, struct_time_to_dt

logger = logging.getLogger(__name__)

_UA = "WhereQNewsCrawler/1.0 (+https://whereq.com)"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip() or None


def _entry_image(entry) -> str | None:
    # media:content / media:thumbnail
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key)
        if media and isinstance(media, list) and media[0].get("url"):
            return media[0]["url"]
    # enclosure links
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image"):
            return link.get("href")
    # <img> inside summary/content
    html = entry.get("summary") or ""
    if entry.get("content"):
        html += entry["content"][0].get("value", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    return m.group(1) if m else None


class RssSource(BaseSource):
    async def fetch(self) -> list[RawItem]:
        limit = int(self.config.get("item_limit", 60))
        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": _UA},
                                     follow_redirects=True) as client:
            resp = await client.get(self.source.url)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

        items: list[RawItem] = []
        for entry in feed.entries[:limit]:
            url = entry.get("link")
            external_id = entry.get("id") or url
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            summary = _strip_html(entry.get("summary"))
            content = None
            if entry.get("content"):
                content = _strip_html(entry["content"][0].get("value"))
            published = struct_time_to_dt(entry.get("published_parsed")) or \
                struct_time_to_dt(entry.get("updated_parsed"))
            items.append(RawItem(
                external_id=external_id, url=url, title=title,
                summary=summary, content=content or summary,
                image_url=_entry_image(entry), published=published,
                raw={"feed_title": feed.feed.get("title")},
            ))

        if self.config.get("fetch_article"):
            await self._enrich_articles(items)
        return items

    async def _enrich_articles(self, items: list[RawItem]) -> None:
        """Fetch each article page to backfill missing image/content (best-effort)."""
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _UA},
                                     follow_redirects=True) as client:
            for item in items:
                if item.image_url and item.content:
                    continue
                if not item.url:
                    continue
                try:
                    r = await client.get(item.url)
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "lxml")
                    if not item.image_url:
                        og = soup.find("meta", property="og:image")
                        if og and og.get("content"):
                            item.image_url = og["content"]
                    if not item.content:
                        desc = soup.find("meta", property="og:description") or \
                            soup.find("meta", attrs={"name": "description"})
                        if desc and desc.get("content"):
                            item.content = desc["content"].strip()
                except Exception as exc:  # best-effort enrichment
                    logger.debug("Article enrich failed for %s: %s", item.url, exc)
