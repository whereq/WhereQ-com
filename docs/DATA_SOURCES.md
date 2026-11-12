# Data sources

Every dataset this app can show, where it comes from, and what you have to
do to use it. Nothing is bundled: there is no seeded database, no checked-in
data dump, and no scraper whose output ships with the repository.

The short version: **the code is here, the data is yours.** You point the app
at a feed you are licensed to use, or you run the crawler against your own
sources.

Every feed below is reached by the **crawler** — the app's retrieval layer.
[CRAWLER.md](CRAWLER.md) describes how that layer works; this page is about
the licences and the obligations each feed comes with.

---

## The table

| Feed | Used for | Licence | Key needed |
|---|---|---|---|
| **whereq.cloud Data API** | Fuel stations, live fuel prices, administrative geography (outlines) | Metered API — public preview without a key, full dataset with one | `WHEREQ_CLOUD_API_KEY` |
| **Google Maps Platform** | The map itself, geocoding, routing, static maps | Google Maps Platform Terms | `GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_SERVER_KEY`, `VITE_GOOGLE_MAPS_MAP_ID` |
| **OpenStreetMap** | POI crawl — cafes, food, pharmacies and the other quick categories | ODbL 1.0 | No key; a contact address for the User-Agent |
| **Your own OIDC realm** | Sign-in, roles, the staff surface | Yours | `KEYCLOAK_URL` |
| **Your own RSS / JSON sources** | The local-content crawl | Whatever each source's terms are | Configured via `news_source` rows |

---

## whereq.cloud

The Data API is the primary structured feed. It is a separate service with its
own key; the Python client is the public
[`whereq.cloud`](https://pypi.org/project/whereq.cloud/) package (MIT).

| Endpoint family | Lands in | Notes |
|---|---|---|
| Fuel stations | `places` (category `gas`) | North America. Prices arrive in local currency per litre. |
| Fuel price series | `fuel_price_series` | Aggregated averages — EIA weekly for the US, StatCan monthly for Canada, CRE for Mexico. |
| Administrative geography | `geo_places` | Provinces, regions, municipalities, cities, towns, wards, neighbourhoods — with real outlines. |

Two vocabularies (OpenStreetMap and geoBoundaries) are kept side by side in the
geography feed; they are deliberately **not** merged. Both are open data
(ODbL 1.0 and CC-BY 4.0), so the attribution travels with each row: the
`license` and `source_url` columns carry it, and the API serves it.

**Without a key**, the fuel endpoints fall back to the public preview feed —
the oldest 100 rows, which is not geographically interesting. Everything else
works normally.

### Running the crawl

```bash
cd backend

# Fuel stations — every configured target
.venv/bin/python -m app.crawler.cli.fuel

# One target at a time
.venv/bin/python -m app.crawler.cli.fuel --target "CA:Ontario:Toronto"
.venv/bin/python -m app.crawler.cli.fuel --bbox -79.64,43.58,-79.12,43.86

# The aggregated price series
.venv/bin/python -m app.crawler.cli.fuel --prices

# The public preview feed, explicitly
.venv/bin/python -m app.crawler.cli.fuel --allow-demo

# Administrative geography
.venv/bin/python -m app.crawler.cli.geo
.venv/bin/python -m app.crawler.cli.geo --target "kind:ward"
.venv/bin/python -m app.crawler.cli.geo --boundaries   # also fetch the outlines
```

The crawl is idempotent — it upserts by `(source, external_id)`, so running it
twice is safe.

The targets are configured in `backend/.env` (see `FUEL_CRAWL_TARGETS` and
`GEO_CRAWL_TARGETS`). The crawler visits them round-robin, one target per
tick, because the API allows 30 requests per minute per key and being faster
than the limit only earns a 429.

---

## Google Maps Platform

The map is Google Maps. Three values, all yours:

| Value | What it is | Where it goes |
|---|---|---|
| `VITE_GOOGLE_MAPS_API_KEY` | The **browser** key. Referrer-locked. | Baked into the bundle. |
| `GOOGLE_MAPS_SERVER_KEY` | The **server** key, for web-service calls (Geocoding, Places New, Routes, Static). It must have **no** HTTP-referrer restriction, or Google returns `API_KEY_HTTP_REFERRER_BLOCKED`. Restrict it by IP and/or API allowlist instead. | Backend only. |
| `VITE_GOOGLE_MAPS_MAP_ID` | The Map ID that carries your custom map styling. | Baked into the bundle. |

The backend prefers the server key and falls back to the browser key
(`settings.maps_google_key`).

**Attribution is required.** The API returns
`"Map data ©<year> Google"` with every user-facing result
(`MAPS_ATTRIBUTION` in `backend/app/core/config.py`); keep that string
ToS-shaped if you override it.

---

## OpenStreetMap

The POI crawl reads OSM through Overpass for the "quick categories" — food,
coffee, pharmacy, and the rest.

- **Licence:** ODbL 1.0. Attribution is required: *"© OpenStreetMap
  contributors"*. The footer carries it.
- **No API key** — but the OSM usage policy does require a real contact
  address in the User-Agent. Set `NOMINATIM_EMAIL` (and the equivalent for the
  POI crawl) to an address that reaches you, not a placeholder.

```bash
cd backend
.venv/bin/python -m app.crawler.cli.places
.venv/bin/python -m app.crawler.cli.places --only food,coffee,pharmacy
.venv/bin/python -m app.crawler.cli.places --bbox -79.64,43.58,-79.12,43.86
```

---

## The local-content crawler

The crawler collects local news, events and stories from RSS and JSON sources
you configure, then places each item on the map. The sources are yours: seed
the defaults, or replace them.

```bash
cd backend
.venv/bin/python -m app.crawler.run --seed       # bootstrap the default sources
.venv/bin/python -m app.crawler.run --list       # show what is configured
.venv/bin/python -m app.crawler.run --all        # crawl everything now
.venv/bin/python -m app.crawler.run --source citynews-toronto --limit 20
.venv/bin/python -m app.crawler.run --retention  # expire stale rows
```

A source is a URL and a parser. **Check the terms of every site you add** —
the crawler is a generic RSS/JSON reader, but what you point it at is your
responsibility.

---

## School data

**School data is not bundled, and this repository contains no school scraper.**

The school tables, their models and their API are all here — the app reads
them from the database like any other data. What is not here is the pipeline
that would fill them from a third-party listing site, because those sites'
terms forbid it and their robots.txt disallows the endpoints involved. Adding
one would make this repository a redistribution and scraping tool for data
that is not licensed for either.

If you want school data in your deployment, use a source you are licensed to
use: your own imports, a school board's published open data, or a feed whose
terms permit redistribution. Load it into the same tables the app already
reads — `schools`, `school_facts`, `school_boundary` — and the map, the
catchments and the school pages all work unchanged.

The `boundary_geojson` for a school is served only to authenticated callers,
and the geometry is stored in PostGIS with SRID 4326.

---

## Attribution checklist

If you run this app for other people, keep these visible:

- [ ] "Map data © Google" — on every map surface.
- [ ] "© OpenStreetMap contributors" — wherever OSM POIs appear (the footer
      carries it by default).
- [ ] The per-row `license` and `source_url` from the geography feed — the API
      serves them; surface them if you re-display the data.
- [ ] Font Awesome icons, if you keep using `react-icons` — **CC BY 4.0**
      attribution is required. `lucide-react` (ISC) is already in the
      dependency tree and carries no such obligation.
- [ ] Whatever each RSS/JSON source's terms require, if you display its
      content.
