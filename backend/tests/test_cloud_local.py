"""The local layer — read from whereq.cloud instead of collected here.

WHAT IS BEING TESTED
---------------------
whereq.cloud collects the news feeds and the OSM points of interest now.
whereq.com reads them over the SDK and upserts them into the local mirror,
so the map and the search keep answering while the *collection* happens
once, in one place. Three things have to hold for that to be safe:

1. **The translation is right.** The upstream's content and place payloads
   are re-shaped into the rows this app's tables already hold. A field that
   is renamed or dropped in the re-shaping is a field the app stops showing.

2. **The keys agree.** The upsert keys on ``(source_id, external_id)`` for
   content and ``(source, external_id)`` for places — the same keys the
   collectors that are being retired used. A row that cannot be keyed is a
   row that would land **twice**, so it is skipped and counted, never
   guessed.

3. **The old collectors are actually off.** They are still in the image,
   because the rollback is the rollback. But they only run when
   ``LEGACY_COLLECTORS_ENABLED`` says so, and two schedulers writing the
   same tables is the failure this flag exists to prevent.

THE POINT IS NOT PROXYING
-------------------------
The rows are **copied into** the local tables, not forwarded. The upstream's
fuel prices carry a licence condition (they are stripped for anonymous
callers) and the shape this app returns is its own; a copy is what lets
the app keep answering from its own database while the collection moves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.cloud_local import _content_row, _place_row


# ── the upstream's payloads ────────────────────────────────────────────
CONTENT_ROW = {
    "id": 40,
    "source_slug": "citynews-toronto",
    "source_name": "CityNews Toronto",
    "source_url": "https://toronto.citynews.ca/2026/11/21/some-story/",
    "external_id": "https://toronto.citynews.ca/?p=4967131",
    "type": "news",
    "category": "other",
    "title": "Toronto zoo reviews enclosures",
    "summary": "The zoo reviewed several habitats.",
    "event_time": "2026-11-21T19:06:46+00:00",
    "event_end_time": None,
    "publish_time": "2026-11-21T19:06:46+00:00",
    "latitude": 43.65,
    "longitude": -79.38,
    "address": None,
    "city": "Toronto",
    "province": "ON",
    "country": "CA",
    "geocode_status": "none",
    "geocode_source": None,
    "confidence_score": 0.2,
    "status": "active",
    "image_url": None,
    "expires_at": "2026-11-28T19:06:46+00:00",
    "tags": [],
}

PLACE_ROW = {
    "id": 8735,
    "name": "Shoppers Drug Mart",
    "description": None,
    "latitude": 43.6770286,
    "longitude": -79.3553728,
    "address": "1234 Yonge St",
    "city": "Toronto",
    "country": "Canada",
    "category": "pharmacy",
    "kind": "pharmacy",
    "sub": None,
    "metadata": {"brand": "Shoppers", "opening_hours": "Mo-Fr 10:00-18:00"},
    "source": "osm",
    "external_id": "node/48553517",
    "source_url": "https://www.openstreetmap.org/node/48553517",
    "license": "ODbL 1.0 (OpenStreetMap contributors)",
}

SOURCE_IDS = {"citynews-toronto": 2, "global-news-toronto": 5}


# ── the content translation ────────────────────────────────────────────
class TestContentRow:
    def test_a_row_becomes_a_local_row(self):
        row = _content_row(CONTENT_ROW, SOURCE_IDS)
        assert row is not None
        assert row["source_id"] == 2
        assert row["external_id"] == "https://toronto.citynews.ca/?p=4967131"
        assert row["title"] == "Toronto zoo reviews enclosures"
        assert row["city"] == "Toronto"
        assert row["province"] == "ON"
        assert row["country"] == "CA"

    def test_the_point_is_built_in_the_row(self):
        """The PostGIS point is built in the same statement as the row, the
        way the POI ingest does it — not left to a second pass."""
        row = _content_row(CONTENT_ROW, SOURCE_IDS)
        assert row["geom"] == "SRID=4326;POINT(-79.38 43.65)"

    def test_a_row_without_a_point_has_no_point(self):
        """A half-placed row — a latitude without a longitude — is not a
        point, and must not become one."""
        payload = dict(CONTENT_ROW, latitude=None, longitude=None)
        row = _content_row(payload, SOURCE_IDS)
        assert row["geom"] is None
        assert row["latitude"] is None

    def test_a_row_without_an_external_id_is_skipped(self):
        """Without the key there is nothing to upsert on, so the row would
        land twice. It is skipped, never guessed."""
        payload = dict(CONTENT_ROW, external_id=None)
        assert _content_row(payload, SOURCE_IDS) is None

    def test_a_row_from_an_unknown_source_is_skipped(self):
        """The local table keys the row on a source id, and the upstream's
        slug is how it is found. An unknown slug has no id to point at."""
        payload = dict(CONTENT_ROW, source_slug="a-feed-we-do-not-have")
        assert _content_row(payload, SOURCE_IDS) is None

    def test_the_timestamps_are_parsed(self):
        row = _content_row(CONTENT_ROW, SOURCE_IDS)
        assert row["publish_time"].year == 2026
        assert row["publish_time"].tzinfo is not None
        assert row["expires_at"] is not None

    def test_a_null_timestamp_stays_null(self):
        payload = dict(CONTENT_ROW, publish_time=None, event_time=None)
        row = _content_row(payload, SOURCE_IDS)
        assert row["publish_time"] is None
        assert row["event_time"] is None


# ── the places translation ─────────────────────────────────────────────
class TestPlaceRow:
    def test_a_row_becomes_a_local_row(self):
        row = _place_row(PLACE_ROW)
        assert row is not None
        assert row["name"] == "Shoppers Drug Mart"
        assert row["category"] == "pharmacy"
        assert row["kind"] == "pharmacy"
        assert row["external_id"] == "node/48553517"
        assert row["source"] == "osm"
        assert row["metadata_json"] == {"brand": "Shoppers",
                                        "opening_hours": "Mo-Fr 10:00-18:00"}

    def test_the_point_is_built_in_the_row(self):
        row = _place_row(PLACE_ROW)
        assert row["geom"] == "SRID=4326;POINT(-79.3553728 43.6770286)"

    def test_the_source_is_the_upstream_one(self):
        """The source is part of the upsert key, so it must be the value the
        rows already carry — 'osm', not a new one."""
        row = _place_row(PLACE_ROW)
        assert row["source"] == "osm"
        assert _place_row(dict(PLACE_ROW, source=None))["source"] == "osm"

    def test_a_row_without_a_point_is_skipped(self):
        assert _place_row(dict(PLACE_ROW, latitude=None)) is None
        assert _place_row(dict(PLACE_ROW, longitude=None)) is None

    def test_a_row_without_an_external_id_is_skipped(self):
        assert _place_row(dict(PLACE_ROW, external_id=None)) is None


# ── the collectors that are being retired ─────────────────────────────
class TestTheLegacyCollectorsAreOff:
    def test_the_legacy_flag_defaults_to_off(self):
        """whereq.cloud collects now. The old collectors come back only when
        the rollback asks for them by name."""
        from app.core.config import Settings

        assert Settings().LEGACY_COLLECTORS_ENABLED is False

    def test_the_legacy_ticks_do_nothing_without_the_flag(self):
        import asyncio

        from app.crawler import scheduler

        async def run():
            # Both ticks return before touching the database, so this needs
            # no database and no network.
            await scheduler._crawl_tick()
            await scheduler._poi_tick()

        asyncio.run(run())

    def test_the_sync_ticks_are_wired(self):
        """The scheduler runs the two upstream reads. If they were missing,
        the container would start and quietly do nothing."""
        from app.crawler import scheduler

        assert callable(scheduler._local_content_sync_tick)
        assert callable(scheduler._local_places_sync_tick)


# ── the wiring ─────────────────────────────────────────────────────────
class TestTheWiring:
    def _compose(self) -> str:
        root = Path(__file__).resolve().parents[2]
        return (root / "docker" / "docker-compose.yml").read_text()

    def test_the_service_is_the_consumer(self):
        """The container stopped collecting and started consuming.

        The service keeps its ``crawler`` name here, because this repository's
        own setup guide runs ``docker compose logs -f crawler`` — but what it
        does is consume: whereq.cloud collects the news feed and the POI
        catalogue, and this container reads them back over the SDK.
        """
        compose = self._compose()
        assert "\n  crawler:" in compose
        assert "python\", \"-m\", \"app.crawler.scheduler" in compose

    def test_the_legacy_container_name_is_gone(self):
        """A container that still carries the old name would keep running
        beside the new one — two schedulers, one set of tables."""
        assert "whereq-crawler" not in self._compose()

    def test_only_one_scheduler_runs(self):
        """One scheduler, or two write to the same tables."""
        compose = self._compose()
        assert compose.count("app.crawler.scheduler") == 1

    def test_the_sync_settings_are_wired(self):
        compose = self._compose()
        for setting in ("LOCAL_CONTENT_SYNC_ENABLED", "LOCAL_PLACES_SYNC_ENABLED",
                        "LOCAL_CONTENT_SYNC_PAGES", "LOCAL_PLACES_SYNC_INTERVAL_HOURS",
                        "LEGACY_COLLECTORS_ENABLED"):
            assert setting in compose, f"{setting} is not wired into compose"

    def test_the_env_examples_document_the_flags(self):
        root = Path(__file__).resolve().parents[2]
        for example in (root / "backend" / ".env.example",
                        root / "docker" / ".env.example"):
            if not example.exists():
                continue
            text = example.read_text()
            assert "LEGACY_COLLECTORS_ENABLED" in text, \
                f"{example} does not document the rollback lever"
