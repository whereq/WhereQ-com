<div align="center">

# whereq.com

**A location-based services platform — a map, the places on it, and the stories around them.**

[MIT licensed](LICENSE) · Python 3.12+ · React 18 + Vite · PostgreSQL 17 + PostGIS

</div>

---

whereq.com is a map-centric web app. You open it, you see the places around
you — coffee, food, parking, fuel, schools, hazards, local news — and you can
look at any one of them properly: a card with its address, its hours, its
rating, the photos, the route to it.

The map is the product. Every other feature hangs off it.

## What you get

| | |
|---|---|
| **Places** | A curated POI map, plus a nearby search that merges everything within a radius into one ranked list. |
| **Place cards** | A full page per place — photos, address, hours, categories, the route, the notes people left. |
| **Schools** | Every school in the coverage area with its catchment boundary, drawn on the map. |
| **Hazards** | Environmental and infrastructure hazards, mapped. |
| **Local content** | Local news, events and stories, crawled from RSS and JSON feeds and placed on the map. |
| **Stories** | Longer-form pieces tied to the places they describe. |
| **Fuel** | Fuel stations and live prices, crawled from the whereq.cloud Data API. |
| **Geography** | The administrative areas that *contain* the places — provinces, cities, wards, neighbourhoods — with real outlines. |
| **Routes** | Route tracking and a route planner over the same map. |
| **Social** | Friends, saved places, notifications. |
| **Bilingual** | English, French and Simplified Chinese throughout the interface. |

## The crawler

Nothing on the map was typed in by hand. The **crawler** pulls it, refreshes
it, and writes it into the database; the app serves what it crawled.

| Upstream | What it crawls |
|---|---|
| **whereq.cloud** | Fuel stations, live prices, the aggregated price series, and the administrative geography with its outlines |
| **OpenStreetMap** | The POI layer — coffee, food, parking, pharmacies, libraries, plazas |
| **RSS / JSON feeds** | Local news, events, stories and community topics |

The crawler is one scheduler with one cadence, and it lives in
`backend/app/crawler/`. See **[docs/CRAWLER.md](docs/CRAWLER.md)** for the
whole retrieval layer.

## What you need to run it

Nothing is bundled that a stranger could not get for themselves. There is no
pre-seeded database, no scraper and no anonymous fallback to a hosted service.

| Secret | Why | Where it goes |
|---|---|---|
| **Your OIDC provider** | Logins and roles. The shipped values are placeholders — point them at your own realm, or leave them empty and run in anonymous mode. | `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID` |
| **Google Maps key + Map ID** | The map itself. Without them the map does not render; everything else still works. | `GOOGLE_MAPS_API_KEY`, `VITE_GOOGLE_MAPS_API_KEY` |
| **whereq.cloud API key** *(optional)* | Fuel stations, prices and administrative geography. Without it those panels are empty; the public preview feed works for the demo. | `WHEREQ_CLOUD_API_KEY` |

**You do not need any of them to build, test or lint the project.** The
backend's test suite runs without a database, the frontend build needs no keys,
and the app boots in anonymous mode with an empty configuration.

## Quick start

### Docker Compose (recommended)

```bash
git clone https://github.com/whereq/WhereQ-com.git
cd WhereQ-com

cp docker/.env.example docker/.env
# edit docker/.env — set POSTGRES_PASSWORD and SECRET_KEY at minimum

docker compose -f docker/docker-compose.yml up -d --build
```

The app comes up on **<http://localhost:3743>** and the API on
**<http://localhost:8002>**. The compose stack is self-contained: it brings up
PostgreSQL 17 with PostGIS, runs the Alembic migrations, and starts the API,
the crawler and the nginx-served frontend.

Migrations run automatically as part of `up`. To apply them by hand:

```bash
docker compose -f docker/docker-compose.yml run --rm migrate
```

### Local development

```bash
# Backend — from backend/
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # then edit DATABASE_URL
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend — from the repo root, it is a yarn workspace
yarn install
yarn dev                                   # http://localhost:3743
```

The frontend dev server proxies `/api` to `localhost:8000`. See
**[docs/SETUP.md](docs/SETUP.md)** for the full guide — the ports, the two
Google keys, the crawler, the crawl commands and troubleshooting.

## Architecture at a glance

