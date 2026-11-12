# Architecture

How whereq.com is put together: the layers, the request path, the data flow,
the auth model and the background jobs.

---

## The shape of it

A map is the centre of the product, and almost everything else is a layer on
top of it. The map is Google Maps; whereq.com supplies the *contents* of that
map — the places, the schools, the hazards, the news, the fuel stations, the
administrative boundaries — and the cards that describe them.

```
┌─────────────────────────────────────────────────────────────────────┐
│ browser                                                            │
│   React 18 · TypeScript · Vite · Tailwind · react-router           │
│   contexts: Map · Places · Routes · Friends · Auth · Theme        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  /api  (JSON + WebSocket)
┌───────────────────────────────▼─────────────────────────────────────┐
│ api — FastAPI                                                       │
│   routes/    thin HTTP layer, one module per resource              │
│   services/  the business logic                                   │
│   models/    SQLAlchemy ORM                                        │
│   schemas/   Pydantic I/O models                                   │
│   crawler/   the retrieval layer — every upstream pull             │
│   maps/      the keyed Maps data service                           │
└───────────┬──────────────────────────────────┬──────────────────────┘
            │ SQLAlchemy (asyncpg)            │ HTTP
┌───────────▼────────────────┐   ┌───────────▼────────────────────────┐
│ PostgreSQL 17 + PostGIS    │   │ whereq.cloud Data API              │
│ 18 Alembic migrations      │   │ Google Maps Platform              │
│ geometry columns + GiST    │   │ OpenStreetMap (Overpass)          │
└────────────────────────────┘   │ your OIDC realm                    │
                                 │ your RSS / JSON sources            │
┌────────────────────────────┐   └────────────────────────────────────┘
│ crawler — same image,        │
│ the scheduler loop instead   │
│ of uvicorn                   │
└────────────────────────────┘
```

---

## The backend

### Layers

| Layer | Directory | The rule |
|---|---|---|
| HTTP | `app/api/routes/` | Thin. Parse, delegate, serialise. No business logic. |
| Domain | `app/services/` | The business logic — geocoding, routing, taxonomy, dedup. |
| Retrieval | `app/crawler/` | Everything the app pulls from the outside world. `upstream/` is one module per upstream; the rest is the content crawl and the scheduler. |
| Persistence | `app/models/` | SQLAlchemy ORM models. |
| I/O | `app/schemas/` | Pydantic request and response models. |
| Cross-cutting | `app/core/` | Settings, the database engine, security, permissions, logging. |

A route that grows logic belongs in `app/services/`. A service that grows SQL
belongs in `app/models/`. A module that *fetches* something belongs in
`app/crawler/upstream/`.

### Request flow

`app/main.py` wires everything. Routers are registered under the `/api`
prefix and split into three groups:

- **Public** — anonymous browsing: places, neighbourhoods, stories, local
  content, the schools list and map, the hazards map, nearby search, route
  tracking, the newsletter signup, health.
- **Protected** — `Depends(get_current_user)`: users, saved places,
  notifications, friends, user settings.
- **Mixed** — schools and hazards are public to *browse*, but gate the
  sensitive parts per endpoint. A school's `boundary_geojson` and
  `GET /schools/at` both require a token.

Every response carries an `X-Request-Id`. The Maps service mirrors that id in
its error envelope, so one id ties a user-visible failure to the log line
that explains it.

### Settings

`app/core/config.py` is the single source of truth: every environment
variable name, its type and its default. `Settings` is a `pydantic-settings`
model reading `.env` relative to the working directory, so the backend must
be started from `backend/`.

Two properties of it are worth knowing:

- **`is_dev`** — in development the lifespan hook calls
  `Base.metadata.create_all`. That is a convenience for a fresh database, not
  the schema mechanism. Alembic is.
- **`unsafe_dev_mode`** — development mode enables SQL echo (every statement
  *and its bound parameters* — emails and tokens included) and `create_all`,
  which hides a missing migration. Both are unsafe against a shared
  database, so the app **refuses to start** when development mode is combined
  with a non-local `DATABASE_URL`.

---

## The auth model

There is no local session. The backend never issues a token.

```
browser ── keycloak.init(check-sso) ──▶ OIDC provider
        ◀── access_token (RS256 JWT) ──
        ── GET /api/...  Bearer <jwt> ──▶ FastAPI
                                          │  _get_jwks()  (cached 1 h)
                                          │  jwt.decode(RS256)
                                          │  verify iss + azp
                                          ▼
                                   local `users` row
```

- The SPA uses `onLoad: 'check-sso'` — an existing session is restored
  silently, anonymous visitors pass through untouched, and the app renders
  even when the provider is unreachable.
- The backend verifies the signature against the provider's JWKS (cached for
  an hour, serving stale keys if the provider is briefly down), checks the
  issuer, and checks `azp` against `KEYCLOAK_CLIENT_ID`.
- On the first authenticated request, `provision_user` maps the provider's
  `sub` onto a local `users` row — creating it, or linking a pre-existing
  local account with the same email. Everything else in the app references
  `users.id`, and this is the bridge.
