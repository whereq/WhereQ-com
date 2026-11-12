"""Unit tests for Maps routing (Routes API) parsing + cache keys (no DB/network)."""

from app.services.routing import (
    _google_mode, _parse_duration, _parse_matrix, _parse_route,
    _rfc3339, _route_cache_key,
)


def test_google_mode_mapping():
    assert _google_mode("driving") == "DRIVE"
    assert _google_mode("walking") == "WALK"
    assert _google_mode("cycling") == "BICYCLE"      # public → Routes API term
    assert _google_mode("nonsense") == "DRIVE"       # safe default
    assert _google_mode(None) == "DRIVE"


def test_parse_duration():
    assert _parse_duration("2040s") == 2040
    assert _parse_duration("60.4s") == 60
    assert _parse_duration(None) is None
    assert _parse_duration("bad") is None


def test_parse_route_traffic_aware():
    body = {"routes": [{
        "distanceMeters": 24800,
        "duration": "2380s",          # traffic-aware
        "staticDuration": "2040s",    # free-flow baseline
        "polyline": {"encodedPolyline": "abc123"},
        "viewport": {"low": {"latitude": 43.58, "longitude": -79.66},
                     "high": {"latitude": 43.66, "longitude": -79.37}},
    }]}
    r = _parse_route(body, traffic=True)
    assert r["distance_m"] == 24800
    assert r["duration_s"] == 2040                    # baseline
    assert r["duration_in_traffic_s"] == 2380         # traffic
    assert r["polyline"] == "abc123"
    assert r["bounds"] == {"north": 43.66, "south": 43.58, "east": -79.37, "west": -79.66}


def test_parse_route_no_traffic_nulls_traffic_field():
    body = {"routes": [{"distanceMeters": 100, "duration": "60s",
                        "staticDuration": "60s",
                        "polyline": {"encodedPolyline": "x"}}]}
    r = _parse_route(body, traffic=False)
    assert r["duration_s"] == 60
    assert r["duration_in_traffic_s"] is None
    assert r["bounds"] is None


def test_parse_route_empty():
    assert _parse_route({"routes": []}) is None


def test_parse_matrix_scatters_flat_elements_into_grid():
    # 2 origins × 2 destinations, returned flat + out of order
    elements = [
        {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 5000,
         "duration": "600s", "condition": "ROUTE_EXISTS"},
        {"originIndex": 1, "destinationIndex": 0, "condition": "ROUTE_NOT_FOUND"},
        {"originIndex": 0, "destinationIndex": 1, "distanceMeters": 8000,
         "duration": "900s", "condition": "ROUTE_EXISTS"},
        {"originIndex": 1, "destinationIndex": 1, "distanceMeters": 3000,
         "duration": "400s", "condition": "ROUTE_EXISTS"},
    ]
    out = _parse_matrix(elements, 2, 2)
    assert out["rows"][0]["elements"][0] == {"distance_m": 5000, "duration_s": 600, "status": "OK"}
    assert out["rows"][0]["elements"][1] == {"distance_m": 8000, "duration_s": 900, "status": "OK"}
    assert out["rows"][1]["elements"][0]["status"] == "ROUTE_NOT_FOUND"
    assert out["rows"][1]["elements"][0]["distance_m"] is None
    assert out["rows"][1]["elements"][1] == {"distance_m": 3000, "duration_s": 400, "status": "OK"}


def test_rfc3339():
    assert _rfc3339("now") is None
    assert _rfc3339(None) is None
    assert _rfc3339("1700000000").endswith("Z")
    assert _rfc3339("2026-09-28T12:00:00Z") == "2026-09-28T12:00:00Z"


def test_route_cache_key_rounds_and_varies():
    a = _route_cache_key("driving", (43.653200, -79.383200), (43.5890, -79.6441), False)
    b = _route_cache_key("driving", (43.6532004, -79.3832001), (43.5890, -79.6441), False)
    assert a == b                                     # within 5dp → same key
    assert a != _route_cache_key("driving", (43.6532, -79.3832), (43.5890, -79.6441), True)
    assert a != _route_cache_key("walking", (43.6532, -79.3832), (43.5890, -79.6441), False)
