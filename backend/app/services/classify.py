"""Content classification: assign a category + content type from text.

Rule-based keyword scoring for now. The public interface (``classify``) is
intentionally small so it can later delegate to an LLM enrichment step without
changing callers — the crawler pipeline only depends on the return shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# category -> keywords. Order matters only for tie-breaking via specificity
# weighting below; scoring is additive.
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "accident": ["collision", "crash", "multi-vehicle", "pile-up", "rollover", "car accident",
                 "pedestrian struck", "vehicle", "traffic accident"],
    "crime": ["shooting", "stabbing", "homicide", "robbery", "assault", "arrest", "suspect",
              "police investigate", "break-in", "carjacking", "gunfire", "fatal shooting"],
    "fire": ["fire", "blaze", "firefighters", "smoke", "arson", "two-alarm", "three-alarm"],
    "weather": ["storm", "snow squall", "flood", "tornado", "heat warning", "freezing rain",
                "thunderstorm", "blizzard", "weather warning", "rainfall warning"],
    "transportation": ["ttc", "subway", "go transit", "road closure", "lane closure", "delays",
                       "transit", "highway closed", "traffic", "detour"],
    "construction": ["construction", "roadwork", "infrastructure", "development", "rezoning",
                     "condo", "building permit", "demolition"],
    "festival": ["festival", "parade", "fair", "carnival", "celebration"],
    "event": ["concert", "market", "exhibition", "show", "game", "tournament", "gathering",
              "workshop", "screening", "performance"],
    "business": ["opening", "opens", "closing", "closes", "restaurant", "store", "shop",
                 "business", "bakery", "cafe", "café", "brewery", "launch"],
    "education": ["school", "students", "university", "college", "tdsb", "tcdsb", "board of education",
                  "campus", "classroom"],
    "government": ["city council", "mayor", "municipal", "bylaw", "budget", "election",
                   "province announces", "premier", "city of toronto"],
    "health": ["hospital", "outbreak", "health unit", "overdose", "public health", "advisory"],
    "community": ["neighbourhood", "neighborhood", "residents", "community", "local", "volunteer"],
}

# Type inference from category (events/festivals -> event; civic chatter -> topic).
_CATEGORY_TYPE = {
    "festival": "event",
    "event": "event",
    "business": "story",
    "construction": "story",
    "education": "story",
    "government": "topic",
    "community": "story",
}


@dataclass
class Classification:
    category: str
    content_type: str
    confidence: float
    tags: list[str]


def _count(keyword: str, text: str) -> int:
    # word-ish boundary match, case-insensitive
    return len(re.findall(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text))


def classify(title: str, body: str | None = None, *, default_type: str = "news") -> Classification:
    """Classify text into (category, content_type, confidence, tags)."""
    text = f"{title or ''}. {body or ''}".lower()

    scores: dict[str, int] = {}
    hit_tags: list[str] = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            n = _count(kw.lower(), text)
            if n:
                score += n
                hit_tags.append(kw)
        if score:
            scores[category] = score

    if not scores:
        return Classification("other", default_type, 0.2, [])

    category = max(scores, key=lambda c: scores[c])
    total = sum(scores.values())
    confidence = min(0.95, 0.4 + 0.5 * (scores[category] / total))
    content_type = _CATEGORY_TYPE.get(category, default_type)

    # de-duplicate tags, keep a compact set
    tags = list(dict.fromkeys(hit_tags))[:8]
    return Classification(category, content_type, round(confidence, 3), tags)
