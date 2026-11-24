"""The shared whereq.cloud client — one key, one rate limit.

Every whereq.cloud feed — the fuel stations, the price series, the geography,
the schools and the local layer — is one use of the **same** whereq.cloud
account, so they share the same upstream budget: the upstream enforces a
sliding 60-second window per key. Independent throttles would each allow the
full budget and the set would 429 itself — so the limiter lives here and is
shared.

The budget is the key's **tier**: 30 requests/minute on the free tier, 1 200
on the ``unlimited`` tier the whereq.com service key is on. The limiter
follows ``WHEREQ_CLOUD_RATE_LIMIT_PER_MIN`` rather than a constant, so the
pace matches the credential instead of assuming the smallest one.

Everything the feeds have in common is here: the client factory, the
throttle, the retry policy and the "is there a key?" check. The feeds keep
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

#: The upstream's own limit for a **free-tier** key: 30 requests per minute.
#: The whereq.com service key is on the `unlimited` tier (1 200/minute), so
#: this constant is the floor for a key that has no tier of its own — not the
#: pace every key is held to. See ``shared_interval()``.
FREE_TIER_MIN_INTERVAL = 2.0

#: The safety margin over the key's published limit. The upstream enforces a
#: sliding 60-second window, so a limiter that aims exactly at the limit is
#: always one burst away from a 429.
LIMIT_MARGIN = 1.2

#: The **floor** on the installed SDK.
#:
#: The app depends on a method that only exists from 0.8.1:
#: ``geo_boundaries(exclude_kind=...)`` — the bulk outline route's kind
#: exclusion, added in the SDK release of 2026-11-21. On 0.8.0 the call
#: raises ``TypeError: geo_boundaries() got an unexpected keyword argument
#: 'exclude_kind'`` — deep inside a request, for a reason that has nothing
#: to do with the data. A stale virtual environment is otherwise invisible
#: until a map pan asks for outlines.
#:
#: So the floor is checked, and it is checked against the **pin** in
#: ``backend/requirements.txt`` by a test — the two cannot drift apart.
SDK_FLOOR = "0.8.1"

#: What the floor is for, in the words a reader needs.
SDK_FLOOR_REASON = (
    "geo_boundaries(exclude_kind=...) — the bulk outline route's kind "
    "exclusion, which only exists from 0.8.1"
)


def _version_tuple(value: str) -> tuple[int, ...]:
    """``"0.8.1"`` → ``(0, 8, 1)``. Anything unparsable sorts last."""
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            return (0,)
        parts.append(int(digits))
    return tuple(parts)


def sdk_version() -> str:
    """The installed SDK's version."""
    return str(getattr(whereq_cloud, "__version__", "0"))


def check_sdk_version() -> None:
    """Fail loudly if the installed SDK is older than the app needs.

    Called by :func:`client`, so it is the *first* thing an upstream read
    does — not a ``TypeError`` from inside the SDK's own argument parsing.
    """
    installed = sdk_version()
    if _version_tuple(installed) >= _version_tuple(SDK_FLOOR):
        return
    raise RuntimeError(
        f"the installed whereq.cloud SDK is {installed}, but this app needs "
        f">= {SDK_FLOOR} — {SDK_FLOOR_REASON}. "
        f"Install it with: pip install -U 'whereq.cloud>={SDK_FLOOR}'"
    )


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

    The throttle is shared, so every whereq.cloud reader — the fuel stations,
    the price series, the geography and the local layer — is paced by this one
    number.

    The number comes from the **key's own tier**, not from a constant. The
    upstream enforces a sliding 60-second window and reports the key's limit
    on every response (``X-RateLimit-Limit``); the whereq.com service key is
    on the ``unlimited`` tier at 1 200 requests/minute, while a free-tier key
    is held to 30. A limiter built on the free tier's number would cap an
    unlimited key at 27 requests a minute — which is what it used to do, and
    what made the live read look unaffordable.

    A 20% margin is kept over the published limit, because a limiter aimed
    exactly at the ceiling is one burst away from a 429.
    """
    limit = max(1, settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN)
    return max(60.0 / limit * LIMIT_MARGIN, 0.05)


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
    check_sdk_version()
    return whereq_cloud.Client(
        api_key=settings.WHEREQ_CLOUD_API_KEY or None,
        timeout=settings.WHEREQ_CLOUD_TIMEOUT,
    )


def has_api_key() -> bool:
    return bool(settings.WHEREQ_CLOUD_API_KEY)
