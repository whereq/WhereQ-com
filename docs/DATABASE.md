# The database

PostgreSQL 17 with PostGIS. The spatial columns carry SRID 4326 and GiST
indexes — the viewport queries and the point-in-polygon tests are the reason
PostGIS is not optional.

---

## Migrations are the schema

`backend/alembic/versions/` is the source of truth. 18 migrations, applied in
order.

```bash
cd backend
.venv/bin/alembic upgrade head              # apply everything
.venv/bin/alembic downgrade -1              # step back one
.venv/bin/alembic revision -m "message"     # write a new one
.venv/bin/alembic current                   # where am I?
.venv/bin/alembic history                   # what has been applied
```

Two rules that matter:

1. **Every migration must run on an empty database.** The Compose stack
   proves it on every start — `migrate` runs against a fresh Postgres and the
   API waits for it to succeed.
2. **Never edit a migration that has shipped.** People have already applied
   it. Add a new one.

`db/schema.sql` is a **generated snapshot** of what the migrations produce.
It is there so you can read the shape of the database without running
anything. When the two disagree, the migrations win. The regeneration command
is in the header of the file.

---

## The tables

40 tables — 39 of them the application's, plus Alembic's version marker.
Here is what each one is for.

### Identity

| Table | Cols | What it holds |
|---|---|---|
| `users` | 10 | The local user row. `keycloak_id` is the OIDC `sub`; `hashed_password` is nullable and unused — the backend never issues a session. |
| `friendships` | 5 | The friend graph between users. |
| `user_settings` | 5 | Per-user preferences — the saved nearby radius, the theme, the locale. |
| `notifications` | 7 | The notification feed. |
| `newsletter_subscribers` | 3 | The email signup list. |

### Places

| Table | Cols | What it holds |
|---|---|---|
| `places` | 19 | Every POI on the map. Carries the PostGIS `geom` point, the crawl provenance (`source`, `external_id`) and the category taxonomy. |
| `place_cards` | 23 | The long-form card for a place — photos, hours, notes, ownership. |
| `saved_places` | 5 | A user's saved places. |
| `neighborhoods` | 17 | The named neighbourhoods, with their boundary and their scores. |

### Geography

| Table | Cols | What it holds |
|---|---|---|
| `geo_places` | 37 | The administrative areas that *contain* the places — provinces, cities, wards, neighbourhoods — with their outlines, their kind and their source. The `license` and `source_url` columns carry the attribution of the upstream (ODbL / CC-BY), and the API serves them. |
| `geo_concepts` | 9 | The vocabulary of administrative kinds, refreshed from the feed. |
| `geo_sync_state` | 12 | How far each geography target has been crawled. |

### Schools

| Table | Cols | What it holds |
|---|---|---|
| `school` | 44 | The school itself — identity, address, coordinates, the board it belongs to. |
| `school_board` | 16 | The school boards. |
| `board_category` | 6 | The category taxonomy boards use. |
| `country` / `province` | 4 / 5 | The administrative hierarchy the boards nest into. |
| `program` / `school_program` | 3 / 2 | The programmes a school offers. |
| `school_boundary` | 11 | The catchment polygon, as a PostGIS `geom`. Served only to authenticated callers. |
| `school_eqao` | 8 | The per-school assessment results. |
| `school_score` | 10 | The per-school ratings. |
| `school_version` | 9 | The provenance of each row — when it was seen, from where. |

> The app reads these tables like any other data. **No school dataset and no
> school scraper ships in this repository** — the listing site involved
> disallows the endpoints in its `robots.txt` and forbids redistribution in
> its terms. Fill these tables from a source you are licensed to use; see
> [DATA_SOURCES.md](DATA_SOURCES.md).

### Content

| Table | Cols | What it holds |
|---|---|---|
| `local_content` | 31 | The collected local news, events and stories. Carries the PostGIS `geom` once the content has been placed on the map. |
| `local_content_location` | 8 | The link between a piece of content and the place it describes. |
| `local_content_tag` | 3 | The tags on a piece of content. |
| `stories` | 9 | The longer-form pieces. |
| `news_source` | 19 | The crawler's configured sources. |
| `crawl_snapshot` | 13 | The raw payload of every collected item, so a re-parse never needs a re-crawl. |
| `hazards` | 13 | The environmental and infrastructure hazards, mapped. |

### Fuel

| Table | Cols | What it holds |
|---|---|---|
| `fuel_price_series` | 15 | The aggregated price series — EIA weekly for the US, StatCan monthly for Canada, CRE for Mexico. |
| `fuel_sync_state` | 11 | How far each fuel target has been crawled. |

### Routing

| Table | Cols | What it holds |
|---|---|---|
| `routes` | 10 | The tracked routes. |
| `route_cache` | 8 | The cached route geometry. |

### The Maps service

| Table | Cols | What it holds |
|---|---|---|
| `maps_api_consumer` | 10 | A consumer of `/api/maps/v1`. **Only the SHA-256 hash of the key and a short prefix are stored** — the plaintext is printed once, at mint time, and never again. |
| `maps_api_usage` | 6 | The per-consumer usage, for the quota. |

### Infrastructure

| Table | Cols | What it holds |
|---|---|---|
| `geocode_cache` | 12 | The cached geocoding results. |
| `geocode_provider_usage` | 5 | The per-provider call counters, so the free tiers are spent before the paid one. |
| `alembic_version` | 1 | Which migration the database is at. Managed by Alembic. |

---

## The shape of the spatial data

Three tables carry geometry:

| Table | Geometry | Why |
|---|---|---|
| `places` | `POINT` | The viewport query — "everything inside this rectangle". |
| `local_content` | `POINT` | The same, for collected content. |
| `school_boundary` | `POLYGON` | The catchment, and the point-in-polygon test for "which schools contain this pin". |
| `geo_places` | `MULTIPOLYGON` | The administrative outlines. |

All of them are SRID 4326 (WGS 84 — the same system Google Maps uses), so no
reprojection is needed between the map and the database.

> The stored geometry is **full resolution**. Where the API simplifies an
> outline for transport, it does so on the way out
> (`GEO_BOUNDARY_SIMPLIFY_M`) — the point-in-polygon test must not be fooled
> by a simplified edge.

---

## Development vs production

In development (`APP_ENV=development`) the lifespan hook creates the tables
straight from the models with `Base.metadata.create_all`. That is a
convenience for a fresh database — **it is not the schema mechanism**, and it
hides a missing migration.

In production, the schema is managed **only** by the Alembic migrations.

The backend also **refuses to start** when `APP_ENV=development` is combined
with a non-local `DATABASE_URL`. Development mode enables SQL echo — every
statement *and its bound parameters*, emails and tokens included — and
`create_all`. Neither is safe against a shared database, so the combination is
a hard startup failure rather than a quiet misbehaviour.

---

## The seed

```bash
cd backend
.venv/bin/python -m app.seed
```

A small set of demo places, a neighbourhood, some stories and two demo user
rows. It is idempotent — it refuses to run twice.

The demo users carry **no password**. Authentication is delegated to the OIDC
provider, so a password was never usable; a real user row is provisioned
automatically on the first authenticated request.
