"""The shared whereq.cloud client — one key, one rate limit.

The fuel crawl and the geography crawl are two uses of the **same**
whereq.cloud account, so they share the same upstream budget: the API allows
**30 requests/minute**. Two independent throttles would each allow 30/min
and the pair would 429 each other — so the limiter lives here and is shared.

Everything the two crawls have in common is here: the client factory, the
throttle, the retry policy and the "is there a key?" check. The crawls keep
their own target grammars, row mappings and settings.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

import whereq_cloud

from app.core.config import settings

logger = logging.getLogger(__name__)

#: The upstream's own limit: 30 requests per minute.
UPSTREAM_MIN_INTERVAL = 2.0


class Throttle:
    """A client-side rate limiter.

    The interval may be a callable, so a shared limiter can follow the
    configuration instead of freezing it at import time.
    """

    def __init__(self, min_interval: float | Callable[[], float] = 0.0) -> None:
        self._interval = min_interval
        self._last = 0.0

    @property
    def min_interval(self) -> float:
        value = self._interval() if callable(self._interval) else self._interval
        return max(0.0, value)

    def wait(self) -> None:
        now = time.monotonic()
        delay = self.min_interval - (now - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


def shared_interval() -> float:
    """The interval that keeps the **combined** feed rate inside the limit.

    The throttle is shared, so this is the slowest of the two feeds' own
    settings — and never faster than the upstream's own limit.
    """
    return max(
        UPSTREAM_MIN_INTERVAL,
        settings.FUEL_CRAWL_MIN_INTERVAL,
        settings.GEO_CRAWL_MIN_INTERVAL,
    )


#: The one limiter for the whole whereq.cloud API.
shared_throttle = Throttle(shared_interval)


_RETRY_IN_RE = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)


def retry_delay(exc: Exception, attempt: int) -> float:
    """How long to wait before retrying: the API's own hint, else exponential."""
    message = str(getattr(exc, "message", "") or exc)
    match = _RETRY_IN_RE.search(message)
    if match:
        return min(float(match.group(1)) + 0.5, 120.0)
    return min(2.0 ** attempt, 60.0)


def call_with_retry(fn, *, attempts: int = 5, **kwargs: Any) -> Any:
    """Call an SDK method, retrying 429/5xx with backoff.

    The SDK raises ``WhereqError`` with ``.status``; 429 is the rate limiter
    and 5xx are transient upstream failures. Anything else is a real error
    (bad parameters, unknown country) and is raised immediately.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn(**kwargs)
        except whereq_cloud.WhereqError as exc:
            last = exc
            if exc.status != 429 and exc.status < 500:
                raise
            delay = retry_delay(exc, attempt)
            logger.warning("whereq.cloud %s — retrying in %.1fs (attempt %d/%d)",
                           exc.message, delay, attempt + 1, attempts)
            time.sleep(delay)
    assert last is not None
    raise last


def client() -> whereq_cloud.Client:
    """A configured SDK client. Callers must close it (it holds a pool)."""
    return whereq_cloud.Client(
        api_key=settings.WHEREQ_CLOUD_API_KEY or None,
        timeout=settings.WHEREQ_CLOUD_TIMEOUT,
    )


def has_api_key() -> bool:
    return bool(settings.WHEREQ_CLOUD_API_KEY)
