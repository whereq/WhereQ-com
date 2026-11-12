"""Maps service spend controls.

Two things were wrong:

* **Usage was only recorded on the success path.** The monthly quota is a
  spend control, but a request that reached Google costs money whether or not
  it returned a usable result — so a consumer could burn upstream quota with
  failing requests and never be charged against its quota.
* **The provider bias was hard-coded to Canada.** A lookup for a US address
  was restricted to Canadian results (and cached under the Canadian key),
  because the bias never followed the requested country.
"""

import asyncio
import uuid

from app.maps.usage import usage_tracker


class _FakeSession:
    """Minimal async session that records the usage statements."""

    def __init__(self):
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt):
        self.statements.append(stmt)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _recorded(session):
    """(endpoint, provider) for each recorded usage row."""
    out = []
    for stmt in session.statements:
        params = stmt.compile().params
        out.append((params["endpoint"], params["provider"]))
    return out


# ── usage accounting ─────────────────────────────────────────────────────────
def test_a_successful_request_is_recorded_with_its_provider():
    session = _FakeSession()
    consumer_id = uuid.uuid4()

    async def _run():
        async with usage_tracker(session, consumer_id, "geocode") as usage:
            usage.provider = "nominatim"

    asyncio.run(_run())

    assert _recorded(session) == [("geocode", "nominatim")]
    assert session.commits == 1


def test_a_failed_request_is_still_charged_to_the_quota():
    """The whole point: a request that reached the upstream provider costs
    money even when it failed."""
    session = _FakeSession()
    consumer_id = uuid.uuid4()

    async def _run():
        try:
            async with usage_tracker(session, consumer_id, "matrix") as usage:
                raise RuntimeError("upstream exploded")
        except RuntimeError:
            pass

    asyncio.run(_run())

    assert _recorded(session) == [("matrix", "error")]
    assert session.commits == 1


def test_a_failed_request_clears_a_broken_transaction_first():
    """A failure inside the handler may leave the session in a failed
    transaction state; the counter insert must still go through."""
    session = _FakeSession()
    consumer_id = uuid.uuid4()

    async def _run():
        try:
            async with usage_tracker(session, consumer_id, "route"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass

    asyncio.run(_run())

    assert session.rollbacks == 1
    assert _recorded(session) == [("route", "error")]


def test_a_failure_keeps_the_provider_the_handler_named():
    session = _FakeSession()
    consumer_id = uuid.uuid4()

    async def _run():
        try:
            async with usage_tracker(session, consumer_id, "geocode") as usage:
                usage.provider = "miss"
                raise RuntimeError("no match")
        except RuntimeError:
            pass

    asyncio.run(_run())

    assert _recorded(session) == [("geocode", "miss")]


def test_usage_accounting_never_breaks_the_request():
    """A failure to write the counter must not turn a working request into a
    500 — it is logged and swallowed."""
    class _BrokenSession(_FakeSession):
        async def execute(self, stmt):
            raise RuntimeError("counter table unavailable")

    session = _BrokenSession()
    consumer_id = uuid.uuid4()
    result = {}

    async def _run():
        async with usage_tracker(session, consumer_id, "geocode") as usage:
            usage.provider = "nominatim"
            result["value"] = "ok"

    asyncio.run(_run())

    assert result["value"] == "ok"


# ── country bias ─────────────────────────────────────────────────────────────
def test_the_bias_follows_the_requested_country():
    """A US lookup must not be restricted to Canadian results."""
    from app.api.routes.maps import _resolve_country

    assert _resolve_country("US") == ("us", "us")
    assert _resolve_country("us") == ("us", "us")
    assert _resolve_country("CA") == ("ca", "ca")


def test_without_a_country_the_deployment_default_applies():
    from app.api.routes.maps import _resolve_country
    from app.core.config import settings

    country, bias = _resolve_country(None)
    assert country == settings.GEOCODE_COUNTRY
    assert bias == settings.GEOCODE_REGION_BIAS.lower()


def test_the_manager_bias_follows_the_country():
    from app.services.geocoding.manager import _bias_for

    assert _bias_for("US") == "us"
    assert _bias_for("CA") == "ca"
    # An explicit region always wins.
    assert _bias_for("US", "GB") == "gb"


def test_google_is_not_the_default_for_the_maps_service():
    """The service must not spend paid quota on a consumer's behalf by
    default — Google is an explicit opt-in (``prefer_google=true``)."""
    from app.core.config import settings

    assert settings.MAPS_GEOCODE_GOOGLE_PREFERRED is False
