"""API-key auth, scopes, rate limiting, and monthly quota for the Maps service.

Keys are opaque: ``wq_<env>_<base62>``. Only a sha256 hash + a short prefix are
stored. Auth is server-to-server (Bearer), independent of Keycloak.

The per-minute limit is an in-process token bucket (fine for the single ``api``
container; if the API is ever horizontally scaled this should move to a shared
store such as Redis). The monthly cap is DB-backed via ``maps_api_usage``.
"""

from __future__ import annotations

import hashlib
import math
import secrets
import string
import time
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.maps.errors import MapsError
from app.maps.usage import monthly_request_count
from app.models.maps import MapsApiConsumer

KEY_PREFIX_LEN = 12
_B62 = string.digits + string.ascii_letters


def _b62(nbytes: int = 32) -> str:
    n = int.from_bytes(secrets.token_bytes(nbytes), "big")
    out = ""
    while n:
        n, r = divmod(n, 62)
        out = _B62[r] + out
    return out or "0"


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def generate_key(env: str = "live") -> tuple[str, str, str]:
    """Return ``(plaintext, key_hash, key_prefix)``. Plaintext is shown once."""
    plaintext = f"wq_{env}_{_b62(32)}"
    return plaintext, hash_key(plaintext), plaintext[:KEY_PREFIX_LEN]


# ── in-process per-key token bucket ─────────────────────────────────────────
# id -> (tokens, last_monotonic)
_buckets: dict[str, tuple[float, float]] = {}


def _check_rate(consumer: MapsApiConsumer) -> tuple[bool, int]:
    """Consume one token. Returns ``(allowed, retry_after_seconds)``."""
    rate = max(1, consumer.rate_limit_per_min)
    now = time.monotonic()
    tokens, last = _buckets.get(str(consumer.id), (float(rate), now))
    tokens = min(float(rate), tokens + (now - last) * rate / 60.0)
    if tokens < 1.0:
        retry = math.ceil((1.0 - tokens) / (rate / 60.0))
        _buckets[str(consumer.id)] = (tokens, now)
        return False, max(1, retry)
    _buckets[str(consumer.id)] = (tokens - 1.0, now)
    return True, 0


def _seconds_to_month_end() -> int:
    now = datetime.now(timezone.utc)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0,
                          second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1, hour=0, minute=0,
                          second=0, microsecond=0)
    return int((nxt - now).total_seconds())


async def _authenticate(request: Request, db: AsyncSession) -> MapsApiConsumer:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise MapsError(401, "unauthenticated", "Missing or malformed Authorization header")
    token = auth[len("Bearer "):].strip()
    if not token:
        raise MapsError(401, "unauthenticated", "Empty bearer token")
    consumer = (await db.execute(
        select(MapsApiConsumer).where(MapsApiConsumer.key_hash == hash_key(token))
    )).scalar_one_or_none()
    if consumer is None or not consumer.active or consumer.revoked_at is not None:
        raise MapsError(401, "unauthenticated", "Invalid or revoked API key")
    return consumer


def require_maps_key(scope: str):
    """Dependency factory: authenticate the key, enforce ``scope`` + limits."""

    async def dependency(request: Request,
                         db: AsyncSession = Depends(get_db)) -> MapsApiConsumer:
        consumer = await _authenticate(request, db)

        if scope not in (consumer.scopes or []):
            raise MapsError(403, "forbidden_scope",
                            f"API key is not authorized for scope '{scope}'")

        allowed, retry = _check_rate(consumer)
        if not allowed:
            raise MapsError(429, "rate_limited",
                            "Per-minute rate limit exceeded", retry_after=retry)

        used = await monthly_request_count(db, consumer.id)
        if used >= consumer.monthly_quota:
            raise MapsError(429, "rate_limited", "Monthly quota exceeded",
                            retry_after=_seconds_to_month_end())

        return consumer

    return dependency
