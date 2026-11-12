"""Configuration safety rails.

The most dangerous default in the backend is ``APP_ENV=development``: it turns
on SQL echo (every statement *and its bound parameters* — emails, tokens —
goes to the log) and on ``create_all`` (tables are created straight from the
models, which hides a missing Alembic migration). On a shared or production
database either one is a mistake, so the app refuses to start in that
combination.
"""

import pytest

from app.core.config import Settings, settings


def _settings(**overrides) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/whereq",
        "APP_ENV": "development",
    }
    base.update(overrides)
    return Settings(**base)


# ── development mode against a non-local database ────────────────────────────
def test_development_against_a_remote_database_is_unsafe():
    s = _settings(DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq-com")
    assert s.unsafe_dev_mode is True


def test_development_against_a_local_database_is_fine():
    s = _settings()
    assert s.unsafe_dev_mode is False


@pytest.mark.parametrize(
    "host",
    ["localhost", "127.0.0.1", "::1", "host.docker.internal"],
)
def test_local_hosts_are_all_considered_local(host):
    s = _settings(DATABASE_URL=f"postgresql+asyncpg://u:p@{host}:5432/whereq")
    assert s.unsafe_dev_mode is False


def test_production_against_a_remote_database_is_fine():
    s = _settings(
        APP_ENV="production",
        DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq-com",
    )
    assert s.unsafe_dev_mode is False


def test_an_unparsable_database_url_does_not_block_startup():
    """We cannot prove the host is remote, so we do not guess."""
    s = _settings(DATABASE_URL="not-a-url")
    assert s.database_host is None
    assert s.unsafe_dev_mode is False


def test_the_database_host_is_parsed_out_of_the_url():
    s = _settings(DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq-com")
    assert s.database_host == "postgres"


# ── staff roles ──────────────────────────────────────────────────────────────
def test_the_canonical_staff_role_is_recognised():
    assert "whereq-admin" in settings.staff_roles


def test_the_legacy_maps_admin_role_is_still_honoured():
    s = Settings(STAFF_ROLE="whereq-admin", MAPS_ADMIN_ROLE="whereq-maps")
    assert "whereq-maps" in s.staff_roles
    assert "whereq-admin" in s.staff_roles


def test_a_deployment_that_only_sets_the_legacy_role_still_works(monkeypatch):
    """The Maps-specific name is an alias, so a deployment that only sets the
    older MAPS_ADMIN_ROLE keeps working."""
    from app.core.security import has_staff_role

    monkeypatch.setattr(settings, "STAFF_ROLE", "whereq-admin")
    monkeypatch.setattr(settings, "MAPS_ADMIN_ROLE", "whereq-maps")

    assert has_staff_role({"realm_access": {"roles": ["whereq-maps"]}}) is True
    assert has_staff_role({"realm_access": {"roles": ["whereq-admin"]}}) is True
    assert has_staff_role({"realm_access": {"roles": ["someone-else"]}}) is False
