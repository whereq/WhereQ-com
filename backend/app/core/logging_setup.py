"""Shared logging setup for the entry points.

httpx logs the **full request URL** at INFO, and the Google Geocoding URL
carries the server API key in its query string — so every geocode wrote a
live credential into the container logs. httpx is therefore quietened to
WARNING; the providers log their own outcomes, and the request log was never
worth a leaked key.
"""

from __future__ import annotations

import logging

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def configure_logging(level: int = logging.INFO, fmt: str = DEFAULT_FORMAT) -> None:
    """Configure the root logger and keep secrets out of the request log."""
    logging.basicConfig(level=level, format=fmt)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
