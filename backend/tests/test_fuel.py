"""Unit tests for the whereq.cloud fuel integration (no DB / no network)."""

import asyncio
from types import SimpleNamespace

import pytest

from app.crawler.upstream.fuel_stations import (
    CURRENCY_BY_COUNTRY,
    UNIT_BY_COUNTRY,
    FuelTarget,
    _iter_stations,
    _Throttle,
    call_with_retry,
    configured_targets,
    external_id_for,
    is_due,
    parse_target,
    retry_delay,
    station_to_row,
)


# ── targets ─────────────────────────────────────────────────────────────────
def test_parse_country_target():
    t = parse_target("CA")
    assert t == FuelTarget(country="CA")
    assert t.key == "ca"
    assert t.api_filters() == {"country": "CA"}


def test_parse_state_and_municipality_targets():
    t = parse_target("CA:Ontario:Toronto")
    assert (t.country, t.state, t.municipality) == ("CA", "Ontario", "Toronto")
    assert t.key == "ca:ontario:toronto"
    assert t.api_filters() == {"country": "CA", "state": "Ontario", "municipality": "Toronto"}

    assert parse_target("US:Texas").api_filters() == {"country": "US", "state": "Texas"}


def test_parse_bbox_target():
    t = parse_target("bbox:-79.7,43.4,-79.3,43.9")
    assert t.bbox == "-79.7,43.4,-79.3,43.9"
    assert t.api_filters() == {"bbox": "-79.7,43.4,-79.3,43.9"}
    assert t.key.startswith("bbox:")


def test_parse_rejects_bad_targets():
    assert parse_target("") is None
    assert parse_target("   ") is None
    assert parse_target("ZZ") is None          # not a whereq.cloud fuel country
    assert parse_target("bbox:1,2,3") is None  # needs 4 numbers


def test_configured_targets_dedupes(monkeypatch):
    monkeypatch.setattr("app.crawler.upstream.fuel_stations.settings.FUEL_CRAWL_TARGETS",
                        "CA,US,ca:ontario,CA:Ontario")
    targets = configured_targets()
    assert [t.key for t in targets] == ["ca", "us", "ca:ontario"]


# ── row mapping ─────────────────────────────────────────────────────────────
def _station(**over):
    base = {
        "id": 437547, "source": "cheapgastoronto",
        "ext_id": "pioneer-3279-kingston-rd-toronto-2",
        "country": "CA", "name": "Pioneer", "brand": "Pioneer",
        "state": "Ontario", "state_iso": "ON", "municipality": "Toronto",
        "lat": 43.7315166, "lon": -79.2247578,
        "prices": {"regular": {"price": 1.669, "observed_at": "2026-10-25T19:57:50+00:00"}},
    }
    base.update(over)
    return base


def test_station_to_row_maps_fields():
    row = station_to_row(_station())
    assert row["category"] == "gas"
    assert row["kind"] == "poi"
    assert row["source"] == "whereq_cloud"
    assert row["city"] == "Toronto"
    assert row["country"] == "CA"
    assert row["latitude"] == 43.7315166
    assert row["metadata_json"]["prices"]["regular"]["price"] == 1.669
    assert row["metadata_json"]["observed_at"] == "2026-10-25T19:57:50+00:00"
    assert row["metadata_json"]["data_source"] == "cheapgastoronto"


def test_station_to_row_carries_currency_per_country():
    ca = station_to_row(_station(country="CA"))
    us = station_to_row(_station(country="US", state="Texas", state_iso="TX"))
    mx = station_to_row(_station(country="MX", state="Baja California", state_iso=None))

    assert ca["metadata_json"]["currency"] == "CAD"
    assert ca["metadata_json"]["unit"] == "CAD/L"
    assert us["metadata_json"]["currency"] == "USD"
    assert us["metadata_json"]["unit"] == "USD/L"
    assert mx["metadata_json"]["currency"] == "MXN"
    assert CURRENCY_BY_COUNTRY == {"MX": "MXN", "US": "USD", "CA": "CAD"}
    assert UNIT_BY_COUNTRY["US"] == "USD/L"


def test_station_to_row_skips_unusable_rows():
    assert station_to_row(_station(lat=None)) is None
    assert station_to_row(_station(lon=None)) is None
    assert station_to_row(_station(ext_id=None, id=None)) is None


def test_external_id_is_stable_and_fits_the_column():
    short = external_id_for("cheapgastoronto", "pioneer-3279-kingston-rd-toronto-2")
    assert short == "cheapgastoronto/pioneer-3279-kingston-rd-toronto-2"
    assert len(short) <= 64

    # A long id is hashed rather than truncated — truncating would merge two
    # different stations onto one key.
    long_id = "a" * 200
    hashed = external_id_for("gasbuddy", long_id)
    assert len(hashed) <= 64
    assert hashed == external_id_for("gasbuddy", long_id)
    assert hashed != external_id_for("gasbuddy", "b" * 200)


