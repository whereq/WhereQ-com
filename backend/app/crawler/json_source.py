"""Generic JSON-API source plugin (kind='json').

Demonstrates non-RSS extensibility: many event/municipal APIs return JSON.
Field mapping is fully config-driven (no code per source) via the news_source
``config`` column, e.g.:

    {
      "items_path": "events",                 # dotted path to the list (optional)
      "params": {"city": "toronto"},          # query params for the request
      "item_limit": 60,
      "fields": {
        "id": "id", "title": "name.text", "url": "url",
        "summary": "summary", "image": "logo.url",
        "published": "published", "start": "start.utc", "end": "end.utc",
        "address": "venue.address.localized_address_display"
      }
    }

Dotted paths traverse nested dicts. Datetimes are parsed from ISO-8601.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.crawler.base import BaseSource, RawItem

logger = logging.getLogger(__name__)

_UA = "WhereQNewsCrawler/1.0 (+https://whereq.com)"


def _dig(obj, path: str | None):
    """Traverse a dotted path through nested dicts; return None if missing."""
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _parse_iso(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class JsonSource(BaseSource):
    async def fetch(self) -> list[RawItem]:
        cfg = self.config
        fields: dict = cfg.get("fields", {})
        limit = int(cfg.get("item_limit", 60))

        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": _UA},
                                     follow_redirects=True) as client:
            resp = await client.get(self.source.url, params=cfg.get("params") or None)
            resp.raise_for_status()
            payload = resp.json()

        raw_items = _dig(payload, cfg.get("items_path"))
        if not isinstance(raw_items, list):
            logger.warning("JsonSource %s: items_path did not resolve to a list", self.source.slug)
            return []

        out: list[RawItem] = []
        for it in raw_items[:limit]:
            title = _dig(it, fields.get("title", "title"))
            if not title:
                continue
            url = _dig(it, fields.get("url", "url"))
            external_id = _dig(it, fields.get("id", "id")) or url
            summary = _dig(it, fields.get("summary", "summary"))
            published = _parse_iso(_dig(it, fields.get("published", "published")))
            start = _parse_iso(_dig(it, fields.get("start", "")))
            end = _parse_iso(_dig(it, fields.get("end", "")))
            image = _dig(it, fields.get("image", ""))
            address = _dig(it, fields.get("address", ""))

            out.append(RawItem(
                external_id=str(external_id) if external_id is not None else None,
                url=url, title=str(title).strip(),
                summary=str(summary).strip() if summary else None,
                content=str(summary).strip() if summary else None,
                image_url=image, published=published or start,
                raw={"json_start": start.isoformat() if start else None,
                     "json_end": end.isoformat() if end else None,
                     "address": address},
            ))
        return out
