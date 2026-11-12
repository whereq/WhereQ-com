"""Unit tests for local-content crawler core logic (no DB / network).

Run from backend/:  pytest tests/test_local_content.py
"""

from datetime import datetime, timedelta, timezone

from app.services.classify import classify
from app.services.datetime_extract import extract_event_datetime
from app.services.location_extract import best_query, extract_locations
from app.crawler.pipeline import _content_hash, _dedup_key, compute_expiry


# ── classification ──────────────────────────────────────────────────────────
def test_classify_accident():
    c = classify("Multi-Vehicle Collision on Highway 401",
                 "Several vehicles were involved in a collision causing major delays.")
    assert c.category == "accident"
    assert c.content_type == "news"
    assert c.confidence > 0.4
    assert "collision" in c.tags


def test_classify_event_type():
    c = classify("Summer Music Festival returns to Yonge-Dundas Square",
                 "A free outdoor concert and festival this weekend.")
    assert c.category in ("festival", "event")
    assert c.content_type == "event"


def test_classify_business_story():
    c = classify("New bakery opens on Queen Street West",
                 "A popular bakery opens its second Toronto store.")
    assert c.category == "business"
    assert c.content_type == "story"


def test_classify_unknown_is_other():
    c = classify("A reflection on nothing in particular", "")
    assert c.category == "other"
    assert c.confidence <= 0.3


# ── location extraction ─────────────────────────────────────────────────────
def test_extract_highway():
    cands = extract_locations("Crash on Highway 401",
                              "A crash westbound on Highway 401 near Keele Street.")
    assert cands[0].text == "Highway 401"
    plan = best_query(cands, city="Toronto", province="ON")
    assert plan.query == "Highway 401, Toronto, ON, Canada"
    assert plan.city == "Toronto"


def test_extract_address_is_most_specific():
    cands = extract_locations("New bakery opens at 123 Queen Street West", "")
    assert cands[0].kind == "address"
    assert cands[0].text.startswith("123 Queen Street")


def test_extract_intersection_not_from_near():
    # "Stabbing near Yonge and Dundas" must not yield "Stabbing & Yonge"
    cands = extract_locations("Stabbing near Yonge and Dundas",
                              "Police investigate near Yonge and Dundas Square.")
    texts = [c.text for c in cands]
    assert not any(t.startswith("Stabbing") for t in texts)
    assert any("Yonge & Dundas" in t for t in texts)


def test_extract_no_location():
    assert extract_locations("An opinion piece", "Just thoughts.") == []
    assert best_query([], city="Toronto") is None


# ── dedup + hashing ─────────────────────────────────────────────────────────
def test_content_hash_stable_and_sensitive():
    a = _content_hash("Title", "Summary", "http://x")
    assert a == _content_hash("Title", "Summary", "http://x")
    assert a != _content_hash("Title changed", "Summary", "http://x")


def test_dedup_key_normalizes_and_separates_by_day():
    d1 = datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 6, 4, 9, 0, tzinfo=timezone.utc)
    assert _dedup_key("Multi-Vehicle Collision!", d1) == _dedup_key("multi vehicle   collision", d1)
    assert _dedup_key("Same title", d1) != _dedup_key("Same title", d2)


# ── retention windows ───────────────────────────────────────────────────────
def test_compute_expiry_incident_is_short():
    pub = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    exp = compute_expiry("news", "accident", pub, pub, None)
    assert exp == pub + timedelta(days=2)


def test_compute_expiry_story_is_long():
    pub = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    exp = compute_expiry("story", "business", pub, None, None)
    assert exp == pub + timedelta(days=90)


def test_compute_expiry_event_after_end():
    pub = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    exp = compute_expiry("event", "festival", pub, pub, end)
    assert exp == end + timedelta(days=2)


# ── event datetime extraction ───────────────────────────────────────────────
def test_event_datetime_date_and_time():
    ev = extract_event_datetime("Summer Fest on June 14, 2026 at 7:00 PM", base_year=2026)
    assert ev is not None and ev.has_time
    assert (ev.start.year, ev.start.month, ev.start.day, ev.start.hour) == (2026, 6, 14, 19)
    assert ev.end is None