# ── API error handling ──────────────────────────────────────────────────────
def test_retry_delay_uses_the_api_hint():
    exc = SimpleNamespace(message='{"error": {"detail": "Rate limit exceeded (30/min). Retry in 6s."}}')
    assert retry_delay(exc, 0) == pytest.approx(6.5)


def test_retry_delay_falls_back_to_exponential():
    exc = SimpleNamespace(message="boom")
    assert retry_delay(exc, 0) == 1.0
    assert retry_delay(exc, 3) == 8.0
    assert retry_delay(exc, 10) == 60.0


def test_call_with_retry_retries_429_then_succeeds(monkeypatch):
    import whereq_cloud

    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise whereq_cloud.WhereqError(429, "Retry in 0s", "u")
        return {"ok": True}

    monkeypatch.setattr("app.crawler.upstream.whereq_cloud.time.sleep", lambda _s: None)
    assert call_with_retry(flaky, attempts=5) == {"ok": True}
    assert len(calls) == 3


def test_call_with_retry_raises_client_errors_immediately(monkeypatch):
    import whereq_cloud

    def bad():
        raise whereq_cloud.WhereqError(422, "Invalid request parameters", "u")

    monkeypatch.setattr("app.crawler.upstream.whereq_cloud.time.sleep", lambda _s: None)
    with pytest.raises(whereq_cloud.WhereqError):
        call_with_retry(bad, attempts=5)


