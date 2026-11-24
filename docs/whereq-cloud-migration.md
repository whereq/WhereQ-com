# WhereQ-com ↔ whereq.cloud — the read-side migration

This is the operator's guide to the switch between the two places the data
can come from: **this app's own tables** and **whereq.cloud**, the platform
that collects it.

It is written for a self-hosted installation of this repository. It assumes
you have read `docs/SETUP.md` and that your stack is running.

---

## 0. The one-paragraph version

whereq.cloud collects the geography, the schools, the fuel prices and the
local content. This app **reads** them. Every read is a switch:

| Switch | The API reads | The app behaves like |
|---|---|---|
| `local` | this app's own tables only | the pre-cut app, from its own copy |
| `dual` | both — compares them, **serves the local answer** | exactly like `local` |
| `cloud` | whereq.cloud only | the cut |

There are three switches, because the three feeds are separate decisions:

| Switch | Feed | Default here |
|---|---|---|
| `CLOUD_READ_MODE` | the administrative geography | `cloud` |
| `SCHOOL_READ_MODE` | the school directory | `cloud` |
| `FUEL_READ_MODE` | the fuel stations and the price series | `cloud` |

`GEO_BOUNDARIES_READ_MODE` is a fourth, narrower one: the outlines are
served in bulk by one upstream request, so they have their own switch.
**Empty means "follow `CLOUD_READ_MODE`"** — one switch for the whole
geography unless you want to split it.

This installation **reads live by default**. The mirrors are off, because a
second copy of data the platform already owns is the copy that goes stale.

---

## 1. What is already in place

| Piece | Where | What it does |
|---|---|---|
| The SDK pin | `backend/requirements.txt` | `whereq.cloud>=0.8.1` — the floor is enforced at runtime and pinned by a test |
| The switches | `backend/app/core/config.py` | `CLOUD_READ_MODE`, `SCHOOL_READ_MODE`, `FUEL_READ_MODE`, `GEO_BOUNDARIES_READ_MODE` |
| The routes | `backend/app/api/routes/{geo,schools,fuel}.py` | honour the mode |
| The upstream readers | `backend/app/services/cloud_{geo,schools,fuel}.py` | page the SDK at its cap and say whether the answer was **whole** |
| The comparator | `backend/app/services/cloud_parity.py` | decides match / differ / partial / error |
| The ledger | `backend/app/models/cloud_parity.py` + `backend/alembic/versions/019_cloud_parity_checks.py` | where the comparisons are written |
| The report | `scripts/cloud_parity_report.py` | reads the ledger and says READY or NOT READY |
| The deployment wiring | `docker/docker-compose.yml` | the switches reach the `api` service |

### The surfaces the geography switch covers

| Surface | Upstream |
|---|---|
| `/geo/places` | `/v1/geo/places` |
| `/geo/places/{uid}` | `/v1/geo/places/{uid}` |
| `/geo/places/{uid}/boundary` | `/v1/geo/places/{uid}/boundary` |
| `/geo/concepts` | `/v1/geo/concepts` |
| `/geo/at` | `/v1/geo/at` |
| `/geo/boundaries` | `/v1/geo/boundaries` (bulk, one viewport at a time) |

---

## 2. What counts as a defect

| | A defect? | Why |
|---|---|---|
| The local copy holds a row the upstream does not | **yes** — `only_local` | the local copy has something the original no longer has |
| Both hold it, and a value differs | **yes** — `differing` | the two answers disagree |
| The upstream holds a row the local copy does not | **no** | that is the local copy's coverage, not a defect |
| Upstream could not be read | **error**, never a match | a window full of errors is a window with no evidence in it |
| Either side was **truncated** | **partial**, never a defect | see below |

### A difference needs a whole population

A comparison is only evidence when **both** sides were fetched whole. The
upstream pages its listings; a page that stopped early is not a shorter
answer, it is an *unknown* answer. So a truncated comparison is recorded as
`partial` — not a defect, and not a clean match either.

This is the rule that keeps the ledger meaningful. A comparison that flags
everything is as useless as one that flags nothing.

---

## 3. The rollback

The rollback is one switch and one recreate. Nothing else changes:

```bash
# in docker/.env
CLOUD_READ_MODE=local
SCHOOL_READ_MODE=local
FUEL_READ_MODE=local

docker compose -f docker/docker-compose.yml up -d --force-recreate api
```

Two things to know before you use it:

