"""Unit tests for Maps §4 address-component normalization (no DB/network)."""

from types import SimpleNamespace

from app.services.geocoding.providers import (
    GeocodioProvider, _google_components, _osm_components, _places_new_components,
)


def test_google_components_maps_region_to_two_letter_code():
    result = {
        "address_components": [
            {"long_name": "401", "short_name": "401", "types": ["street_number"]},
            {"long_name": "Bay Street", "short_name": "Bay St", "types": ["route"]},
            {"long_name": "Toronto", "short_name": "Toronto", "types": ["locality"]},
            {"long_name": "Ontario", "short_name": "ON",
             "types": ["administrative_area_level_1"]},
            {"long_name": "Canada", "short_name": "CA", "types": ["country"]},
            {"long_name": "M5H 2Y4", "short_name": "M5H 2Y4", "types": ["postal_code"]},
        ],
    }
    c = _google_components(result)
    assert c.line1 == "401 Bay Street"
    assert c.city == "Toronto"
    assert c.region == "ON"          # short_name, never the full province name
    assert c.region_name == "Ontario"
    assert c.postal_code == "M5H 2Y4"
    assert c.country == "CA"


def test_google_components_city_falls_back_to_postal_town():
    result = {"address_components": [
        {"long_name": "London", "short_name": "London", "types": ["postal_town"]},
    ]}
    assert _google_components(result).city == "London"


def test_osm_components_extracts_region_from_iso_code():
    addr = {
        "house_number": "401", "road": "Bay Street", "city": "Toronto",
        "state": "Ontario", "ISO3166-2-lvl4": "CA-ON",
        "postcode": "M5H 2Y4", "country_code": "ca",
    }
    c = _osm_components(addr)
    assert c.line1 == "401 Bay Street"
    assert c.city == "Toronto"
    assert c.region == "ON"
    assert c.region_name == "Ontario"
    assert c.postal_code == "M5H 2Y4"
    assert c.country == "CA"          # upper-cased alpha-2


def test_osm_components_handles_missing_iso_code():
    c = _osm_components({"town": "Barrie", "state": "Ontario"})
    assert c.city == "Barrie"
    assert c.region is None           # no ISO code → no 2-letter region
    assert c.region_name == "Ontario"


def test_places_new_components():
    # Places API (New) uses longText/shortText instead of long_name/short_name.
    components = [
        {"longText": "401", "shortText": "401", "types": ["street_number"]},
        {"longText": "Bay Street", "shortText": "Bay St", "types": ["route"]},
        {"longText": "Toronto", "shortText": "Toronto", "types": ["locality"]},
        {"longText": "Ontario", "shortText": "ON",
         "types": ["administrative_area_level_1"]},
        {"longText": "Canada", "shortText": "CA", "types": ["country"]},
        {"longText": "M5H 2Y4", "shortText": "M5H 2Y4", "types": ["postal_code"]},
    ]
    c = _places_new_components(components)
    assert c.line1 == "401 Bay Street"
    assert c.city == "Toronto"
    assert c.region == "ON"
    assert c.region_name == "Ontario"
    assert c.postal_code == "M5H 2Y4"
    assert c.country == "CA"


def test_geocodio_components():
    fields = {"number": "401", "formatted_street": "Bay St", "city": "Toronto",
              "state": "ON", "zip": "M5H 2Y4", "country": "CA"}
    c = GeocodioProvider._components(fields)
    assert c.line1 == "401 Bay St"
    assert c.region == "ON"
    assert c.postal_code == "M5H 2Y4"
    assert c.country == "CA"