```
                    ┌───────────────┐
 browser ──────────▶│   frontend    │  React 18 + TypeScript + Vite
                    │  (nginx)      │  served by nginx in production
                    └───────┬───────┘
                            │ /api
                    ┌───────▼───────┐
                    │      api      │  FastAPI
                    │               │  places · schools · hazards · content
                    │               │  nearby · cards · fuel · geo · maps
                    └───────┬───────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌───────▼─────────┐  ┌──────▼──────────┐
│    crawler     │  │  PostgreSQL 17  │  │  OIDC provider  │
│ whereq.cloud   │◀▶│  PostGIS        │  │  (yours)        │
│ OSM · RSS/JSON │  │  18 migrations  │  └─────────────────┘
└────────────────┘  └─────────────────┘
```

Four processes, three of them optional to run separately:

- **`api`** — the FastAPI application. Serves the REST API, the WebSocket
  channel for live location, and the Maps data service.
- **`crawler`** — the retrieval layer. A self-contained scheduler loop that
  crawls whereq.cloud, OpenStreetMap and the content feeds, and keeps the
  database current. No host cron needed.
- **`frontend`** — the React app.
- **`postgres`** — PostgreSQL 17 with PostGIS.

### The Maps data service

`/api/maps/v1` is a keyed **data API** — geocode, autocomplete, reverse geocode,
route, matrix and static map — served by the same backend. It exists so other
applications can consume whereq.com's geocoding without holding a Google key.

## Repository layout

```
WhereQ-com/
├── backend/
│   ├── app/
│   │   ├── api/routes/       HTTP endpoints, one module per resource
│   │   ├── core/             settings, database, security, permissions
│   │   ├── models/           SQLAlchemy ORM models
│   │   ├── schemas/          Pydantic request/response models
│   │   ├── services/         business logic (geocoding, routing, taxonomy)
│   │   ├── crawler/          the retrieval layer
│   │   │   ├── upstream/     one module per upstream (whereq.cloud, OSM)
│   │   │   └── cli/          one-shot crawl commands
│   │   └── maps/             the keyed Maps data service
│   ├── alembic/              schema migrations
│   ├── tests/                the test suite
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       layout, map, search, sections, ui
│   │   ├── contexts/         map, places, routes, friends, auth, theme
│   │   ├── hooks/  lib/      shared helpers and the API client
│   │   ├── pages/            one module per route
│   │   └── i18n/             en / fr / zh
│   ├── public/
│   └── package.json
├── db/schema.sql             a snapshot of the schema (Alembic is the source of truth)
├── docker/                   Dockerfiles, nginx config, the Compose stack
├── docs/                     architecture, setup, crawler, data sources
└── .github/                  CI, issue and pull-request templates
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Getting it running: ports, keys, sign-in, the crawler, the crawl commands. |
| [docs/CRAWLER.md](docs/CRAWLER.md) | The retrieval layer: the upstreams, the targets, the content feeds. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The system end to end — layers, data flow, the auth model, the background jobs. |
| [docs/DATABASE.md](docs/DATABASE.md) | The schema, table by table, and how the migrations work. |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Every data feed, its licence, and its attribution obligation. |

## Development

```bash
# Backend — from backend/
.venv/bin/python -m pytest -q              # the test suite
.venv/bin/alembic upgrade head              # apply the migrations
.venv/bin/python -m app.seed                # demo data (no credentials)

# Frontend — from the repo root
yarn typecheck                               # tsc, strict
yarn build                                   # typecheck + the production bundle
```

The backend suite needs **no database**: the tests that need one are opt-in
and skip unless `WHEREQ_TEST_DATABASE_URL` points at a migrated database.

Four gates run in CI on every push and pull request:

| Gate | What it proves |
|---|---|
| **Backend** | The test suite passes. |
| **Frontend** | The typecheck passes and the production bundle builds. |
| **Docker** | Both production images build, and the Compose stack is valid. |
| **Secret scan** | No credential is committed — the guard that stops this class of problem from ever coming back. |

## Contributing

Pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md)
first, and note that [SECURITY.md](SECURITY.md) explains how to report a
vulnerability privately rather than in a public issue.

## License

MIT — see [LICENSE](LICENSE). Third-party notices are in [NOTICE](NOTICE).

---

**Attribution.** The map is Google Maps Platform; the POI crawl reads
OpenStreetMap data; the fuel and geography crawls pull from whereq.cloud. See
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for the attribution each one
requires.
