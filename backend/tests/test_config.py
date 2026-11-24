"""Configuration safety rails.

The most dangerous default in the backend is ``APP_ENV=development``: it turns
on SQL echo (every statement *and its bound parameters* — emails, tokens —
goes to the log) and on ``create_all`` (tables are created straight from the
models, which hides a missing Alembic migration). On a shared or production
database either one is a mistake, so the app refuses to start in that
combination.

The second rail is the credential itself. A secret with a **default** in the
source is a secret that ends up in the repository and from there in everyone's
clone, so the defaults are empty and a production deployment has to supply
real values — the app refuses to start otherwise.
"""

import pytest

from app.core.config import (
    Settings,
    _DEV_DATABASE_URL,
    _DEV_DATABASE_URL_SYNC,
    settings,
)


def _settings(**overrides) -> Settings:
    """Build a Settings with values that do NOT come from the environment.

    Every relevant field is passed explicitly, so a test never depends on a
    developer's local ``backend/.env`` — that dependency once made a broken
    production check pass on this machine and fail in a fresh clone.
    """
    base = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/whereq",
        "DATABASE_URL_SYNC": "postgresql://u:p@localhost:5432/whereq",
        "SECRET_KEY": "a-real-secret",
        "APP_ENV": "development",
    }
    base.update(overrides)
    return Settings(**base)


# ── development mode against a non-local database ────────────────────────────
def test_development_against_a_remote_database_is_unsafe():
    s = _settings(DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq")
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
        DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq",
        DATABASE_URL_SYNC="postgresql://u:p@postgres:5432/whereq",
        SECRET_KEY="a-real-secret",
    )
    assert s.unsafe_dev_mode is False


def test_an_unparsable_database_url_does_not_block_startup():
    """We cannot prove the host is remote, so we do not guess."""
    s = _settings(DATABASE_URL="not-a-url")
    assert s.database_host is None
    assert s.unsafe_dev_mode is False


def test_the_database_host_is_parsed_out_of_the_url():
    s = _settings(DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq")
    assert s.database_host == "postgres"


# ── credentials have no defaults ─────────────────────────────────────────────
def test_the_development_database_default_carries_no_password():
    """A credential must never be baked into the source."""
    assert ":password@" not in _DEV_DATABASE_URL
    assert ":password@" not in _DEV_DATABASE_URL_SYNC


def test_no_secret_is_committed_as_a_default():
    assert settings.SECRET_KEY not in ("change-me", "change-me-in-production")


def test_a_production_deployment_without_a_secret_key_refuses_to_start():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _settings(
            APP_ENV="production",
            SECRET_KEY="",
            DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq",
        )


def test_a_production_deployment_with_a_placeholder_secret_refuses_to_start():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _settings(
            APP_ENV="production",
            SECRET_KEY="change-me",
            DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq",
        )


def test_a_production_deployment_on_the_development_database_refuses_to_start():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        _settings(
            APP_ENV="production",
            SECRET_KEY="a-real-secret",
            DATABASE_URL=_DEV_DATABASE_URL,
            DATABASE_URL_SYNC=_DEV_DATABASE_URL_SYNC,
        )


def test_a_production_deployment_with_real_credentials_starts():
    s = _settings(
        APP_ENV="production",
        SECRET_KEY="a-real-secret",
        DATABASE_URL="postgresql+asyncpg://u:p@postgres:5432/whereq",
        DATABASE_URL_SYNC="postgresql://u:p@postgres:5432/whereq",
    )
    assert s.SECRET_KEY == "a-real-secret"


def test_development_is_exempt_from_the_secret_requirement():
    """A local dev run has no real secret to set — the defaults are fine."""
    s = _settings(APP_ENV="development", SECRET_KEY="")
    assert s.unsafe_dev_mode is False


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