- `get_optional_user` and `verify_token` (WebSockets) never raise, which is
  what lets anonymous browsing work.

**Authentication is optional.** With `KEYCLOAK_URL` empty, the app runs
anonymously and the protected endpoints answer 401. The walkthrough for
pointing it at your own realm is in [SETUP.md](SETUP.md).

---

## The database

PostgreSQL 17 with PostGIS. The geometry columns carry SRID 4326 and GiST
indexes, and the spatial queries are the reason PostGIS is not optional.

| Area | Tables |
|---|---|
| Identity | `users`, `friendship`, `notification`, `newsletter_subscriber`, `user_settings` |
| Places | `places`, `place_card`, `saved_place`, `neighborhood` |
| Geography | `geo_places` |
| Schools | `schools`, `school_facts`, `school_boundary`, and the history/provenance tables |
| Hazards | `hazards` and their geometry |
| Content | `local_content`, `stories`, `route` |
| Fuel | `fuel_stations`, `fuel_price_series`, `fuel_sync_state` |
| Maps service | `maps_consumer_key`, and the quota/rate tables |

**Alembic is the source of truth.** 18 migrations, applied in order. The
hand-written `db/schema.sql` is a convenience snapshot — when the two
disagree, the migrations win. See [DATABASE.md](DATABASE.md).

---

## The crawler

One container, one loop, five jobs. It reuses the API image and runs
`python -m app.crawler.scheduler` instead of uvicorn. It is the app's retrieval
layer — every datum on the map arrives through it.

```
tick
 ├─ content    RSS + JSON sources → local_content (raw)
 ├─ place      classify → extract a location → geocode → set the geometry
 ├─ fuel       whereq.cloud fuel stations + prices, one target per tick
 ├─ geo        whereq.cloud administrative geography, one target per tick
 └─ poi        OpenStreetMap POIs, when the newest OSM row is stale
```

Two things make the placement step reliable:

- **A provider chain, not a single provider.** Geocoding tries
  `geocode_maps_co → locationiq → geocodio → nominatim → google`. The paid
  provider is last, so the free tiers absorb the traffic and the paid quota
  is only spent when everything else is exhausted. Unconfigured providers are
  skipped.
- **A guard, not a hope.** A candidate is only accepted if it lands within a
  sane distance of the content's own city centre (20 km for a generic
  candidate, 60 km for a curated place). A mis-geocode puts a pin in the
  wrong city, and that is worse than no pin.

Everything the crawler does is **idempotent** — it upserts by
`(source, external_id)`, so a re-run converges instead of duplicating.

The whereq.cloud Data API allows 30 requests per minute per key, so the fuel
and geography crawls take **one target per tick**. Being faster than the limit
only earns a 429.

The whole layer is described in [CRAWLER.md](CRAWLER.md).

---

## The frontend

React 18, TypeScript, Vite, Tailwind, react-router.

| Directory | What lives there |
|---|---|
| `src/pages/` | One module per route. |
| `src/components/` | `layout/`, `map/`, `search/`, `sections/`, `ui/`, `notifications/`. |
| `src/contexts/` | The shared state — the map selection, the places, the route, the friends, the auth, the theme. |
| `src/hooks/` `src/lib/` | Shared helpers, the API client, the i18n wiring. |
| `src/i18n/` | `en`, `fr`, `zh`. |

Two decisions worth knowing about:

- **The typecheck is the gate.** `tsconfig.app.json` is strict with
  `noUnusedLocals` and `noUnusedParameters`, and `tsconfig.json` is
  solution-style (`"files": []` + `references`) — a bare `tsc` compiles zero
  files. The build script therefore names both projects explicitly, and the
  production image runs `yarn build`, not `vite build`. A type error fails
  the image build instead of shipping.
- **The shared controls are defined once.** A radius picker that looks
  different in two places is two controls, not one — the component and the
  radius list live in one place and are reused.

The API client keeps the token fresh and **silently falls back to anonymous**
if a refresh fails, so a public endpoint still loads when the identity
provider is down.

---

## The Maps data service

`/api/maps/v1` is a keyed data API served by the same backend: geocode,
autocomplete, reverse geocode, route, matrix and static map. It exists so
other applications can consume whereq.com's geocoding without holding a
Google key — whereq.com owns the key, the provider fallback, the caching and
the quota.

Auth is an opaque per-consumer key, independent of the OIDC provider. Only the
SHA-256 hash and a short prefix are stored; the plaintext is printed once at
mint time and never again.

---

## Deployment shapes

| | |
|---|---|
| **Local dev** | Vite on 3743 proxying to uvicorn on 8000. The Vite proxy carries WebSocket upgrades for the live-location feature. |
| **Docker** | nginx on 80 (published as 3743) proxying `/api` to the API on 8002. Same-origin, so the WebSocket handshake needs no token in the URL in production. |
| **Compose** | Postgres, migrate, api, crawler, frontend. The API waits for the migration to finish, so the schema is always current. |

The production images are multi-stage: a builder that installs the
dependencies, and a runtime stage that carries only the installed packages
and the source. The API image runs as a non-root user.
