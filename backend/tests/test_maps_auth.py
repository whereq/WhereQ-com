"""Unit tests for Maps key generation + per-key rate bucket (no DB/network)."""

import json
from types import SimpleNamespace

import pytest

from app.maps.auth import _check_rate, generate_key, hash_key
from app.maps.errors import MapsError, error_json
from app.maps.keys import _parse_scopes


def test_generate_key_shape_and_prefix():
    plaintext, key_hash, key_prefix = generate_key("live")
    assert plaintext.startswith("wq_live_")
    assert key_prefix == plaintext[:12]
    assert len(key_hash) == 64            # sha256 hex
    assert hash_key(plaintext) == key_hash
    assert plaintext.isascii()


def test_generate_key_is_unique():
    a, _, _ = generate_key()
    b, _, _ = generate_key()
    assert a != b


def test_check_rate_allows_then_blocks_with_retry_after():
    consumer = SimpleNamespace(id="unit-test-bucket-1", rate_limit_per_min=2)
    assert _check_rate(consumer) == (True, 0)
    assert _check_rate(consumer)[0] is True
    allowed, retry = _check_rate(consumer)     # third within the same window
    assert allowed is False
    assert retry >= 1                          # Retry-After seconds


def test_parse_scopes_accepts_valid_and_rejects_unknown():
    assert _parse_scopes("geocode, reverse ,route") == ["geocode", "reverse", "route"]
    with pytest.raises(ValueError):
        _parse_scopes("geocode,teleport")


def test_error_envelope_shape_and_headers():
    resp = error_json(429, "rate_limited", "slow down", "wqm_abc", retry_after=30)
    assert resp.status_code == 429
    assert resp.headers["X-Request-Id"] == "wqm_abc"
    assert resp.headers["Retry-After"] == "30"
    body = json.loads(bytes(resp.body))
    assert body == {"error": {"code": "rate_limited", "message": "slow down",
                              "request_id": "wqm_abc"}}


def test_maps_error_carries_fields():
    err = MapsError(403, "forbidden_scope", "nope")
    assert (err.status_code, err.code, err.retry_after) == (403, "forbidden_scope", None)
