# The crawler

whereq.com has no hand-typed map. Every place, price, outline and headline on
it was **crawled** from an upstream and written into the database by the
crawler — the app's retrieval layer.

```
                     ┌──────────────────────────────────────┐
   whereq.cloud ────▶│                                      │
   OpenStreetMap ───▶│            the crawler               │──▶ places
   RSS / JSON   ────▶│  (one scheduler, one cadence)        │──▶ local_content
                     │                                      │──▶ fuel_price_series
                     └──────────────────────────────────────┘──▶ geo_places
```

---

## The upstreams

| Upstream | What the crawler pulls | Where it lands |
|---|---|---|
| **whereq.cloud** | Fuel stations and their live prices | `places` (`source='whereq_cloud'`, `category='gas'`) |
| **whereq.cloud** | The aggregated price series — EIA (US), StatCan (CA), CRE (MX) | `fuel_price_series` |
| **whereq.cloud** | Administrative geography — provinces, regions, municipalities, cities, towns, wards, neighbourhoods, with their outlines | `geo_places`, `geo_concepts` |
| **OpenStreetMap** | The POI layer — coffee, food, parking, pharmacies, clinics, libraries, plazas | `places` (`source='osm'`) |
| **RSS / JSON feeds** | Local news, events, stories and community topics | `local_content` |

The **whereq.cloud** feed is the one that is metered. Everything else is open
data. See [DATA_SOURCES.md](DATA_SOURCES.md) for the licences and the
attribution each one requires.

**The fuel and geography mirrors are off by default.** This installation
reads those two from whereq.cloud live (`FUEL_READ_MODE=cloud`,
`CLOUD_READ_MODE=cloud`), so a second copy held here would be the copy that
goes stale. The mirrors are the **rollback**: `FUEL_MIRROR_ENABLED=true` and
`GEO_INGEST_ENABLED=true` bring them back. The POI layer and the content
feeds are mirrored by default — they are the local layer the app serves
directly. See
[whereq-cloud-migration.md](whereq-cloud-migration.md) for the switches.

---

## The key never leaves the server

`WHEREQ_CLOUD_API_KEY` is read from the server environment and sent as an
`X-API-Key` header by the official `whereq.cloud` Python SDK. The browser only
ever talks to whereq.com's own `/api/*` endpoints, so the metered key is never
in the bundle and a visitor never spends your quota.

Without a key, the whereq.cloud endpoints answer with a 100-row preview of the
oldest rows. The crawler **refuses** that preview unless you ask for it
explicitly (`--allow-demo`), because a demo page is not a map.

The API allows **30 requests/minute** per key. Every whereq.cloud read shares
one throttle (`app/services/whereq_cloud_client.py`) — two independent ones
would each allow 30/min and would 429 each other.

---

## Running the crawler

The scheduler is the normal way to run it. In the Compose stack it is the
`crawler` container:

```bash
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml logs -f crawler
```

Locally, from `backend/`:

```bash
.venv/bin/python -m app.crawler.scheduler
```

One ingest pass, by hand:

```bash
.venv/bin/python -m app.fuel_ingest        # whereq.cloud fuel stations
.venv/bin/python -m app.fuel_ingest --prices
.venv/bin/python -m app.geo_ingest         # whereq.cloud geography
.venv/bin/python -m app.places_ingest       # OpenStreetMap POIs
.venv/bin/python -m app.crawler.run         # one content crawl
```

---

## Coverage targets

The whereq.cloud ingests do not pull a whole continent in one go. Coverage is
expressed as **targets**, and the scheduler rotates through the targets that
are due — one (or `*_INGEST_TARGETS_PER_TICK`) per tick — so the upstream is
never asked for everything at once.

**Fuel** — a country, a state/province, a city, or a map viewport:

```
CA                      the whole country
CA:Ontario              a province (a full name or an ISO code — ON works)
CA:Ontario:Toronto      a city
bbox:-79.7,43.4,-79.3,43.9    a map viewport (minLon,minLat,maxLon,maxLat)
```

**Geography** — a kind, a country, a source, or a map viewport:

```
kind:ward                       every ward
kind:neighbourhood              every neighbourhood
country:CA                      every kind within Canada
bbox:-80.3,43.6,-79.2,44.2      one viewport
```

The defaults live in `backend/.env.example`:

