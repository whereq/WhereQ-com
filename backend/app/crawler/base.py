"""Crawler source abstractions.

A *source plugin* turns a ``NewsSource`` row into a list of ``RawItem``s. The
pipeline (``app.crawler.pipeline``) then normalizes, geocodes, classifies, and
persists them. Adding a new source = add a row to ``news_source`` (for generic
RSS) or register a ``BaseSource`` subclass for bespoke parsing.
"""

from __future__ import annotations

import calendar
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.local_content import NewsSource


@dataclass
class RawItem:
    """A single item fetched from a source, before normalization."""

    external_id: str | None
    url: str | None
    title: str
    summary: str | None = None
    content: str | None = None
    image_url: str | None = None
    published: datetime | None = None
    raw: dict = field(default_factory=dict)


class BaseSource(ABC):
    """Fetches and yields RawItems for a NewsSource."""

    def __init__(self, source: NewsSource):
        self.source = source
        self.config: dict = source.config or {}

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        """Return the current batch of items for this source."""
        raise NotImplementedError


def struct_time_to_dt(st) -> datetime | None:
    """Convert a feedparser ``*_parsed`` struct_time (UTC) to an aware datetime."""
    if not st:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None
