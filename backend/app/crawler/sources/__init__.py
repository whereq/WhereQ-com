"""Source plugin registry.

Most sources are plain RSS and resolve to the generic ``RssSource`` via the
``news_source.kind`` column. Bespoke parsers register a slug-specific override
here. To add a new generic source, just insert a ``news_source`` row (see
``app.crawler.seed_sources``); no code change required.
"""

from __future__ import annotations

from app.crawler.base import BaseSource
from app.crawler.json_source import JsonSource
from app.crawler.rss import RssSource
from app.models.local_content import NewsSource

# kind -> default source class
_BY_KIND: dict[str, type[BaseSource]] = {
    "rss": RssSource,
    "json": JsonSource,
}

# slug -> bespoke override (takes precedence over kind)
_BY_SLUG: dict[str, type[BaseSource]] = {}


def register(slug: str, cls: type[BaseSource]) -> None:
    _BY_SLUG[slug] = cls


def get_source(source: NewsSource) -> BaseSource:
    cls = _BY_SLUG.get(source.slug) or _BY_KIND.get(source.kind)
    if cls is None:
        raise ValueError(f"No source plugin for slug={source.slug!r} kind={source.kind!r}")
    return cls(source)
