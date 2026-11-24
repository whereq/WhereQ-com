"""The SDK floor — the app's dependency on whereq.cloud, pinned and checked.

THE FLOOR IS NOT A STYLE CHOICE
-------------------------------
whereq.com calls ``geo_boundaries(exclude_kind=...)`` — the bulk outline
route's kind exclusion. That parameter **did not exist before the SDK's
0.8.1**, so a virtual environment on 0.8.0 raises ``TypeError`` from inside
the SDK's own argument parsing the first time a map pan asks for outlines.
The failure is invisible until then, and it says nothing about the cause.

So the floor is checked in two places, and they are checked against each
other:

1. ``check_sdk_version()`` runs before every upstream read, so a stale
   environment fails with a message that names the version and the fix.

2. This test pins the floor to the **pin in requirements.txt**, so the
   constant cannot drift away from the declared dependency, and asserts
   that the installed SDK satisfies it — so a stale environment fails in
   CI rather than in production.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.whereq_cloud_client import (
    SDK_FLOOR,
    check_sdk_version,
    sdk_version,
    _version_tuple,
)

#: ``backend/requirements.txt``
REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"


def _pinned_floor() -> str:
    """The floor as it is written in requirements.txt."""
    text = REQUIREMENTS.read_text()
    match = re.search(r"^whereq\.cloud\s*>=\s*([0-9.]+)\s*$", text, re.MULTILINE)
    assert match, "requirements.txt must pin whereq.cloud with a >= floor"
    return match.group(1)


class TestTheFloorIsPinned:
    def test_the_constant_matches_the_requirements_pin(self):
        assert SDK_FLOOR == _pinned_floor(), (
            f"SDK_FLOOR is {SDK_FLOOR} but requirements.txt pins "
            f"whereq.cloud>={_pinned_floor()}"
        )

    def test_the_installed_sdk_satisfies_the_floor(self):
        installed = sdk_version()
        assert _version_tuple(installed) >= _version_tuple(SDK_FLOOR), (
            f"the installed whereq.cloud is {installed}, but the floor is "
            f"{SDK_FLOOR} — pip install -U 'whereq.cloud>={SDK_FLOOR}'"
        )

    def test_checking_passes_on_the_installed_sdk(self):
        check_sdk_version()


class TestTheVersionsCompare:
    @pytest.mark.parametrize(
        "left,right,expected",
        [
            ("0.8.1", "0.8.1", True),
            ("0.8.1", "0.8.0", True),
            ("0.8.0", "0.8.1", False),
            ("0.9.0", "0.8.1", True),
            ("1.0.0", "0.8.1", True),
            ("0.8", "0.8.1", False),
            ("0.10.0", "0.9.0", True),
        ],
    )
    def test_ordering(self, left, right, expected):
        assert (_version_tuple(left) >= _version_tuple(right)) is expected


class TestTheGuardFires:
    def test_an_old_sdk_is_refused_with_an_actionable_message(self, monkeypatch):
        from app.services import whereq_cloud_client as module

        monkeypatch.setattr(module, "sdk_version", lambda: "0.8.0")
        with pytest.raises(RuntimeError) as excinfo:
            module.check_sdk_version()
        message = str(excinfo.value)
        assert "0.8.0" in message
        assert SDK_FLOOR in message
        assert "pip install" in message