def test_event_datetime_same_day_range():
    ev = extract_event_datetime("Art show Sat, June 14 · 7:00 PM - 10:00 PM", base_year=2026)
    assert ev is not None and ev.end is not None
    assert ev.start.hour == 19 and ev.end.hour == 22


def test_event_datetime_multiday_range():
    ev = extract_event_datetime("Street festival June 14-16, 2026")
    assert ev is not None and ev.end is not None
    assert (ev.start.day, ev.end.day) == (14, 16)


def test_event_datetime_iso():
    ev = extract_event_datetime("Concert on 2026-06-14 19:00")
    assert ev is not None and ev.has_time
    assert (ev.start.month, ev.start.day, ev.start.hour) == (6, 14, 19)


def test_event_datetime_none():
    assert extract_event_datetime("A regular news headline with no date") is None


# ── placing an item on the map ──────────────────────────────────────────────
def _geo(lat, lng, provider="geocode_maps_co", confidence=0.9):
    from app.services.geocoding import GeoResult

    return GeoResult(lat, lng, "somewhere", confidence, provider)


def test_an_item_we_cannot_place_gets_no_position():
    """It used to be pinned at the city centre — a pin that claims a specific
    place the item is not at."""
    from app.crawler.pipeline import _resolve_position

    lat, lng, status, source, _ = _resolve_position(
        None, (43.6532, -79.3832), 20.0, 0.8, 0.7)
    assert lat is None and lng is None
    assert status == "failed"
    assert source is None


def test_a_resolved_item_keeps_its_position_and_its_real_provider():
    from app.crawler.pipeline import _resolve_position

    lat, lng, status, source, confidence = _resolve_position(
        _geo(43.65, -79.38, provider="nominatim"), (43.6532, -79.3832), 20.0, 0.8, 0.7)
    assert (lat, lng) == (43.65, -79.38)
    assert status == "ok"
    # The provider is recorded, not a hard-coded "google".
    assert source == "nominatim"
    assert 0 < confidence <= 0.99


def test_a_cross_city_geocode_is_rejected_not_snapped():
    """A same-named street in another municipality is not a location for this
    item — it must not be pinned at the city centre either."""
    from app.crawler.pipeline import _resolve_position

    # Quebec City is ~470 km from Toronto's centre.
    lat, lng, status, source, _ = _resolve_position(
        _geo(46.8139, -71.2080), (43.6532, -79.3832), 20.0, 0.8, 0.7)
    assert lat is None and lng is None
    assert status == "rejected"
    assert source is None


def test_a_far_but_correct_result_is_kept_when_only_the_region_is_known():
    """With no city detected the guard is lenient, so a legitimately distant
    result is not thrown away."""
    from app.crawler.pipeline import _resolve_position

    lat, lng, status, _, _ = _resolve_position(
        _geo(43.65, -79.38), None, 60.0, 0.8, 0.7)
    assert (lat, lng) == (43.65, -79.38)
    assert status == "ok"


def test_the_crawler_no_longer_writes_a_fallback_city_status():
    """The city-centre status is gone from the vocabulary entirely."""
    from pathlib import Path

    src = Path("app/crawler/pipeline.py").read_text()
    assert "fallback_city" not in src
    # And the city centre is never assigned as a position.
    assert "lat, lng = center" not in src


def test_the_migration_unplaces_only_the_fallback_rows():
    from pathlib import Path

    src = Path("alembic/versions/014_unplace_fallback_content.py").read_text()
    assert "geocode_status = 'fallback_city'" in src
    # The coordinates and the geometry are all cleared.
    assert "latitude = NULL" in src and "longitude = NULL" in src and "geom = NULL" in src


def test_the_legacy_geocode_status_is_reset():
    """The rows migration 014 unplaced still said 'fallback_city' — a value
    that is not in the vocabulary and that described a pin they no longer
    have.  Migration 016 resets it to 'none'."""
    from pathlib import Path

    src = Path("alembic/versions/016_reset_legacy_geocode_status.py").read_text()
    assert "geocode_status = 'none'" in src
    assert "WHERE geocode_status = 'fallback_city'" in src
    # It must not touch the coordinates.
    assert "latitude" not in src and "longitude" not in src and "geom" not in src
