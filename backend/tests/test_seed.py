"""The seeded demo accounts must not carry a password in the source.

A password that is committed to the repository is a password that everybody
has, and a copy-paste target. The seed takes its passwords from the
environment, or generates them per run and prints them once.
"""

import re

from app import seed


def test_the_seed_source_carries_no_password():
    """The obvious check: no literal password in the USERS table."""
    for u in seed.USERS:
        assert "password" not in u or u["password"] == "", (
            f"seed.USERS[{u['username']}] carries a literal password"
        )


def test_the_usernames_are_still_the_documented_pair():
    assert [u["username"] for u in seed.USERS] == ["demo", "admin"]


def test_a_missing_environment_password_is_generated(monkeypatch):
    monkeypatch.delenv("SEED_DEMO_PASSWORD", raising=False)
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)

    users = {u["username"]: u for u in seed._demo_users()}

    for name, u in users.items():
        assert u["generated"] is True
        assert u["password"], f"{name} got no password"
        assert len(u["password"]) >= 16


def test_generated_passwords_differ_between_accounts(monkeypatch):
    monkeypatch.delenv("SEED_DEMO_PASSWORD", raising=False)
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)

    users = {u["username"]: u for u in seed._demo_users()}
    assert users["demo"]["password"] != users["admin"]["password"]


def test_an_environment_password_is_used_as_given(monkeypatch):
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "from-the-environment")

    users = {u["username"]: u for u in seed._demo_users()}

    assert users["admin"]["password"] == "from-the-environment"
    assert users["admin"]["generated"] is False


def test_a_blank_environment_password_falls_back_to_generation(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "   ")

    users = {u["username"]: u for u in seed._demo_users()}

    assert users["demo"]["generated"] is True
    assert users["demo"]["password"].strip()


def test_the_generated_password_is_usable_as_a_password():
    """It must survive the bcrypt round-trip the seed performs."""
    from app.core.security import hash_password, verify_password

    generated = seed._demo_users()[0]["password"]
    assert verify_password(generated, hash_password(generated))


def test_no_committed_password_looks_like_a_demo_credential():
    """A belt-and-braces check on the module source itself."""
    source = open(seed.__file__, encoding="utf-8").read()
    assert not re.search(r"password\s*=\s*[\"'](demo|admin)\d+[\"']", source)
