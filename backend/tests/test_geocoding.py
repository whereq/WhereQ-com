"""Unit tests for the multi-provider geocoder selection logic (no DB/network)."""

from types import SimpleNamespace

from app.services.geocoding.providers import (
    GeocodioProvider, GoogleProvider, LocationIQProvider, NominatimProvider,
    PositionstackProvider, PROVIDER_CLASSES,
)


def _settings(**over):
    base = dict(
        NOMINATIM_BASE_URL="https://nominatim.openstreetmap.org", NOMINATIM_RPS=1.0,
        NOMINATIM_EMAIL="", NOMINATIM_DAILY_QUOTA=100_000,
        GEOCODIO_API_KEY="", GEOCODIO_DAILY_QUOTA=2_500,
        LOCATIONIQ_API_KEY="", LOCATIONIQ_DAILY_QUOTA=5_000,
        GEOCODE_MAPS_CO_API_KEY="", GEOCODE_MAPS_CO_DAILY_QUOTA=5_000,
        POSITIONSTACK_API_KEY="", POSITIONSTACK_MONTHLY_QUOTA=25_000,
        GOOGLE_MAPS_API_KEY="", GOOGLE_MAPS_SERVER_KEY="", GOOGLE_GEOCODE_DAILY_QUOTA=100_000,
    )
    base.update(over)
    # Mirror Settings.maps_google_key (server key preferred, else the SPA key).
    base["maps_google_key"] = base.get("GOOGLE_MAPS_SERVER_KEY") or base.get("GOOGLE_MAPS_API_KEY")
    return SimpleNamespace(**base)


def test_registry_has_all_providers():
    assert set(PROVIDER_CLASSES) == {
        "nominatim", "geocode_maps_co", "locationiq", "geocodio", "positionstack", "google",
    }


def test_is_configured_depends_on_keys():
    s = _settings()
    assert NominatimProvider(s).is_configured() is True          # no key needed
    assert GeocodioProvider(s).is_configured() is False          # needs key
    assert GeocodioProvider(_settings(GEOCODIO_API_KEY="k")).is_configured() is True
    assert GoogleProvider(s).is_configured() is False
    assert LocationIQProvider(_settings(LOCATIONIQ_API_KEY="k")).is_configured() is True


def test_quota_limits_come_from_settings():
    assert GeocodioProvider(_settings()).quota_limit() == 2_500
    assert LocationIQProvider(_settings()).quota_limit() == 5_000
    assert PositionstackProvider(_settings()).quota_limit() == 25_000


def test_period_key_day_vs_month():
    s = _settings()
    assert len(NominatimProvider(s).period_key()) == 10   # YYYY-MM-DD (daily)
    assert len(PositionstackProvider(s).period_key()) == 7  # YYYY-MM (monthly)


def test_nominatim_rate_limit_from_rps():
    assert NominatimProvider(_settings(NOMINATIM_RPS=1.0)).min_interval == 1.0
    assert NominatimProvider(_settings(NOMINATIM_RPS=2.0)).min_interval == 0.5


def test_default_order_keeps_google_last():
    from app.core.config import settings
    order = [s.strip() for s in settings.GEOCODE_PROVIDER_ORDER.split(",") if s.strip()]
    assert order[-1] == "google"
    assert "nominatim" in order
