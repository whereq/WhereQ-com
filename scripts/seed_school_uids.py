#!/usr/bin/env python
"""Seed this app's school rows with the uid — the key whereq.cloud uses.

WHY THIS EXISTS
---------------
whereq.cloud's school routes are keyed by the **uid**: the board's slug and
the school's own code, joined by a slash — ``ycdsb/0158``,
``dcdsb/austin``. This app's school rows are keyed by an integer row id,
which is a key in this app's own database and in nowhere else.

The rows are the same rows on both sides — an import preserved this app's
integers, so id 5 is ``dcdsb/austin`` in both databases — but the *key* is
not the same, and a dual-read window needs a key the two systems agree on.
So the uid is copied in, from whereq.cloud, into the ``school.uid`` column
that migration 020 added.

WHAT IT DOES AND DOES NOT DO
----------------------------
* It **only fills** a uid that is missing. A row that already has one is
  left exactly as it is — the uid is the platform's to change, and this
  script is not the place to argue about it.
* It **never guesses**. The match is on the row id, which the import
  preserved exactly. A row that does not match is *reported*, not matched
  by name, by slug or by proximity. A wrong uid on a school is worse than
  no uid: a dual-read window would compare two different schools and
  call them the same.
* It **touches no other column**. The local tables are kept, read-only, for
  the rollback window; this adds one column's worth of values and changes
  nothing else.

WHEN IT IS NEEDED
-----------------
This installation reads the schools from whereq.cloud live
(``SCHOOL_READ_MODE=cloud``), so the local tables are not what the app
serves. The seed matters only when the local school tables hold rows of
your own — an imported directory — and you want to run the ``dual`` mode
to compare them against the upstream.

HOW TO RUN IT
-------------
On the host, inside the API container (the image does not bundle
``scripts/``):

    docker cp scripts/seed_school_uids.py whereq-com-api:/tmp/
    docker compose -f docker/docker-compose.yml exec -T api \\
        sh -c 'cd /app && PYTHONPATH=backend python /tmp/seed_school_uids.py'

The API key comes from the environment (``WHEREQ_CLOUD_API_KEY``). It is
never written down, and the script never prints it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# The app package lives under ``backend/`` in the repository and at ``/app``
# inside the container. Both are tried, so the script runs from either.
for _candidate in (Path(__file__).resolve().parents[1] / "backend", Path("/app")):
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.whereq_cloud_client import (  # noqa: E402
    call_with_retry,
    client as cloud_client,
    shared_throttle,
)


async def fetch_upstream() -> list[dict]:
    """Every school whereq.cloud holds, with its uid and its row id.

    One call: the whole directory is 2 528 rows and the upstream's limit
    goes to 5 000. The upstream's own count is checked, because a truncated
    answer is not an answer — it would seed half the schools and leave the
    rest looking like schools the platform lost.
    """
    client = cloud_client()
    try:
        shared_throttle.wait()
        payload = call_with_retry(client.schools, limit=5000, offset=0)
    finally:
        client.close()

    payload = payload or {}
    rows = payload.get("data") or []
    pagination = payload.get("pagination") or {}
    total = pagination.get("total")
    if total is not None and len(rows) < int(total):
        raise SystemExit(
            f"the upstream answered {len(rows)} of {total} schools — "
            "refusing to seed a truncated answer"
        )
    return rows


async def seed(dry_run: bool = False) -> int:
    upstream = await fetch_upstream()
    print(f"upstream: {len(upstream)} schools")

    by_id: dict[int, str] = {}
    for row in upstream:
        row_id = row.get("id")
        uid = row.get("uid")
        if row_id is None or not uid:
            continue
        by_id[int(row_id)] = uid
    print(f"upstream: {len(by_id)} rows carry a usable id and uid")

    async with AsyncSessionLocal() as db:
        # Raw SQL on purpose: the seed runs **before** the application knows
        # about the column — the migration adds it, and the model grows it
        # afterwards. Writing it this way means the seed does not depend on
        # which side of that boundary it is run from.
        local = (await db.execute(
            text("SELECT id, uid, name FROM school ORDER BY id"))).all()
        matched = 0
        already = 0
        unmatched: list[tuple[int, str]] = []
        conflicts: list[tuple[int, str, str, str]] = []
        updates: list[tuple[str, int]] = []

        for school_id, uid, name in local:
            platform_uid = by_id.get(int(school_id))
            if platform_uid is None:
                unmatched.append((school_id, name))
                continue
            if uid:
                already += 1
                if uid != platform_uid:
                    # The local uid disagrees with the platform's. The
                    # platform is the source of truth for the uid, but this
                    # is a disagreement worth a human's eyes, not something
                    # to overwrite silently.
                    conflicts.append((school_id, name, uid, platform_uid))
                continue
            matched += 1
            updates.append((platform_uid, school_id))

        print(f"local: {len(local)} schools")
        print(f"  already carry a uid: {already}")
        print(f"  to be filled:         {matched}")
        print(f"  no upstream row:      {len(unmatched)}")
        print(f"  uid disagreements:    {len(conflicts)}")

        for school_id, name, local_uid, platform_uid in conflicts[:20]:
            print(f"    id {school_id} {name!r}: local {local_uid!r} != platform {platform_uid!r}")
        for school_id, name in unmatched[:20]:
            print(f"    id {school_id} {name!r}: the platform has no row with this id")

        if dry_run:
            print("dry run — nothing written")
            return 0

        if updates:
            # One statement, not one per row: 2 528 UPDATEs would be 2 528
            # round trips to the database, and this is a one-off that runs
            # against a live database.
            #
            # The values are bound, never interpolated — the uid comes from
            # another system, and a statement built by string concatenation
            # is a statement that can be broken by a value.
            params: dict = {}
            tuples = []
            for index, (uid, school_id) in enumerate(updates):
                params[f"uid_{index}"] = uid
                params[f"id_{index}"] = school_id
                # The casts are not decoration: without them Postgres
                # infers the VALUES columns as text, and `bigint = text`
                # is not an operator it has.
                #
                # ``CAST(... AS ...)`` rather than ``::`` — SQLAlchemy's
                # ``text()`` reads a double colon as an escaped colon and
                # hands Postgres a single one.
                tuples.append(
                    f"(CAST(:uid_{index} AS varchar), CAST(:id_{index} AS bigint))"
                )
            await db.execute(
                text("UPDATE school AS s SET uid = v.uid "
                     f"FROM (VALUES {', '.join(tuples)}) AS v(uid, id) "
                     "WHERE s.id = v.id"),
                params,
            )
            await db.commit()
            print(f"wrote {len(updates)} uids")

        if unmatched or conflicts:
            print()
            print("There are rows this script could not settle. The uid is the key the")
            print("dual-read window joins on, so a row without one is a row that cannot")
            print("be compared. Look at them before opening the window.")
            return 1
    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(asyncio.run(seed(dry_run=dry)))
