"""The class-B cut — the fuel feeds read from whereq.cloud instead of mirrored.

WHAT IS BEING TESTED
---------------------
whereq.com used to keep a copy of whereq.cloud's fuel data: the stations in
``places`` (``source='whereq_cloud'``, ``category='gas'``) and the aggregated
series in ``fuel_price_series``. The cut reads the original instead, so
whereq.cloud is the only place the data lives.

Four things have to hold for that to be safe:

1. **The demo preview is refused.** whereq.cloud's unentitled preview carries
   prices, so serving it would serve a frozen slice as though it were the live
   feed. A preview is an **error**, not a degraded answer.

2. **The payload is re-shaped, not proxied.** The upstream's station row is
   not this app's station row: the currency and the unit have to be looked up
   from the country, and the series have to be normalised to local currency
   per litre — the unit the station prices use.

3. **The prices stay behind the session.** The licence is enforced on the
   whereq.com side: the fuel endpoints require a session and the place
   payload strips ``prices``/``observed_at`` for anonymous callers. A live
   read must not quietly drop that rule.

4. **The mirror is actually off.** The two ticks stay in the image — the
   rollback is the rollback — but they only run when ``FUEL_MIRROR_ENABLED``
   says so. Two writers for the same tables is the failure the flag exists
   to prevent.

THE THROTTLE
-------------
The limiter follows the key's **tier**, not a constant. The whereq.com
service key is on the ``unlimited`` tier (1 200 requests/minute); a limiter
built on the free tier's 30 would cap the app at 27 reads a minute on a
credential that allows forty times that.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.cloud_fuel import (
    CloudFuelError,
    _assert_live,
    series_to_read,
    station_external_id,
    station_to_read,
)


# ── the upstream's payloads ─────────────────────────────────────────────────
def _station(**over):
    base = {
        "id": 437547,
        "source": "cheapgastoronto",
        "ext_id": "pioneer-3279-kingston-rd-toronto-2",
        "country": "CA",
        "name": "Pioneer — 3279 Kingston Rd",
        "brand": "Pioneer",
        "state": "Ontario",
        "state_iso": "ON",
        "municipality": "Toronto",
        "lat": 43.7315166,
        "lon": -79.2247578,
        "prices": {
            "regular": {"price": 1.669, "observed_at": "2026-10-25T19:57:50+00:00"},
            "diesel": {"price": 1.799, "observed_at": "2026-10-25T19:57:50+00:00"},
        },
    }
    base.update(over)
    return base


def _series(**over):
    base = {
        "id": 22281,
        "domain": "fuel",
        "source": "statcan",
        "region": "ca",
        "geo": "Toronto, Ontario",
        "item": "Regular unleaded gasoline at self service filling stations",
        "unit": "Cents per litre",
        "frequency": "monthly",
        "latest_period": "2026-10-01",
        "latest_value": 152.4,
        "prev_value": 151.9,
        "points": 25,
        "spark": [150.1, 151.2, 152.4],
    }
    base.update(over)
    return base


# ── the demo gate ───────────────────────────────────────────────────────────
class TestTheDemoGate:
    def test_a_live_payload_passes(self):
        payload = {"demo": False, "stations": [], "total": 0}
        assert _assert_live(payload, "stations") is payload

    def test_a_payload_without_the_flag_passes(self):
        """Only an explicit ``demo`` is a preview. Absence is not a signal."""
        payload = {"stations": []}
        assert _assert_live(payload, "stations") is payload

    def test_a_preview_is_refused(self):
        with pytest.raises(CloudFuelError):
            _assert_live({"demo": True, "stations": []}, "stations")

    def test_the_refusal_says_why(self):
        with pytest.raises(CloudFuelError, match="demo preview"):
            _assert_live({"demo": True}, "stations")


# ── the station re-shaping ──────────────────────────────────────────────────
class TestStationToRead:
    def test_the_fields_are_whereq_com_own(self):
        out = station_to_read(_station(), product="regular")
        assert out["id"] == 437547
        assert out["name"] == "Pioneer — 3279 Kingston Rd"
        assert out["brand"] == "Pioneer"
        assert out["city"] == "Toronto"
        assert out["country"] == "CA"
        assert out["lat"] == 43.7315166
        assert out["lng"] == -79.2247578

    def test_the_currency_is_looked_up_from_the_country(self):
        """The upstream quotes in local currency per litre but does not name
        the currency on the row — so the row cannot be passed through."""
        out = station_to_read(_station())
        assert out["currency"] == "CAD"
        assert out["unit"] == "CAD/L"

    def test_a_us_station_is_usd(self):
        out = station_to_read(_station(country="US"))
        assert out["currency"] == "USD"

    def test_a_mexican_station_is_mxn(self):
        out = station_to_read(_station(country="MX"))
        assert out["currency"] == "MXN"

    def test_the_prices_travel_with_the_row(self):
        out = station_to_read(_station())
        assert out["prices"]["regular"]["price"] == 1.669

    def test_the_observed_at_is_the_newest(self):
        out = station_to_read(_station())
        assert out["observed_at"] == "2026-10-25T19:57:50+00:00"

    def test_the_chosen_product_is_the_one_asked_for(self):
        out = station_to_read(_station(), product="diesel")
        assert out["price"] == 1.799
        assert out["product"] == "diesel"

    def test_a_station_without_that_product_has_no_price(self):
        out = station_to_read(_station(), product="premium")
        assert out["price"] is None

    def test_a_station_without_a_name_falls_back_to_the_brand(self):
        out = station_to_read(_station(name=None))
        assert out["name"] == "Pioneer"


# ── the series re-shaping ───────────────────────────────────────────────────
class TestSeriesToRead:
    def test_the_litre_normalisation_is_whereq_com_own_rule(self):
        """StatCan quotes cents per litre; the station prices are CAD/L. The
        UI puts an average next to a station price, so they must agree."""
        out = series_to_read(_series())
        assert out["value_per_litre"] == pytest.approx(1.524)
        assert out["currency"] == "CAD"

    def test_a_us_series_is_dollars_per_gallon_becomes_dollars_per_litre(self):
        out = series_to_read(_series(unit="$/GAL", latest_value=3.5))
        # The rule rounds to four decimals — the UI shows two.
        assert out["value_per_litre"] == pytest.approx(3.5 / 3.785411784, abs=1e-4)
        assert out["currency"] == "USD"

    def test_the_product_key_is_normalised(self):
        out = series_to_read(_series(item="Diesel fuel at full service filling stations"))
        assert out["product"] == "diesel"

    def test_an_unknown_item_has_no_product(self):
        out = series_to_read(_series(item="Aviation fuel"))
        assert out["product"] is None

    def test_the_fields_survive(self):
        out = series_to_read(_series())
        assert out["id"] == 22281
        assert out["region"] == "ca"
        assert out["geo"] == "Toronto, Ontario"
        assert out["item"].startswith("Regular unleaded")
        assert out["frequency"] == "monthly"
        assert out["latest_value"] == 152.4
        assert out["points"] == 25


# ── the identity of a station ───────────────────────────────────────────────
class TestStationIdentity:
    def test_the_external_id_is_the_same_one_the_mirror_used(self):
        """A station that was mirrored before the cut and is materialised
        after it must land on the same row, not beside it."""
        assert station_external_id(_station()) == "cheapgastoronto/pioneer-3279-kingston-rd-toronto-2"

    def test_a_long_id_is_hashed_rather_than_truncated(self):
        """Truncating would map two stations onto the same key and silently
        merge them, so a long id is hashed instead."""
        station = _station(ext_id="x" * 200)
        ext = station_external_id(station)
        assert len(ext) <= 64
        assert ext != "x" * 200


# ── the read mode ───────────────────────────────────────────────────────────
class TestTheReadMode:
    def test_the_fuel_router_has_a_read_mode(self):
        from app.api.routes.fuel import _mode

        assert _mode() in ("local", "dual", "cloud")

    def test_the_mode_defaults_to_cloud(self):
        """The prices are read live: whereq.cloud holds them, so this app reads
        them from there rather than keeping a copy that goes stale."""
        from app.core.config import Settings

        assert Settings().FUEL_READ_MODE == "cloud"

    def test_the_mirror_is_off_by_default(self):
        from app.core.config import Settings

        assert Settings().FUEL_MIRROR_ENABLED is False

    def test_the_mirror_switch_is_wired_to_both_fuel_ticks(self):
        """Two writers for the same tables is the failure the flag prevents,
        so both ticks must check it."""
        import inspect

        from app.crawler import scheduler

        for name in ("_fuel_tick", "_fuel_prices_tick"):
            source = inspect.getsource(getattr(scheduler, name))
            assert "FUEL_MIRROR_ENABLED" in source, name


# ── the throttle ────────────────────────────────────────────────────────────
class TestTheThrottle:
    def test_it_follows_the_key_tier(self):
        """The whereq.com service key is on the ``unlimited`` tier."""
        from app.services import whereq_cloud_client as wcc

        original = wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN
        try:
            wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN = 1200
            interval = wcc.shared_interval()
            # 60 / 1200 = 0.05 s, plus the 20% safety margin.
            assert interval == pytest.approx(0.06)
        finally:
            wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN = original

    def test_a_free_tier_key_is_still_paced_safely(self):
        from app.services import whereq_cloud_client as wcc

        original = wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN
        try:
            wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN = 30
            assert wcc.shared_interval() >= 2.0
        finally:
            wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN = original

    def test_the_old_floor_is_gone(self):
        """The old limiter was pinned at 2.2 s no matter what the key could
        do — 27 requests a minute on a key that allows 1 200."""
        from app.services import whereq_cloud_client as wcc

        original = wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN
        try:
            wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN = 1200
            assert wcc.shared_interval() < 0.1
        finally:
            wcc.settings.WHEREQ_CLOUD_RATE_LIMIT_PER_MIN = original

    def test_the_fuel_and_geo_feeds_share_one_limiter(self):
        """One key, one budget: two limiters would each allow the full
        budget and the pair would 429 itself."""
        from app.services import whereq_cloud_client as wcc

        assert wcc.shared_throttle is wcc.shared_throttle


# ── the licence rule ────────────────────────────────────────────────────────
class TestTheLicenceRule:
    def test_the_fuel_router_still_needs_a_session(self):
        """The prices are licensed: the whole router is behind a session, and
        a live read must not quietly open it."""
        from app.core.security import get_current_user
        from app.main import app

        routes = []
        for r in app.routes:
            sub = getattr(r, "original_router", None)
            if sub is not None and getattr(sub, "prefix", None) == "/fuel":
                routes.extend(sub.routes)
        assert routes
        for route in routes:
            deps = {d.call for d in route.dependant.dependencies}
            assert get_current_user in deps, route.path

    def test_anonymous_callers_get_no_prices(self):
        """The stripping is whereq.com's job and it does not move with the
        transport — a live station is stripped exactly like a mirrored one."""
        from app.api.routes.places import _without_prices

        meta = {"brand": "Pioneer", "prices": {"regular": {"price": 1.669}},
                "observed_at": "2026-10-25T19:57:50+00:00"}
        stripped = _without_prices(meta)
        assert "prices" not in stripped
        assert "observed_at" not in stripped
        assert stripped["brand"] == "Pioneer"


# ── the geography ───────────────────────────────────────────────────────────
class TestTheGeography:
    def test_the_at_route_serves_the_upstream_when_it_carries_the_licence(self):
        """The cut happens by itself the day whereq.cloud publishes the
        attribution — there is no flag to remember to flip."""
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(geo._upstream_at_carries_the_licence)
        assert 'p.get("license")' in source

    def test_the_licence_is_checked_once_not_on_every_pan(self):
        """Checking it means reading the upstream, and reading the upstream to
        throw the answer away would be a request per map pan for nothing."""
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(geo._upstream_at_carries_the_licence)
        assert "_AT_LICENCE_CHECKED_AT" in source
        assert "_AT_LICENCE_TTL" in source

    def test_the_at_route_falls_back_to_the_local_answer(self):
        """Without the licence the local answer is the one that carries the
        attribution the open licences require."""
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(geo.geo_at)
        assert "does not publish the licence" in source

    def test_the_boundaries_route_reads_the_upstream(self):
        """whereq.cloud serves a viewport's outlines in one request now, so
        the surface no longer needs the mirror."""
        import inspect

        from app.api.routes import geo

        source = inspect.getsource(geo.geo_boundaries)
        assert "_cloud_boundaries" in source
        assert "reads the local mirror in every mode" not in source

    def test_the_geography_mirror_still_runs(self):
        """The geo tick is a mirror of its own — it is switched off with
        ``GEO_INGEST_ENABLED``, not with the fuel mirrors, so the two
        decisions stay separate."""
        import inspect

        from app.crawler import scheduler

        source = inspect.getsource(scheduler._geo_tick)
        assert "FUEL_MIRROR_ENABLED" not in source


# ── the compose wiring ──────────────────────────────────────────────────────
class TestTheComposeWiring:
    def _compose(self) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return (root / "docker" / "docker-compose.yml").read_text()

    def test_the_read_mode_reaches_the_api(self):
        """A mode that never reaches the container looks exactly like a mode
        that does not work."""
        assert "FUEL_READ_MODE: ${FUEL_READ_MODE:-cloud}" in self._compose()

    def test_the_mirror_flag_reaches_the_consumer(self):
        assert "FUEL_MIRROR_ENABLED: ${FUEL_MIRROR_ENABLED:-false}" in self._compose()

    def test_the_rate_limit_reaches_both(self):
        compose = self._compose()
        assert compose.count("WHEREQ_CLOUD_RATE_LIMIT_PER_MIN") >= 2

class TestThePlacesSurfaces:
    def test_the_map_merges_the_live_stations(self):
        """The fuel pins come from whereq.cloud when the mode is ``cloud``."""
        import inspect

        from app.api.routes import places

        source = inspect.getsource(places.places_map)
        assert "_live_fuel_pins" in source

    def test_a_live_station_keeps_a_negative_id(self):
        """The local place ids are positive, so the sign is what tells a live
        station from a stored place — and the card reads it live."""
        from app.api.routes.places import _live_fuel_pins

        class _Result:
            def all(self):
                return []

        class _Db:
            async def execute(self, *a, **kw):
                return _Result()

        import asyncio

        def _fake(*a, **kw):
            return {"stations": [_station()], "total": 1}

        from app.services import cloud_fuel

        original = cloud_fuel.fetch_stations
        cloud_fuel.fetch_stations = _fake
        try:
            pins, points = asyncio.run(
                _live_fuel_pins(_Db(), bbox="-79.8,43.5,-79.2,44.0", limit=100))
        finally:
            cloud_fuel.fetch_stations = original

        assert len(pins) == 1
        assert pins[0].id == -437547
        assert pins[0].category == "gas"
        assert pins[0].kind == "poi"
        assert pins[0].sub == "Pioneer"
        assert points == [(-79.2247578, 43.7315166)]

    def test_the_card_reads_a_negative_id_live(self):
        import inspect

        from app.api.routes import places

        source = inspect.getsource(places.get_place)
        assert "place_id < 0" in source
        assert "_live_fuel_place" in source

    def test_a_saved_station_is_materialised(self):
        """A live station has no local row to point at, so saving one writes
        whereq.com's own row — identity only, no licensed prices."""
        import inspect

        from app.api.routes import saved_places

        source = inspect.getsource(saved_places.save_place)
        assert "_materialise_station" in source

    def test_the_materialised_row_holds_no_prices(self):
        """The licensed prices are read live; the stored row is identity."""
        from app.api.routes.saved_places import _station_meta

        meta = _station_meta({
            "brand": "Pioneer", "state": "Ontario", "municipality": "Toronto",
            "source": "cheapgastoronto", "id": 437547,
            "prices": {"regular": {"price": 1.669}},
            "observed_at": "2026-10-25T19:57:50+00:00",
        }, "CA")
        assert "prices" not in meta
        assert "observed_at" not in meta
        assert meta["brand"] == "Pioneer"
        assert meta["currency"] == "CAD"


