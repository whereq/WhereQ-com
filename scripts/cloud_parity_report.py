#!/usr/bin/env python
"""Read the dual-read ledger and say whether the cut is safe.

The cut decision rests on the ledger: the comparisons the app took while it
was reading from both places. This script is how that evidence is read.

    python scripts/cloud_parity_report.py                 # the last 7 days
    python scripts/cloud_parity_report.py --days 30
    python scripts/cloud_parity_report.py --surface geo_places --verbose
    python scripts/cloud_parity_report.py --window schools --verbose

WHAT "CLEAN" MEANS
------------------
Two things make a comparison a failure:

* **only_local** — the mirror holds a place upstream does not. The mirror
  has something the original no longer has.
* **differing** — both sides hold the place, and the values disagree.

A place upstream holds and the mirror does not is NOT a failure. The mirror
is a copy restricted to the targets this installation syncs, so upstream is
always at least as broad. Counting that as a difference would drown the
signal.

**An error is not a clean comparison.** If upstream could not be read, the
comparison did not happen — and a window full of errors is a window with no
evidence in it.

**A partial is not a clean comparison either.** A comparison is *partial*
when one of the two sides was truncated — the upstream's answer was paged
and stopped early, or the mirror's answer hit the limit. A truncated
answer cannot tell "upstream lost this place" from "the page stopped
here", so the comparison is inconclusive: no difference is written, and the
row is recorded as partial. Partial rows carry no evidence, so a surface
whose latest comparison is a partial is a surface that has not been
checked.

WHAT THE VERDICT IS ABOUT
-------------------------
The verdict is over the **latest** comparison of each surface — that is the
surface's state *now*, and the state now is what the cut is decided on. The
older rows are history: they are how the window got here, and they stay in
the ledger, because a window that forgets what went wrong is a window
nobody can learn from.

But a bug that was fixed an hour ago must not veto the cut forever, or no
window would ever pass. So the history is printed beside the verdict, and
the verdict itself is about the present.

This is not a theoretical worry. Measured against the live API: the upstream
holds 32 954 places, the mirror holds the 304 of them inside whereq.com's
coverage targets, and the upstream's first 500 rows contain 10 of the
mirror's. Comparing those two populations reported 294 of 304 mirror rows
as places the upstream had lost — 97% false defects.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.cloud_parity import CloudParityCheck  # noqa: E402

#: The two windows, and the surfaces each one decides.
#:
#: They share one ledger, but they are **separate decisions**: cutting the
#: schools says nothing about the geography feed. So the report can be asked
#: about one window or the other — a verdict that mixes the two would say
#: "NOT READY" for a cut that is not the one being considered.
WINDOWS = {
    "geo": ("geo_places", "geo_boundary", "geo_boundaries", "geo_at",
            "geo_concepts", "geo_place"),
    "schools": ("school_list", "school_detail", "school_boundary",
                "school_at", "school_taxonomy", "school_stats"),
}


async def summarise(days: int, surface: str | None, verbose: bool,
                    window: str | None = None) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        conds = [CloudParityCheck.checked_at >= since]
        if surface:
            conds.append(CloudParityCheck.surface == surface)
        elif window:
            conds.append(CloudParityCheck.surface.in_(WINDOWS[window]))

        rows = (await db.execute(
            select(CloudParityCheck).where(*conds)
            .order_by(CloudParityCheck.checked_at.asc())
        )).scalars().all()

        print(f"the last {days} day(s)"
              + (f" — surface {surface}" if surface else "")
              + (f" — the {window} window" if window else ""))
        print()
        if not rows:
            print("  no comparisons recorded.")
            print()
            print("  Is CLOUD_READ_MODE=dual? The ledger only fills while it is.")
            return 1

        # The **latest** comparison of each surface is that surface's state
        # now, and the state now is what the cut is decided on. The older
        # rows are history: they are how the window got here, and they stay
        # in the ledger because a window that forgets what went wrong is a
        # window nobody can learn from. But a bug that was fixed an hour ago
        # must not veto the cut forever — or no window would ever pass.
        #
        # So: the verdict is over the latest row per surface, and the
        # history is printed beside it.
        latest: dict[str, object] = {}
        history: dict[str, dict[str, int]] = {}
        for row in rows:
            latest[row.surface] = row
            history.setdefault(row.surface, {})[row.status] = (
                history.setdefault(row.surface, {}).get(row.status, 0) + 1
            )

        header = (f"{'surface':<16} {'now':<8} {'n':>6} "
                  f"{'local rows':>12} {'cloud rows':>12}   history")
        print(header)
        print("-" * len(header))
        for surface_name in sorted(latest):
            row = latest[surface_name]
            counts = history.get(surface_name, {})
            past = " ".join(f"{count} {status}" for status, count in sorted(counts.items()))
            print(f"{surface_name:<16} {row.status:<8} {sum(counts.values()):>6} "
                  f"{row.local_count or 0:>12} {row.cloud_count or 0:>12}   {past}")
        print()

        total = {"match": 0, "differ": 0, "error": 0, "partial": 0}
        for row in latest.values():
            total[row.status] = total.get(row.status, 0) + 1
        clean = total.get("match", 0)
        differ = total.get("differ", 0)
        error = total.get("error", 0)
        partial = total.get("partial", 0)
        print("  the latest comparison of each surface:")
        print(f"  matching   {clean}")
        print(f"  differing  {differ}")
        print(f"  errors     {error}")
        print(f"  partial    {partial}   (inconclusive — no evidence either way)")
        print()
        print("  and the whole window, for the record:")
        whole = {"match": 0, "differ": 0, "error": 0, "partial": 0}
        for counts in history.values():
            for status, count in counts.items():
                whole[status] = whole.get(status, 0) + count
        print(f"  matching   {whole.get('match', 0)}")
        print(f"  differing  {whole.get('differ', 0)}")
        print(f"  errors     {whole.get('error', 0)}")
        print(f"  partial    {whole.get('partial', 0)}")
        print()

        if verbose:
            recent = [row for row in rows if row.status != "match"][-20:]
            if recent:
                print("  the comparisons that were not clean:")
                for row in recent:
                    print(f"    {row.checked_at.isoformat()}  {row.surface}  {row.status}")
                    if row.error:
                        print(f"      error: {row.error[:200]}")
                    if row.status == "partial":
                        print("      one of the two sides was truncated — inconclusive")
                    for uid in (row.only_local or [])[:10]:
                        print(f"      only local: {uid}")
                    for uid, fields in list((row.differing or {}).items())[:10]:
                        print(f"      differs: {uid} {fields}")
                print()

        if error:
            print("  NOT READY — some comparisons could not be made.")
            print("  A window with errors is a window with no evidence in it.")
            return 1
        if differ:
            print("  NOT READY — the two answers disagree.")
            print("  Read the differences above before moving the mode to 'cloud'.")
            return 1

        # A surface whose latest comparison was a partial has not been
        # checked, however good the other surfaces look.
        unchecked = sorted(
            name for name, row in latest.items() if row.status == "partial"
        )
        if unchecked:
            print("  NOT READY — these surfaces have no clean comparison yet:")
            for surface in unchecked:
                print(f"    {surface}")
            print("  A partial comparison is the absence of evidence, not agreement.")
            return 1

        if not clean:
            print("  NOT READY — nothing has been compared yet.")
            return 1

        print("  READY — every comparison that could be made, matched.")
        print("  This is AGREEMENT, not DURATION. The window still has to run for")
        print("  one full content cycle per class before the cut — a clean hour is")
        print("  not a clean week.")
        if window == "schools":
            print("  The next step is the cut: SCHOOL_READ_MODE=cloud.")
        else:
            print("  The next step is the cut: CLOUD_READ_MODE=cloud.")
            print("  (and then, once the boundaries surface is cut too, the")
            print("   collectors can be stopped.)")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7,
                        help="how far back to look (default 7)")
    parser.add_argument("--surface", default=None,
                        help="only this surface (e.g. geo_places)")
    parser.add_argument("--window", default=None, choices=sorted(WINDOWS),
                        help="only one window's surfaces: the geography feed or the "
                             "schools. The two are separate decisions, so a verdict "
                             "should not mix them.")
    parser.add_argument("--verbose", action="store_true",
                        help="list the comparisons that were not clean")
    args = parser.parse_args()
    if args.surface and args.window:
        parser.error("--surface and --window cannot both be given")
    return asyncio.run(summarise(args.days, args.surface, args.verbose, args.window))


if __name__ == "__main__":
    raise SystemExit(main())