# ── paging ──────────────────────────────────────────────────────────────────
class _FakeClient:
    """Stands in for the whereq.cloud SDK client."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fuel_stations(self, **params):
        self.calls.append(params)
        return self.pages[min(len(self.calls) - 1, len(self.pages) - 1)]


def test_iter_stations_pages_until_total():
    pages = [
        {"stations": [{"id": i} for i in range(3)], "total": 5, "demo": False},
        {"stations": [{"id": i} for i in range(3, 5)], "total": 5, "demo": False},
    ]
    client = _FakeClient(pages)
    rows = list(_iter_stations(client, target=parse_target("CA"),
                               throttle=_Throttle(0), max_stations=100))
    assert len(rows) == 5
    assert client.calls[0]["limit"] == 500
    assert client.calls[1]["offset"] == 3


def test_iter_stations_stops_after_the_first_demo_page():
    demo = {"stations": [{"id": 1}], "total": None, "demo": True}
    client = _FakeClient([demo, demo])
    rows = list(_iter_stations(client, target=parse_target("CA"),
                               throttle=_Throttle(0), max_stations=100))
    # The preview ignores paging — fetching page 2 would return the same rows —
    # and its rows are dropped unless the caller asked for the demo data.
    assert rows == []
    assert len(client.calls) == 1


def test_iter_stations_yields_the_demo_rows_when_allowed():
    demo = {"stations": [{"id": 1}], "total": None, "demo": True}
    client = _FakeClient([demo, demo])
    rows = list(_iter_stations(client, target=parse_target("CA"),
                               throttle=_Throttle(0), max_stations=100,
                               allow_demo=True))
    assert len(rows) == 1
    assert len(client.calls) == 1


def test_iter_stations_respects_the_station_cap():
    page = {"stations": [{"id": i} for i in range(10)], "total": 1000, "demo": False}
    client = _FakeClient([page])
    rows = list(_iter_stations(client, target=parse_target("CA"),
                               throttle=_Throttle(0), max_stations=10))
    assert len(rows) == 10


# ── due-ness ────────────────────────────────────────────────────────────────
def test_is_due_for_never_synced_target():
    assert is_due(None, interval_hours=6) is True


def test_is_due_for_fresh_and_stale_targets():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    fresh = SimpleNamespace(last_synced_at=now - timedelta(hours=1), last_error=None)
    stale = SimpleNamespace(last_synced_at=now - timedelta(hours=7), last_error=None)
    assert is_due(fresh, interval_hours=6) is False
    assert is_due(stale, interval_hours=6) is True


def test_failed_target_is_retried_without_waiting():
    from datetime import datetime, timezone

    failed = SimpleNamespace(last_synced_at=datetime.now(timezone.utc), last_error="boom")
    assert is_due(failed, interval_hours=6) is True


# ── aggregated price series ─────────────────────────────────────────────────
def test_normalize_per_litre_converts_source_units():
    from app.crawler.upstream.fuel_prices import normalize_per_litre

    # StatCan quotes cents per litre.
    assert normalize_per_litre("Cents per litre", 170.3) == (1.703, "CAD")
    # EIA quotes dollars per US gallon.
    value, currency = normalize_per_litre("$/GAL", 3.841)
    assert currency == "USD"
    assert round(value, 4) == 1.0147
    # CRE quotes pesos per litre.
    assert normalize_per_litre("MXN/L", 22.5) == (22.5, "MXN")
    # An unknown unit is passed through rather than guessed at.
    assert normalize_per_litre("furlongs per fortnight", 5.0) == (5.0, None)
    assert normalize_per_litre("Cents per litre", None) == (None, None)


def test_product_key_normalizes_item_names():
    from app.crawler.upstream.fuel_prices import product_key

    assert product_key("Regular unleaded gasoline at self service filling stations") == "regular"
    assert product_key("Regular Gasoline") == "regular"
    assert product_key("No 2 Diesel") == "diesel"
    assert product_key("Household heating fuel") == "heating"
    assert product_key("Something else entirely") is None


def test_preferred_series_picks_self_service_and_the_most_recent():
    from app.crawler.upstream.fuel_prices import preferred_series

    series = [
        {"product": "regular", "item": "Regular unleaded gasoline at full service filling stations",
         "latest_period": "2013-01-01", "points": 25, "geo": "Toronto, Ontario"},
        {"product": "regular", "item": "Regular unleaded gasoline at self service filling stations",
         "latest_period": "2026-08-01", "points": 188, "geo": "Toronto, Ontario"},
        {"product": "diesel", "item": "Diesel fuel at self service filling stations",
         "latest_period": "2026-08-01", "points": 188, "geo": "Toronto, Ontario"},
    ]
    picked = preferred_series(series)
    assert [p["product"] for p in picked] == ["regular", "diesel"]
    assert picked[0]["latest_period"] == "2026-08-01"
    assert "self service" in picked[0]["item"]


def test_candidate_geos_prefers_the_exact_region():
    from app.crawler.upstream.fuel_prices import _candidate_geos

    ca = _candidate_geos("CA", "Ontario", "Toronto", ["Toronto, Ontario", "Canada", "Winnipeg, Manitoba"])
    assert ca[0] == "Toronto, Ontario"
    assert ca[-1] == "Canada"

    us = _candidate_geos("US", "Texas", None, ["U.S.", "TEXAS"])
    assert us == ["TEXAS", "U.S."]


# ── resilience ──────────────────────────────────────────────────────────────
def test_price_series_due_when_the_table_is_missing():
    from sqlalchemy.exc import ProgrammingError

    from app.crawler.upstream.fuel_prices import price_series_due

    class _NoTable:
        async def execute(self, *_a, **_k):
            raise ProgrammingError('SELECT ...', {}, Exception('relation does not exist'))

    # A missing table must be treated as "due" so the tick retries instead of
    # waiting out the whole interval (the crawler can start before the
    # migration has run).
    assert asyncio.run(price_series_due(_NoTable(), interval_hours=24)) is True


def test_price_series_due_uses_the_newest_row():
    from app.crawler.upstream.fuel_prices import price_series_due

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _DB:
        def __init__(self, value):
            self._value = value

        async def execute(self, *_a, **_k):
            return _Result(self._value)

    from datetime import datetime, timedelta, timezone

    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = datetime.now(timezone.utc) - timedelta(hours=30)
    assert asyncio.run(price_series_due(_DB(fresh), interval_hours=24)) is False
    assert asyncio.run(price_series_due(_DB(stale), interval_hours=24)) is True
    assert asyncio.run(price_series_due(_DB(None), interval_hours=24)) is True


# ── finding stations ────────────────────────────────────────────────────────
def test_find_stations_is_exposed_with_the_expected_filters():
    import inspect

    from app.crawler.upstream.fuel_stations import find_stations

    params = inspect.signature(find_stations).parameters
    for name in ("q", "lat", "lng", "radius_km", "bbox", "product", "sort", "limit"):
        assert name in params, name


def test_price_column_reads_the_product_price():
    from sqlalchemy.dialects import postgresql

    from app.crawler.upstream.fuel_stations import _price_column

    compiled = str(_price_column("regular").compile(
        dialect=postgresql.dialect()))
    assert "metadata_json" in compiled
    assert "regular" in compiled or "param" in compiled


def test_radius_condition_uses_metres_not_degrees():
    """ST_DWithin on a 4326 geometry measures in degrees — the radius has to
    be applied on the geography or it matches the whole planet."""
    from sqlalchemy.dialects import postgresql

    from app.crawler.upstream.fuel_stations import _radius_condition

    sql = str(_radius_condition(-79.46, 43.84, 25).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "ST_DWithin" in sql
    assert "geography" in sql.lower(), sql
    assert "25000" in sql  # 25 km in metres, not degrees