| Setting | Default | Notes |
|---|---|---|
| `FUEL_INGEST_TARGETS` | `CA,US` | The fuel coverage. |
| `FUEL_INGEST_TARGETS_PER_TICK` | `1` | Targets ingested per tick. |
| `FUEL_INGEST_INTERVAL_HOURS` | `6` | How often a target is re-ingested. |
| `GEO_INGEST_TARGETS` | `bbox:-80.3,43.6,-79.2,44.2` | The geography coverage. |
| `GEO_INGEST_TARGETS_PER_TICK` | `1` | Targets ingested per tick. |
| `GEO_INGEST_INTERVAL_HOURS` | `168` | How often a target is re-ingested. |
| `POI_INGEST_INTERVAL_DAYS` | `7` | How often the OSM POIs are re-ingested. |

Due-ness is tracked per target in `fuel_sync_state` and `geo_sync_state`, so a
target that failed is retried on the next tick instead of waiting out its
interval. (The table names are historical — they are the crawl state.)

---

## The content feeds

Local news, events, stories and topics are crawled from **sources**, each one
a row in the `news_source` table:

| Column | What it is |
|---|---|
| `slug` | the source's identity — the key everything else hangs off |
| `kind` | `rss` or `json` — which parser to use |
| `url` | the feed URL the crawler fetches |
| `enabled` | whether the crawler visits it |
| `crawl_interval_minutes` | how often it is due |
| `default_type` / `default_city` / … | the fallbacks for an item that does not say where it happened |

Adding a generic RSS source needs **no code change** — insert a row:

```sql
INSERT INTO news_source (slug, name, kind, url, homepage_url,
                         default_type, default_city, default_province,
                         default_country, crawl_interval_minutes, config)
VALUES ('example-news', 'Example News', 'rss',
        'https://example.com/feed/', 'https://example.com',
        'news', 'Toronto', 'ON', 'CA', 60, '{"item_limit": 80}');
```

A *bespoke* parser (a feed whose shape no generic reader handles) is a
`BaseSource` subclass registered in `app/crawler/sources/__init__.py` under its
slug.

The crawler is resilient to a dead feed: it records `last_status='error'` on
that source and carries on with the others. Several of the shipped defaults
start disabled because their public feed URL no longer works — enable them
once you have confirmed a working URL.

---

## What a crawl does with an item

The content pipeline, one step at a time:

1. **Fetch** the source and parse it into raw items.
2. **Normalize** them — headline, summary, image, published time.
3. **Place** them — the location is extracted from the item, then geocoded
   through the provider chain (`app/services/geocoding`).
4. **Classify** them — a category (news, event, story, topic) and a type.
5. **Upsert** them into `local_content`, keyed by `(source, external_id)`.

An item that cannot be placed is stored without coordinates and picked up
later by the re-geocode pass:

```bash
.venv/bin/python -m app.crawler.regeocode --dry-run   # see what would change
.venv/bin/python -m app.crawler.regeocode --limit 200  # do it
```

---

## Where the code lives

| Module | What it does |
|---|---|
| `app/crawler/scheduler.py` | the loop — what is due, and when |
| `app/crawler/run.py` | one content crawl, by hand |
| `app/crawler/pipeline.py` | normalize → place → classify → upsert |
| `app/crawler/rss.py`, `json_source.py` | the source parsers |
| `app/crawler/base.py` | the `BaseSource` / `RawItem` contract |
| `app/crawler/sources/__init__.py` | the source registry |
| `app/crawler/seed_sources.py` | the default source set |
| `app/services/whereq_cloud_client.py` | the shared client, throttle and retry policy |
| `app/services/cloud_fuel.py` | the live fuel read — stations and price series |
| `app/services/cloud_geo.py` | the live geography read, and the bulk outlines |
| `app/services/cloud_schools.py` | the live school read |
| `app/services/cloud_local.py` | the local content and places sync |
| `app/services/fuel_stations.py` | the whereq.cloud fuel ingest |
| `app/services/fuel_prices.py` | the whereq.cloud price-series ingest |
| `app/services/geo_places.py` | the whereq.cloud geography ingest |
| `app/services/osm_places.py` | the OpenStreetMap POI ingest |
| `app/fuel_ingest.py` | the fuel ingest command |
| `app/geo_ingest.py` | the geography ingest command |
| `app/places_ingest.py` | the POI ingest command |
