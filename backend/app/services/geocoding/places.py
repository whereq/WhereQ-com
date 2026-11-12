"""Google Places API (New) — Autocomplete.

Places Autocomplete is a distinct Google API (separate billing from Geocoding),
so it lives outside the geocode provider chain. Predictions are grouped into a
billable *session* via a session token: all keystrokes of one search plus the
resolving Place Details / geocode call share the same ``sessionToken``.

This uses the **Places API (New)** endpoint
``POST https://places.googleapis.com/v1/places:autocomplete`` (auth via the
``X-Goog-Api-Key`` header). Per Google Maps ToS, autocomplete predictions must
NOT be cached across sessions — so this module never persists predictions.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"


@dataclass
class Suggestion:
    """One autocomplete prediction. ``lat/lng/components`` are resolved later
    (on selection) via ``/geocode?place_id=…`` within the same session."""
    id: str                      # provider place ref (Google place id)
    primary: str | None          # e.g. "401 Bay Street"
    secondary: str | None        # e.g. "Toronto, ON, Canada"
    formatted: str | None        # full description


class GooglePlacesProvider:
    name = "google"

    def __init__(self, settings):
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.maps_google_key)

    async def autocomplete(
        self,
        client: httpx.AsyncClient,
        q: str,
        *,
        country: str | None = None,
        limit: int = 5,
        proximity: tuple[float, float] | None = None,
        session: str | None = None,
        lang: str = "en",
    ) -> list[Suggestion]:
        body: dict = {"input": q, "languageCode": lang}
        if country:
            codes = [c.strip().lower() for c in country.split(",") if c.strip()][:15]
            if codes:
                body["includedRegionCodes"] = codes
        if proximity:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": proximity[0], "longitude": proximity[1]},
                    "radius": 50000.0,   # metres — a soft bias, not a hard filter
                }
            }
        if session:
            body["sessionToken"] = session

        headers = {
            "X-Goog-Api-Key": self.settings.maps_google_key,
            "Content-Type": "application/json",
        }
        resp = await client.post(_AUTOCOMPLETE_URL, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        out: list[Suggestion] = []
        for sug in (data.get("suggestions") or []):
            pred = sug.get("placePrediction")
            if not pred:   # skip queryPrediction entries (no place id)
                continue
            sf = pred.get("structuredFormat") or {}
            main = (sf.get("mainText") or {}).get("text")
            secondary = (sf.get("secondaryText") or {}).get("text")
            out.append(Suggestion(
                id=pred.get("placeId"),
                primary=main,
                secondary=secondary,
                formatted=(pred.get("text") or {}).get("text"),
            ))
            if len(out) >= limit:
                break
        return out
