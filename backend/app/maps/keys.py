"""Maps API key management — reusable helpers + a CLI.

CLI:
    python -m app.maps.keys mint   --name my-consumer --scopes autocomplete,geocode,reverse,route
    python -m app.maps.keys list
    python -m app.maps.keys rotate --name my-consumer
    python -m app.maps.keys revoke --prefix wq_live_9f3c

Minting/rotating prints the plaintext key **once** — it is never recoverable.
Rotation issues a fresh key and leaves the previous one active (grace window);
revoke it once the consumer has cut over.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.maps.auth import generate_key
from app.models.maps import MAPS_SCOPES, MapsApiConsumer


def _parse_scopes(csv: str) -> list[str]:
    scopes = [s.strip() for s in csv.split(",") if s.strip()]
    bad = [s for s in scopes if s not in MAPS_SCOPES]
    if bad:
        raise ValueError(f"Unknown scope(s): {', '.join(bad)}. "
                         f"Valid: {', '.join(sorted(MAPS_SCOPES))}")
    return scopes


async def create_consumer(db: AsyncSession, *, name: str, scopes: list[str],
                          rate_limit_per_min: int | None = None,
                          monthly_quota: int | None = None,
                          env: str = "live") -> tuple[MapsApiConsumer, str]:
    """Create a consumer + key. Returns ``(consumer, plaintext_key)``."""
    plaintext, key_hash, key_prefix = generate_key(env)
    consumer = MapsApiConsumer(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=scopes,
        rate_limit_per_min=rate_limit_per_min or settings.MAPS_DEFAULT_RATE_LIMIT_PER_MIN,
        monthly_quota=monthly_quota or settings.MAPS_DEFAULT_MONTHLY_QUOTA,
    )
    db.add(consumer)
    await db.commit()
    await db.refresh(consumer)
    return consumer, plaintext


async def rotate_consumer(db: AsyncSession, *, name: str,
                          env: str = "live") -> tuple[MapsApiConsumer, str]:
    """Issue a fresh key for the latest active consumer with ``name``.

    Creates a new consumer row cloning the settings of the most recent active
    one; the old key stays valid until you revoke it (grace window).
    """
    latest = (await db.execute(
        select(MapsApiConsumer)
        .where(MapsApiConsumer.name == name, MapsApiConsumer.active.is_(True))
        .order_by(MapsApiConsumer.created_at.desc())
    )).scalars().first()
    if latest is None:
        raise ValueError(f"No active consumer named {name!r} to rotate")
    return await create_consumer(
        db, name=name, scopes=list(latest.scopes or []),
        rate_limit_per_min=latest.rate_limit_per_min,
        monthly_quota=latest.monthly_quota, env=env)


async def revoke_consumer(db: AsyncSession, *, prefix: str | None = None,
                          consumer_id: str | None = None) -> int:
    """Soft-disable matching consumer(s). Returns the number revoked."""
    q = select(MapsApiConsumer).where(MapsApiConsumer.active.is_(True))
    if consumer_id:
        q = q.where(MapsApiConsumer.id == uuid.UUID(consumer_id))
    elif prefix:
        q = q.where(MapsApiConsumer.key_prefix == prefix)
    else:
        raise ValueError("Provide --prefix or --id")
    rows = (await db.execute(q)).scalars().all()
    for c in rows:
        c.active = False
        c.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return len(rows)


async def list_consumers(db: AsyncSession) -> list[MapsApiConsumer]:
    return list((await db.execute(
        select(MapsApiConsumer).order_by(MapsApiConsumer.created_at.desc())
    )).scalars().all())


# ── CLI ─────────────────────────────────────────────────────────────────────
def _print_key(consumer: MapsApiConsumer, plaintext: str) -> None:
    print("\n  ── Maps API key minted (store it now — shown only once) ──")
    print(f"  consumer : {consumer.name}  ({consumer.id})")
    print(f"  scopes   : {', '.join(consumer.scopes or [])}")
    print(f"  limits   : {consumer.rate_limit_per_min}/min, {consumer.monthly_quota}/month")
    print(f"  key      : {plaintext}\n")


async def _run(args) -> None:
    async with AsyncSessionLocal() as db:
        if args.command == "mint":
            consumer, plaintext = await create_consumer(
                db, name=args.name, scopes=_parse_scopes(args.scopes),
                rate_limit_per_min=args.rate, monthly_quota=args.quota, env=args.env)
            _print_key(consumer, plaintext)
        elif args.command == "rotate":
            consumer, plaintext = await rotate_consumer(db, name=args.name, env=args.env)
            _print_key(consumer, plaintext)
        elif args.command == "revoke":
            n = await revoke_consumer(db, prefix=args.prefix, consumer_id=args.id)
            print(f"Revoked {n} consumer(s).")
        elif args.command == "list":
            for c in await list_consumers(db):
                state = "active" if c.active else "revoked"
                print(f"  {c.key_prefix:<14} {state:<8} {c.name:<20} "
                      f"scopes=[{','.join(c.scopes or [])}] "
                      f"{c.rate_limit_per_min}/min {c.monthly_quota}/mo")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.maps.keys",
                                description="Maps API key management")
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("mint", help="Create a new consumer + key")
    m.add_argument("--name", required=True, help="Consumer name, e.g. my-consumer")
    m.add_argument("--scopes", required=True,
                   help="CSV: autocomplete,geocode,reverse,route,matrix,static")
    m.add_argument("--rate", type=int, default=None, help="Requests per minute")
    m.add_argument("--quota", type=int, default=None, help="Requests per month")
    m.add_argument("--env", default="live", help="Key env segment (live/test)")

    r = sub.add_parser("rotate", help="Issue a fresh key for an existing consumer")
    r.add_argument("--name", required=True)
    r.add_argument("--env", default="live")

    rv = sub.add_parser("revoke", help="Revoke a key by prefix or id")
    rv.add_argument("--prefix", default=None, help="e.g. wq_live_9f3c")
    rv.add_argument("--id", default=None, help="Consumer UUID")

    sub.add_parser("list", help="List consumers")

    args = p.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