1. **`local` serves this app's own tables.** In this installation the
   mirrors are **off**, so those tables are empty until the mirrors are
   turned on. The rollback is therefore two variables for the feeds that
   have a mirror:

   ```bash
   FUEL_MIRROR_ENABLED=true     # the fuel stations and the price series
   GEO_INGEST_ENABLED=true      # the administrative geography
   ```

   and then let the `crawler` service fill them:

   ```bash
   docker compose -f docker/docker-compose.yml logs -f crawler
   ```

2. **The mirrors are the rollback, not the default.** The reads above go to
   whereq.cloud; a second copy held here would be the copy that goes stale.
   Turning a mirror on is a decision, and it is reversible.

`--force-recreate` is what makes the switch take effect: the mode is read
at import time, so a container that is merely *restarted* keeps the old
value if it was recreated from a stale image.

---

## 4. Reading the evidence

The comparisons are written to the `cloud_parity_checks` table. The report
reads that table and says READY or NOT READY:

```bash
# the report cannot be run from the host — it has no dependencies of its
# own — so it is copied into the container and run there
docker cp scripts/cloud_parity_report.py whereq-com-api:/tmp/cloud_parity_report.py
docker exec -i whereq-com-api python /tmp/cloud_parity_report.py --days 7 --verbose
```

To compare one window only:

```bash
docker exec -i whereq-com-api python /tmp/cloud_parity_report.py --window schools --verbose
```

> **READY means agreement, not duration.** The report says the two answers
> agree; it does not say the window has been open for long. A window that
> has been open for a minute and a window that has been open for a week
> look the same to it.

The history stays in the ledger on purpose — a window that forgets what went
wrong is a window nobody can learn from.

---

## 5. The service key

Every feed is one use of the **same** whereq.cloud account, so the key's
budget is shared by all of them. The client-side limiter follows the key's
own tier (`WHEREQ_CLOUD_RATE_LIMIT_PER_MIN`), because a limiter built on the
free tier's number would throttle a paid key to nothing.

| Scope | For |
|---|---|
| `fuel` | the fuel stations |
| `prices` | the fuel price series |
| `geo` | the geography, its outlines and its concepts |
| `local` | the local content and the places feed |
| `school` | the open school facts |
| `school_licensed` | the catchment polygons and the assessment scores |

The key is server-side only. It is never built into the frontend bundle.

The licensed scope is **not** optional for the catchments: a key without
`school_licensed` gets the open facts and **not** the polygons. That is a
field-level difference, not a 403 — the school still appears, without its
outline.

The fuel prices are licensed too, and they are served to signed-in callers
only. Anonymous callers get the station without its prices.

---

## 6. The school window

The school directory is keyed by the **uid** — the board's slug and the
school's own code joined by a slash, `ycdsb/0158`. The uid carries a slash,
so the routes use a converter that is told one slash is part of the id;
without it every lookup of every school would 404.

If you keep your own school rows and want to compare them against the
upstream, the local rows need the uid before the comparison can join on it.
The seed fills it and never guesses:

```bash
docker cp scripts/seed_school_uids.py whereq-com-api:/tmp/
docker compose -f docker/docker-compose.yml exec -T api \
    sh -c 'cd /app && PYTHONPATH=backend python /tmp/seed_school_uids.py'
```

Run it with `--dry-run` first. It only fills a missing uid, never overwrites
one, and it reports every row it could not settle — a row it cannot settle
is a row the comparison cannot join on.

---

## 7. Before you flip a switch

- [ ] `WHEREQ_CLOUD_API_KEY` is set and the key carries the scopes the feeds
      need (`fuel`, `prices`, `geo`, `local`, `school`, `school_licensed`).
- [ ] The SDK floor is satisfied: `pip show whereq.cloud` reports **0.8.1**
      or newer. The app refuses to start a read against an older SDK.
- [ ] `scripts/cloud_parity_report.py` says **READY** for the window.
- [ ] You know how to roll back (§3), and you have tested that the rollback
      command is one step, not a procedure.

---

## 8. Where the data comes from

| Feed | Collected by | Read here |
|---|---|---|
| The geography | whereq.cloud | live, by default |
| The schools | whereq.cloud | live, by default |
| The fuel prices | whereq.cloud | live, by default |
| The news, events and stories | whereq.cloud | mirrored into `local_content` by the `crawler` service |
| The POI catalogue | whereq.cloud | mirrored into `places` by the `crawler` service |

The last two are mirrored by design: they are the **local layer** this app
serves directly, and the `crawler` service reads them back from the
platform. `LEGACY_COLLECTORS_ENABLED` is the rollback for those two — it
turns the old RSS and Overpass collectors back on.
