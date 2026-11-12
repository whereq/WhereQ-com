# Setup

Getting whereq.com running, locally or in a container. The short version is
in the [README](../README.md); this is the full guide.

---

## Requirements

| | |
|---|---|
| **Docker + Docker Compose** | The recommended path. Everything else is optional. |
| **Python 3.12+** | The backend. The production image uses 3.14. |
| **Node 20+** | The frontend build. The production image uses Node 24. |
| **PostgreSQL 15+ with PostGIS** | The database. The migrations create the PostGIS extension themselves. |

---

## The Docker path

```bash
git clone https://github.com/whereq/WhereQ-com.git
cd WhereQ-com

cp docker/.env.example docker/.env
# edit docker/.env — at minimum set POSTGRES_PASSWORD and SECRET_KEY

docker compose -f docker/docker-compose.yml up -d --build
```

The stack starts four services:

| Service | Port | What it is |
|---|---|---|
| `frontend` | 3743 | nginx serving the built SPA, proxying `/api` to the API |
| `api` | 8002 | the FastAPI application |
| `crawler` | — | the background crawler: it crawls whereq.cloud, OpenStreetMap and the content feeds |
| `postgres` | — | PostgreSQL 17 + PostGIS |

A fifth service, `migrate`, runs `alembic upgrade head` and exits. The API
waits for it to finish successfully, so the schema is always current before
the first request. To apply migrations by hand:

```bash
docker compose -f docker/docker-compose.yml run --rm migrate
```

To watch what the crawler is doing:

```bash
docker compose -f docker/docker-compose.yml logs -f crawler
```

To stop and remove everything, including the database volume:

```bash
docker compose -f docker/docker-compose.yml down -v
```

### What the stack refuses to start without

`POSTGRES_PASSWORD` and `SECRET_KEY` are declared with `${VAR:?message}`
rather than a fallback. Compose **fails to start** when they are missing,
instead of quietly booting with a default that looks like a real
configuration. That is deliberate — a missing secret should be loud.

---

## Local development

### Backend

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.lock

cp .env.example .env
# edit .env — DATABASE_URL must point at your database

.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

The API is then on <http://localhost:8000>, with its OpenAPI docs at
`/api/docs`.

**Run the backend from `backend/`.** The `app.*` imports are absolute and
`Settings` reads `.env` relative to the working directory, so `pytest`,
`alembic` and the `python -m app.*` entry points all expect to be run from
there.

### Frontend

From the **repo root** — it is a yarn workspace:

```bash
yarn install
yarn dev
```

The dev server is on <http://localhost:3743> and proxies `/api` to
`localhost:8000`, including WebSocket upgrades for the live-location feature.

```bash
yarn typecheck   # tsc over both tsconfig projects
yarn build       # typecheck + the production bundle
yarn preview     # serve the built bundle
```

`tsconfig.app.json` is strict, with `noUnusedLocals` and
`noUnusedParameters` — an unused import fails the build. That is on purpose:
the typecheck is the frontend's only real gate.

---

## Ports

The ports differ by context, and the difference is not accidental:

| | Port |
|---|---|
| Frontend dev server | **3743** |
| Backend local dev (uvicorn) | **8000** — matches the Vite proxy target |
| Backend in Docker | **8002** |
| Frontend in Docker | nginx on 80, published as **3743** |

---

## Environment variables

Three files hold configuration, and none of them are committed:

| File | Read by |
|---|---|
| `backend/.env` | the backend when you run it locally |
| `frontend/.env` | Vite, when you run it locally (`VITE_*` only) |
| `docker/.env` | the Compose stack |

Each has an `.example` template that is tracked.