# ── the paged read ──────────────────────────────────────────────────────────
class TestThePagedRead:
    """The upstream holds 500 stations on a page and orders them by its own
    station id, so one page is an arbitrary slice of the area."""

    @staticmethod
    def _paged_upstream(monkeypatch, *, total=1200, near_at=None):
        """A fake upstream that answers by offset, like the real one."""
        from app.services import cloud_fuel

        calls: list[dict] = []

        def _fake(*, limit=100, offset=0, **kw):
            calls.append({"limit": limit, "offset": offset, **kw})
            rows = []
            for i in range(offset, offset + limit):
                if i == near_at:
                    rows.append(_station(id=i, name="Near", lat=43.65, lon=-79.38))
                else:
                    # 5.5 km north of the search point — inside the radius.
                    rows.append(_station(id=i, name=f"Far {i}", lat=43.70, lon=-79.38))
            return {"stations": rows, "total": total, "demo": False}

        monkeypatch.setattr(cloud_fuel, "fetch_stations", _fake)
        return calls

    def test_it_reads_page_after_page(self, monkeypatch):
        from app.services import cloud_fuel

        calls = self._paged_upstream(monkeypatch)
        out = cloud_fuel.fetch_stations_paged(max_rows=1200)

        assert len(out["stations"]) == 1200
        assert out["total"] == 1200
        assert out["complete"] is True
        assert [c["offset"] for c in calls] == [0, 500, 1000]

    def test_a_box_bigger_than_the_ceiling_is_reported(self, monkeypatch):
        """The ceiling is a ceiling: the rows beyond it are not read, and the
        answer says so rather than pretending the area was covered."""
        from app.services import cloud_fuel

        self._paged_upstream(monkeypatch)
        out = cloud_fuel.fetch_stations_paged(max_rows=500)

        assert len(out["stations"]) == 500
        assert out["total"] == 1200
        assert out["complete"] is False

    def test_the_map_reads_more_than_one_page(self, monkeypatch):
        """A viewport holds more than 500 stations; the map must show them."""
        import asyncio

        from app.api.routes.places import _live_fuel_pins
        from app.services import cloud_fuel

        class _Result:
            def all(self):
                return []

        class _Db:
            async def execute(self, *a, **kw):
                return _Result()

        self._paged_upstream(monkeypatch)
        pins, points = asyncio.run(
            _live_fuel_pins(_Db(), bbox="-79.8,43.5,-79.2,44.0", limit=1200))

        assert len(pins) == 1200
        assert len(points) == 1200
        assert all(p.id < 0 for p in pins)

    def test_the_stations_are_sorted_over_the_whole_box(self, monkeypatch):
        """The nearest station must not be missed because it sits on the
        second page of the upstream's own id order."""
        import asyncio

        from app.api.routes.fuel import _cloud_stations
        from app.services import cloud_fuel

        self._paged_upstream(monkeypatch, near_at=700)
        out = asyncio.run(_cloud_stations(
            q=None, lat=43.65, lng=-79.38, radius_km=50, bbox=None,
            product="regular", sort="distance", limit=10))

        assert out[0]["name"] == "Near"
        assert out[0]["distance_km"] == 0.0

    def test_the_first_page_alone_would_have_missed_it(self, monkeypatch):
        """The defect the paged read fixes, stated as a fact about the
        upstream: the first page holds none of the nearest station."""
        from app.services import cloud_fuel

        calls = self._paged_upstream(monkeypatch, near_at=700)
        page = cloud_fuel.fetch_stations(bbox="x", limit=500)

        assert calls[0]["offset"] == 0
        assert all(s["name"] != "Near" for s in page["stations"])

    def test_the_viewport_and_the_radius_are_intersected(self, monkeypatch):
        """The local query answered the viewport AND the circle; the live read
        asks for the same set, so it reads the overlap and not the viewport."""
        import asyncio

        from app.api.routes.fuel import _cloud_stations
        from app.services import cloud_fuel

        calls = self._paged_upstream(monkeypatch)
        asyncio.run(_cloud_stations(
            q=None, lat=43.65, lng=-79.38, radius_km=10,
            bbox="-80.0,43.0,-79.0,44.0", product="regular",
            sort="distance", limit=5))

        box = calls[0]["bbox"]
        parts = [float(v) for v in box.split(",")]
        assert parts[0] > -80.0 and parts[2] < -79.0
        assert parts[1] > 43.0 and parts[3] < 44.0

    def test_the_boxes_intersection(self):
        from app.api.routes.fuel import _intersect_box

        assert _intersect_box(None, "1,2,3,4") == "1.0,2.0,3.0,4.0"
        assert _intersect_box("1,2,3,4", None) == "1.0,2.0,3.0,4.0"
        assert _intersect_box("0,0,10,10", "2,3,4,5") == "2.0,3.0,4.0,5.0"
        assert _intersect_box("0,0,1,1", "5,5,6,6") is None

    def test_the_nearby_list_reads_the_whole_box(self, monkeypatch):
        """The nearby list is nearest-first too, so it reads the whole box."""
        import asyncio

        from app.api.routes.nearby import _live_fuel_stations
        from app.services import cloud_fuel

        self._paged_upstream(monkeypatch, near_at=700)
        stations, count = asyncio.run(
            _live_fuel_stations(43.65, -79.38, 50_000, 5))

        assert stations, "the nearby list must not come back empty"
        assert stations[0]["distance_m"] == 0.0
        # The badge counts the stations nearby, not the ones the list had room for.
        assert count > 5

    def test_the_nearby_bucket_is_sorted_after_the_merge(self, monkeypatch):
        """The live stations are appended to the OSM rows of the same bucket,
        and the OSM rows are the further away — so the bucket must be sorted
        again or the list opens with a station kilometres away."""
        import asyncio

        from app.api.routes.nearby import _nearby_places
        from app.core.config import settings
        from app.services import cloud_fuel

        class _Result:
            def all(self):
                return []

        class _Db:
            async def execute(self, *a, **kw):
                return _Result()

        monkeypatch.setattr(settings, "FUEL_READ_MODE", "cloud")
        self._paged_upstream(monkeypatch, near_at=700)
        buckets, counts = asyncio.run(
            _nearby_places(_Db(), 43.65, -79.38, 50_000, ["fuel"], 5, False))

        distances = [i.distance_m for i in buckets["fuel"]]
        assert distances == sorted(distances)
        assert buckets["fuel"][0].distance_m == 0
