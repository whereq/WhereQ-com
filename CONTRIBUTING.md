# Contributing to whereq.com

Thanks for taking the time. This document covers how to get set up, what the
project expects from a change, and how to get it reviewed.

## Getting set up

You need **Python 3.12+**, **Node 20+**, and a **PostgreSQL 15+** instance
with PostGIS. Or just Docker.

```bash
git clone https://github.com/whereq/WhereQ-com.git
cd WhereQ-com

# Backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env                    # then edit DATABASE_URL
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (from the repo root, it is a yarn workspace)
yarn install
yarn dev
```

Or the whole stack in containers:

```bash
cp docker/.env.example docker/.env
docker compose -f docker/docker-compose.yml up -d --build
```

> The root `package.json` sets `"private": true`. That is **intentional** — it
> is what makes the directory a Yarn workspace root, and it also stops an
> accidental `npm publish`. Yarn prints a warning about it; ignore it.

Full setup instructions — the ports, the two Google keys, the crawler, the
crawl commands and troubleshooting — are in [docs/SETUP.md](docs/SETUP.md).

## Before you open a pull request

Run the same checks CI runs:

```bash
# Backend — from backend/
.venv/bin/python -m pytest -q

# Frontend — from the repo root
yarn typecheck
yarn build
```

All of them should pass. If a check fails, fix it before pushing — it is much
easier to review a green branch.

## Where things live

| Path | What goes there |
|---|---|
| `backend/app/api/routes/` | HTTP endpoints, one module per resource. Keep them thin. |
| `backend/app/services/` | Business logic. A route should stay thin. |
| `backend/app/models/` | SQLAlchemy ORM models. |
| `backend/app/schemas/` | Pydantic request and response models. |
| `backend/app/core/` | Settings, the database engine, security, permissions. |
| `backend/app/crawler/` | The retrieval layer — `upstream/` is one module per upstream (whereq.cloud, OpenStreetMap), plus the content crawl and the scheduler. |
| `backend/app/maps/` | The keyed Maps data service. |
| `backend/alembic/versions/` | Schema migrations, one per change. |
| `backend/tests/` | Tests. Fast, no database, no network. |
| `frontend/src/pages/` | One module per route. |
| `frontend/src/components/` | `layout/`, `map/`, `search/`, `sections/`, `ui/`. |
| `frontend/src/contexts/` | The shared state. |
| `frontend/src/lib/` | The API client and shared helpers. |
| `frontend/src/i18n/locales/` | `en.json`, `fr.json`, `zh.json`. |

## Changing the schema

Add an Alembic migration. The models are not the schema — the migrations are.

```bash
cd backend
.venv/bin/alembic revision -m "add a column to places"
.venv/bin/alembic upgrade head
```

Two rules:

1. **Every migration must run on an empty database.** That is what CI checks.
2. **Never edit a migration that has shipped.** Add a new one instead — people
   have already applied the old one.

`db/schema.sql` is a hand-written snapshot, not the source of truth. When the
two disagree, the migrations win.

## Adding a data provider

**A geocoding provider** (a service that turns an address into coordinates):

1. Put it in `backend/app/services/geocoding/`, behind the provider registry.
2. Keep the **free-tiers-first** ordering: the paid provider goes last, so the
   free quota absorbs the traffic. The order lives in
   `GEOCODE_PROVIDER_ORDER`.
3. Respect the rate limit. The whereq.cloud Data API allows 30 requests per
   minute per key; the existing clients throttle themselves, and yours must too.
4. Honour the source's terms, and carry its attribution. See
   [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

**An upstream the crawler pulls from** (a feed of places, prices, outlines or
articles):

1. Put it in `backend/app/crawler/upstream/`, one module per upstream.
2. Wire it into the scheduler in `backend/app/crawler/scheduler.py`, so it
   gets the same due-ness and retry handling as the others.
3. Give it a one-shot command in `backend/app/crawler/cli/`, so it can be run
   by hand.
4. Upsert by `(source, external_id)`, so a re-run converges instead of
   duplicating.

[CRAWLER.md](docs/CRAWLER.md) is the map of that layer.

## Adding a feature to the UI

- **Define the role once.** If your control means the same thing as an
  existing one, extend the existing component rather than writing a second
  one.
- **Every string goes through i18n.** Add the key to `en.json`, `fr.json` and
  `zh.json`.
- **The typecheck is strict.** `noUnusedLocals` and `noUnusedParameters` are
  on, so an unused import fails the build. That is on purpose.

## Commit messages

```
type(scope): summary
```

`type` is `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci` or
`chore`. `scope` is the area — `maps`, `places`, `crawler`, `auth`, `ui`. The
summary is in the imperative mood, under 72 characters.

## Pull requests

- One topic per pull request. Split the refactor from the feature.
- Say what changed and why in the description. If it fixes an issue, say
  which one.
- If it changes the schema, say so explicitly and include the migration.
- If it changes behaviour that a deployment depends on, say that too.

## Reporting a security problem

Not a public issue. See [SECURITY.md](SECURITY.md).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).

## Licence

By contributing you agree that your contribution is licensed under the MIT
License, the same as the rest of the project.
