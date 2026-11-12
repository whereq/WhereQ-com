"""Explicit event date/time extraction from text (dependency-free).

Handles the common shapes seen in event listings/RSS:
  • "June 14, 2026"                        → date only
  • "June 14, 2026 at 7:00 PM"             → date + start time
  • "Sat, June 14 · 7:00 PM - 10:00 PM"    → start + end time (same day)
  • "June 14-16, 2026"                     → multi-day range
  • "2026-06-14" / "2026-06-14 19:00"      → ISO

Times are interpreted in a fixed default zone (UTC) when no zone is present —
event listings rarely carry an explicit offset, so stored times are approximate
to within the local UTC offset. The interface is swappable for an LLM extractor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_TIME = r"\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)"

_RE_MONTH_DATE = re.compile(
    rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:\s*[–-]\s*(\d{{1,2}}))?(?:,?\s*(\d{{4}}))?",
    re.IGNORECASE,
)
_RE_TIME_RANGE = re.compile(rf"({_TIME})(?:\s*(?:[–-]|to)\s*({_TIME}))?", re.IGNORECASE)
_RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?")


@dataclass
class EventDateTime:
    start: datetime
    end: datetime | None
    has_time: bool
    confidence: float


def _parse_time(s: str) -> tuple[int, int]:
    s = s.lower().replace(".", "").strip()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    hour = int(m.group(1)); minute = int(m.group(2) or 0); ap = m.group(3)
    if ap == "pm" and hour != 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    return min(hour, 23), min(minute, 59)


def extract_event_datetime(title: str, body: str | None = None, *,
                           base_year: int | None = None) -> EventDateTime | None:
    """Best-effort start/end extraction. Returns None when no date is found."""
    text = f"{title or ''}. {body or ''}"
    year_default = base_year or datetime.now(timezone.utc).year

    m = _RE_MONTH_DATE.search(text)
    if m:
        month = _MONTHS[m.group(1).lower().rstrip(".")]
        day1 = int(m.group(2))
        day2 = int(m.group(3)) if m.group(3) else None
        year = int(m.group(4)) if m.group(4) else year_default

        # Look for a time / time-range anywhere after the date token.
        hour = minute = 0
        has_time = False
        end_dt = None
        tm = _RE_TIME_RANGE.search(text, m.end())
        if tm:
            hour, minute = _parse_time(tm.group(1))
            has_time = True

        try:
            start = datetime(year, month, day1, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return None

        if day2 and day2 >= day1:  # multi-day range
            try:
                end_dt = datetime(year, month, day2, 23, 59, tzinfo=timezone.utc)
            except ValueError:
                end_dt = None
        elif tm and tm.group(2):    # same-day end time
            eh, em = _parse_time(tm.group(2))
            end_dt = datetime(year, month, day1, eh, em, tzinfo=timezone.utc)
            if end_dt <= start:
                end_dt = None

        return EventDateTime(start, end_dt, has_time, 0.75 if has_time else 0.55)

    iso = _RE_ISO.search(text)
    if iso:
        y, mo, d = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
        has_time = bool(iso.group(4))
        hh = int(iso.group(4)) if has_time else 0
        mm = int(iso.group(5)) if has_time else 0
        try:
            start = datetime(y, mo, d, hh, mm, tzinfo=timezone.utc)
        except ValueError:
            return None
        return EventDateTime(start, None, has_time, 0.7 if has_time else 0.5)

    return None