**Backend settings** live in `backend/app/core/config.py` — that file is the
single source of truth for every name and default. The most important ones:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | a localhost placeholder | The async URL. |
| `DATABASE_URL_SYNC` | — | The sync URL, used by Alembic. |
| `SECRET_KEY` | `change-me` | A random 64-character string. |
| `APP_ENV` | `development` | `production` turns off `create_all` and SQL echo. |
| `CORS_ORIGINS` | `["http://localhost:3743"]` | A JSON list. |
| `KEYCLOAK_URL` | *empty* | Empty means **no authentication**. See [Enabling sign-in](#enabling-sign-in). |
| `GOOGLE_MAPS_API_KEY` | *empty* | The browser key. |
| `GOOGLE_MAPS_SERVER_KEY` | *empty* | The server key — a *different* key, without a referrer lock. |
| `WHEREQ_CLOUD_API_KEY` | *empty* | The Data API key. |
| `NOMINATIM_EMAIL` | *empty* | A contact address for the OSM usage policy. |

### Two Google keys, and they are not interchangeable

`VITE_GOOGLE_MAPS_API_KEY` is a **browser** key with an HTTP-referrer
restriction. The backend cannot use it: Google rejects a referrer-locked key
on a web-service call with `API_KEY_HTTP_REFERRER_BLOCKED`. That is why
`GOOGLE_MAPS_SERVER_KEY` exists — a second key with no referrer restriction,
restricted by IP and/or API allowlist instead.

---

## Enabling sign-in

With `KEYCLOAK_URL` and `VITE_KEYCLOAK_URL` empty — the default — the app runs
in **anonymous mode**: the public browsing endpoints work, and the sign-in
control stays hidden. That is enough to develop, build and demo the app.

Authentication is delegated to an **OIDC provider**. Keycloak is the reference
implementation, but any OIDC-compatible provider works as long as it mints
**RS256** access tokens — the backend only *verifies* the token and maps the
`sub` claim onto a local `users` row. It never issues a session of its own.

To enable sign-in, stand up your own realm and point these at it:

```
KEYCLOAK_URL=https://auth.example.com
KEYCLOAK_REALM=whereq
KEYCLOAK_CLIENT_ID=whereq-spa
```

The SPA also needs its own copy of the provider URL (`VITE_KEYCLOAK_URL`,
`VITE_KEYCLOAK_REALM`, `VITE_KEYCLOAK_CLIENT_ID` in `frontend/.env`).

### The SPA client

One client, `whereq-spa`, of type *OpenID Connect*:

| Setting | Value |
|---|---|
| Client type | OpenID Connect |
| Client authentication | **OFF** (a public client) |
| Standard flow | **ON** (Authorization Code + PKCE) |
| Direct access grants / Implicit / Device | **OFF** |

Its URLs, for a local run:

| Field | Value |
|---|---|
| Root URL | `http://localhost:3743` (your deployment's origin) |
| Valid redirect URIs | `http://localhost:3743/*`, `http://localhost:5173/*` |
| Valid post logout redirect URIs | `http://localhost:3743/*`, `http://localhost:5173/*` |
| Web origins | `http://localhost:3743`, `http://localhost:5173` |

**Web origins take no wildcard** — a bare origin only (scheme + host + port).
The redirect URIs do take the `/*`. PKCE (`S256`) is enabled by default for
public clients and is what the SPA requests.

A misconfigured redirect URI locks the whole app out, so set it before you
deploy.

### The backend client (optional)

Only needed if the backend calls the provider's Admin REST API (for example to
assign roles). Token *verification* does not require it.

| Setting | Value |
|---|---|
| Client authentication | **ON** (a confidential client) |
| Client ID | `whereq-backend` |
| Client secret | your own — `KEYCLOAK_ADMIN_CLIENT_SECRET` |

---

## The database

Migrations are the only supported way to change the schema.

```bash
cd backend
.venv/bin/alembic upgrade head                  # apply everything
.venv/bin/alembic revision -m "add a column"    # a new migration
.venv/bin/alembic downgrade -1                  # step back one
```

In development (`APP_ENV=development`) the lifespan hook auto-creates tables
from the models via `Base.metadata.create_all`. **That is a convenience, not
the mechanism** — it hides a missing migration. Change a model, add a
migration.

> The backend **refuses to start** with `APP_ENV=development` when
> `DATABASE_URL` points at a non-local host. Development mode enables SQL echo
> — every statement *and its bound parameters*, emails and tokens included —
> and `create_all`. Neither is safe against a shared database, so the
> combination is a hard startup failure rather than a quiet misbehaviour.

See [DATABASE.md](DATABASE.md) for the schema.

---

## Seeding demo data

```bash
cd backend
.venv/bin/python -m app.seed
```

This inserts a small set of demo places, a neighbourhood, some stories and two
demo **user rows with no password** — authentication is delegated to the OIDC
provider, so there is nothing to log in with. A real user row is created
automatically on the first authenticated request.

The seed is idempotent: it refuses to run twice.

---

## The crawler

The crawler container runs the scheduler loop — the app's retrieval layer. From
`backend/`, the same loop runs locally:

```bash
.venv/bin/python -m app.crawler.scheduler      # the loop
.venv/bin/python -m app.crawler.stats          # a read-only report
```

It does five things on a cadence:

1. **Crawls the content feeds** — the configured RSS and JSON sources.
2. **Places** each crawled item on the map, using the geocoding provider
   chain.
3. **Crawls fuel stations and prices** from whereq.cloud, one target per tick.
4. **Crawls administrative geography** from whereq.cloud, one target per tick.
5. **Crawls the OpenStreetMap POIs**, when the newest OSM row is stale.

Steps 3 and 4 are throttled on purpose — the whereq.cloud Data API allows 30
requests per minute per key.

See [CRAWLER.md](CRAWLER.md) for the whole retrieval layer.

---

## The crawl commands

Each of these is idempotent (it upserts by `(source, external_id)`), so
running one twice is safe.

```bash
cd backend

# OpenStreetMap POIs → places
.venv/bin/python -m app.crawler.cli.places
.venv/bin/python -m app.crawler.cli.places --only food,coffee,pharmacy
.venv/bin/python -m app.crawler.cli.places --bbox -79.64,43.58,-79.12,43.86

# whereq.cloud → fuel stations, prices
.venv/bin/python -m app.crawler.cli.fuel
.venv/bin/python -m app.crawler.cli.fuel --target "CA:Ontario:Toronto"
.venv/bin/python -m app.crawler.cli.fuel --prices
.venv/bin/python -m app.crawler.cli.fuel --allow-demo

# whereq.cloud → administrative geography
.venv/bin/python -m app.crawler.cli.geo
.venv/bin/python -m app.crawler.cli.geo --target "kind:ward"
.venv/bin/python -m app.crawler.cli.geo --boundaries

# One content crawl, by hand
.venv/bin/python -m app.crawler.run --list
.venv/bin/python -m app.crawler.run --source citynews-toronto --limit 20

# Re-place content that has no coordinates
.venv/bin/python -m app.crawler.regeocode --dry-run
.venv/bin/python -m app.crawler.regeocode --limit 200
.venv/bin/python -m app.crawler.regeocode --recheck
.venv/bin/python -m app.crawler.regeocode --check-places
```

---

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

The default run needs **no database** and no network. The handful of tests
that need a real Postgres are opt-in and skip unless
`WHEREQ_TEST_DATABASE_URL` points at a migrated database:

```bash
cd backend
WHEREQ_TEST_DATABASE_URL=postgresql+asyncpg://whereq@127.0.0.1:5432/whereq_test \
  .venv/bin/python -m pytest -q
```

---

## Troubleshooting

**The map is blank.** The Google Maps key or the Map ID is missing, or the
browser key's referrer restriction does not cover your origin. Check
`VITE_GOOGLE_MAPS_API_KEY` and `VITE_GOOGLE_MAPS_MAP_ID`.

**`API_KEY_HTTP_REFERRER_BLOCKED` from the backend.** You are using the
browser key for a server-side call. Set `GOOGLE_MAPS_SERVER_KEY` to a separate
key without a referrer restriction.

**Every protected endpoint returns 401.** Either authentication is not
configured — that is expected in anonymous mode — or `KEYCLOAK_URL` is wrong.
See [Enabling sign-in](#enabling-sign-in).

**The backend exits immediately at startup.** Look for the dev-mode guard: with
`APP_ENV=development` and a non-local `DATABASE_URL`, it refuses to start on
purpose. Set `APP_ENV=production` for a remote database, or use a local one
while developing.

**The crawler is doing nothing.** Check that `CRAWLER_ENABLED` is true and
that a source is configured (`python -m app.crawler.run --list`). The whereq.cloud
crawls also need a `WHEREQ_CLOUD_API_KEY` to pull anything beyond the public
preview.

**`docker compose up` fails with "variable is not set".** That is the
deliberate `:?` guard. Set `POSTGRES_PASSWORD` and `SECRET_KEY` in
`docker/.env`.

**A migration fails with "extension postgis is not available".** The
database is a plain PostgreSQL without PostGIS. Use the `postgis/postgis`
image, or install the extension on your server.
