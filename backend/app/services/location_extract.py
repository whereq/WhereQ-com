"""Heuristic location extraction from news/event text.

Produces ordered location *candidates* (most specific first) that the crawler
pipeline then geocodes. This is deliberately dependency-free and rule-based so
it runs fast in the crawler; the interface is designed so an LLM-based
extractor can be slotted in later behind the same ``extract_locations`` call.

Two ideas drive the design:

**Precision.** A candidate becomes a pin, so a wrong candidate becomes a wrong
pin. The old intersection rule ("Proper and Proper") accepted *any* two
capitalised phrases — "George Russell & Ferrari", "British Columbia &
Quebec", "Job Creation & Trade" — and the road rule accepted "Supreme Court"
because "Court" is a street type. Both are now rejected: an intersection only
counts when *both* sides look like roads, and a court is not a street.

**Recall.** Point-level places are named in prose far more often than a regex
can spot: "Scotiabank Arena", "Kipling Station", "Upper Canada Mall". Those
come from the curated name list in ``app.services.gta_places`` — names only,
no coordinates, because the geocoder already resolves place names well.

A bare city name ("Toronto") is *not* a location and never becomes a query:
that is what put thousands of items on one false pin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.geo_gazetteer import detect_city
from app.services.gta_places import (
    INSTITUTION_ADJECTIVES,
    find_all_places,
    find_place,
    is_admin_region,
    is_street_name,
)

# Road suffixes used to recognize street/road phrases. Singular and plural
# forms are both listed: "Wellesley Streets" is as common in news copy as
# "Wellesley Street", and the old list only had the singular.
_ROAD_SUFFIX = (
    r"(?:Streets|Street|St|Avenues|Avenue|Ave|Roads|Road|Rd|"
    r"Boulevards|Boulevard|Blvd|Drives|Drive|Dr|Crescents|Crescent|Cres|"
    r"Ways|Way|Lanes|Lane|Ln|Court|Ct|Places|Place|Pl|Parkways|Parkway|Pkwy|"
    r"Expressways|Expressway|Trails|Trail|Terraces|Terrace|"
    r"Gardens|Gate|Gates|Circles|Circle|Squares|Square|Sq|"
    r"Highways|Highway|Hwy)"
)
# Directional qualifiers that may follow a street type ("Finch Avenue West").
_DIRECTION = r"(?:Northbound|Southbound|Eastbound|Westbound|North|South|East|West)"
# Proper-noun run (1–4 capitalized words). No '.' in the class so a token can't
# bridge a sentence boundary (e.g. "Dundas. Police"); road suffixes are matched
# separately, so dropping the dot doesn't hurt "St"/"Ave" detection.
_PROPER = r"[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,3}"
# Plural street types, in either case — "X and Y drives", "X and Y Streets".
_ROAD_SUFFIX_PLURAL = (
    r"(?:Streets|Avenues|Roads|Boulevards|Drives|Lanes|Crescents|Terraces|"
    r"Parkways|Expressways|Trails|Ways|Circles|Squares|Places|Highways|"
    r"Gardens|Gates|streets|avenues|roads|boulevards|drives|lanes|crescents|"
    r"terraces|parkways|expressways|trails|ways|circles|squares|places|"
    r"highways|gardens|gates)"
)

# Named highways/expressways common in the GTA (map shorthand → full phrase).
_NAMED_HIGHWAYS = {
    "qew": "Queen Elizabeth Way",
    "dvp": "Don Valley Parkway",
    "gardiner": "Gardiner Expressway",
    "allen": "Allen Road",
    "401": "Highway 401",
    "400": "Highway 400",
    "404": "Highway 404",
    "427": "Highway 427",
    "407": "Highway 407",
    "403": "Highway 403",
    "410": "Highway 410",
    "409": "Highway 409",
}

# Words that make a "<X> Court" phrase a court, not a street. "Bessie Court"
# is a street; "Supreme Court", "District Court" and "Court of Appeal" are
# not — and they are far more common in news copy.  Any adjective ending in
# -al/-ial (criminal, divisional, municipal, judicial) counts too.
_COURT_QUALIFIERS = frozenset({
    "supreme", "superior", "federal", "district", "county", "provincial",
    "appeal", "appellate", "appeals", "criminal", "family", "small", "claims",
    "ontario", "quebec", "international", "administrative", "tax", "youth",
    "juvenile", "circuit", "divorce", "municipal", "constitutional", "trade",
    "labour", "copyright", "patent", "high", "military", "commercial",
    "settlement", "queen's", "king's", "trial",
})
# Determiners and pronouns: "the Court" is a court, "Bessie Court" is a street.
_ARTICLES = frozenset({
    "the", "a", "an", "this", "that", "these", "those", "its", "his", "her",
    "their", "our", "my", "federal", "state", "provincial",
})

# Titles that never appear in a street name. "Quebec Premier Paul St" is a
# person, not an intersection — and "St" there is Saint, not Street.
_TITLE_WORDS = frozenset({
    "premier", "president", "minister", "senator", "governor", "mayor",
    "judge", "justice", "chancellor", "commissioner", "deputy", "sheriff",
    "lieutenant", "colonel", "sergeant", "inspector", "prosecutor",
    "attorney", "ambassador", "secretary", "treasury", "ministry",
})

# NOTE: these patterns must NOT use a global re.IGNORECASE flag — it would
# defeat the [A-Z] capitalization anchor in _PROPER and swallow trailing
# lowercase words. Case-insensitivity is scoped to keyword tokens via (?i:...).
_RE_HItoken = re.compile(r"\b(?i:Highway|Hwy)\s*-?\s*(\d{2,3})\b")
_RE_NAMED = re.compile(r"\b((?i:QEW|DVP|Gardiner|Allen Road|Don Valley Parkway))\b")
_RE_INTERSECTION = re.compile(
    rf"({_PROPER})\s+(?:and|&|(?i:at))\s+({_PROPER})",
)
# "near Peter Matthews and Alexander Knox drives" — the street type is shared
# by both sides, so each half is a road name on its own.  A context word is
# required: without it, "the Canada and United States highways" would read as
# an intersection.  The type may be lower case here ("... drives"), because in
# that construction it is the common noun ("near X and Y drives").
_RE_INTERSECTION_SHARED = re.compile(
    rf"(?:(?i:near|at|by|beside|intersection of|corner of|junction of|"
    rf"crossroads of|roundabout at))\s+({_PROPER})\s+(?:and|&)\s+({_PROPER})\s+"
    rf"({_ROAD_SUFFIX_PLURAL})\b",
)
_RE_ADDRESS = re.compile(
    rf"\b(\d{{1,5}}\s+{_PROPER}\s+{_ROAD_SUFFIX}(?:\s+{_DIRECTION})?)\b",
)
_RE_ROAD = re.compile(
    rf"\b({_PROPER}\s+{_ROAD_SUFFIX}(?:\s+{_DIRECTION})?)\b",
)
_RE_NEAR = re.compile(rf"\b(?i:near)\s+({_PROPER})")

# "City Hall" — the council chambers.  It is deliberately **not** a curated
# place: there is one in every city (Toronto City Hall, Mississauga City
# Hall), so a curated entry would send every story to the same building.
# It is a *generic* candidate instead — the query is qualified by the story's
# own city ("City Hall, Mississauga, ON, Canada") and the strict 20 km guard
# decides whether that is the right one.  A city named in front of it is kept
# in the query ("Marseille City Hall"), so a foreign city hall is rejected by
# the guard instead of silently becoming the local one.
_CITY_HALL_RE = re.compile(
    r"\b(?:(?P<place>[A-Z][A-Za-z'’]+)\s+)?(?i:city hall)\b")
# Words that can sit in front of "City Hall" without naming a city.
_HALL_PREFIX_STOP = frozenset({
    "the", "at", "in", "new", "old", "our", "every", "this", "that", "a",
})
# A trailing possessive is not part of a place name ("Montreal's").
_POSSESSIVE_RE = re.compile(r"['’]s$")

# A phrase ends in a road type when it matches this.
_RE_ROAD_TAIL = re.compile(
    rf"\b(?:{_ROAD_SUFFIX})(?:\s+{_DIRECTION})?\s*$", re.IGNORECASE)
_RE_ST_ABBR = re.compile(r"\bSt$")
_RE_SAINT_AFTER = re.compile(r"\.\s*[A-Z]")


@dataclass
class LocationCandidate:
    text: str
    kind: str          # address | intersection | highway | road | landmark
    confidence: float  # base confidence for this candidate type
    # The municipality the place itself is in, when known (a curated place).
    # It overrides the story's city for both the query and the cross-city
    # guard — a Brampton mall must not be queried as if it were in Toronto.
    city: str | None = None
    province: str | None = None


def _is_court_phrase(text: str) -> bool:
    """True for "Supreme Court", "District Court", "Court of Appeal" — the
    word "Court" used as an institution, not as a street type."""
    stripped = text.strip()
    if not re.search(r"\b(?:Court|Ct)\b\s*$", stripped, re.IGNORECASE):
        return False
    words = re.findall(r"[A-Za-z'’-]+", stripped)
    if len(words) < 2:
        return False
    prev = words[-2].lower()
    if prev in _COURT_QUALIFIERS or prev in _ARTICLES:
        return True
    # "Divisional Court", "Judicial Review", "Criminal Court" — an adjective
    # ending in -al/-ial is an institution, not a street name.
    return prev.endswith(("al", "ial"))


def _has_title_word(text: str) -> bool:
    """True when the phrase contains an office ("Premier", "Minister")."""
    words = re.findall(r"[A-Za-z'’-]+", text.lower())
    return any(w in _TITLE_WORDS for w in words)


def _followed_by_saint(text: str, end: int) -> bool:
    """True for "Fort St. John" — there "St." is *Saint*, not Street."""
    if not _RE_ST_ABBR.search(text[:end]):
        return False
    return bool(_RE_SAINT_AFTER.match(text[end:end + 4]))


def looks_like_road(text: str) -> bool:
    """True when a phrase plausibly names a street.

    Two ways to qualify: it ends in a road type ("Danforth Avenue"), or it is
    one of the bare street names news copy uses without a type ("Keele and
    Wilson"). Everything else — "George Russell", "British Columbia", "Job
    Creation" — is not a road, and must not become an intersection.
    """
    phrase = text.strip()
    if not phrase:
        return False
    if _is_court_phrase(phrase):
        return False
    if _has_title_word(phrase):
        return False
    tail = _RE_ROAD_TAIL.search(phrase)
    if tail:
        # A street is a *name* plus a type ("Danforth Avenue"). A bare type
        # ("Road & Silverstone Drive") is not a street name.
        if len(phrase.split()) < 2:
            return False
        # "The National Highway Traffic Safety Administration" is an agency.
        head_words = re.findall(r"[A-Za-z'’-]+", phrase[:tail.start()])
        if head_words and head_words[-1].lower() in INSTITUTION_ADJECTIVES:
            return False
        return True
    return is_street_name(phrase)


def _iter_intersections(text: str):
    """Yield the intersection candidates in *text*.

    The regex is deliberately permissive — "Collision at Albion Road and
    Silverstone Drive" matches with the first pair being ("Collision",
    "Albion Road") — so a rejected match must not swallow the good one behind
    it.  On rejection the scan restarts just after the match's start.
    """
    pos = 0
    while True:
        m = _RE_INTERSECTION.search(text, pos)
        if not m:
            return
        a, b = m.group(1).strip(), m.group(2).strip()
        if len(a) <= 40 and len(b) <= 40 and looks_like_road(a) and looks_like_road(b):
            yield a, b
            pos = m.end()
        else:
            pos = m.start() + 1


def _dedup_keep_order(items: list[LocationCandidate]) -> list[LocationCandidate]:
    seen: set[str] = set()
    out: list[LocationCandidate] = []
    for c in items:
        key = c.text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def extract_locations(title: str, body: str | None = None) -> list[LocationCandidate]:
    """Return ordered location candidates (most specific/confident first)."""
    text = f"{title or ''}. {body or ''}".strip()
    if not text:
        return []

    out: list[LocationCandidate] = []

    # 1. Street addresses (most specific)
    for m in _RE_ADDRESS.finditer(text):
        phrase = m.group(1).strip()
        if _followed_by_saint(text, m.end()):
            continue
        if looks_like_road(phrase):
            out.append(LocationCandidate(phrase, "address", 0.9))

    # 2. Intersections ("Keele and Wilson", "Yonge at Bloor").
    #    Both sides must look like roads, or the match is two capitalised
    #    words that happen to sit next to "and" — a name, a company, a
    #    province, a job title.
    for m in _RE_INTERSECTION_SHARED.finditer(text):
        a, b = m.group(1).strip(), m.group(2).strip()
        suffix = m.group(3).strip().capitalize()
        if is_admin_region(a) or is_admin_region(b):
            continue
        phrase = f"{a} & {b} {suffix}"
        if len(a) <= 40 and len(b) <= 40 and not _has_title_word(phrase):
            out.append(LocationCandidate(phrase, "intersection", 0.85))
    for a, b in _iter_intersections(text):
        out.append(LocationCandidate(f"{a} & {b}", "intersection", 0.85))

    # 3. Curated place names — venues, stations, hospitals, neighbourhoods,
    #    malls. These carry the municipality they actually sit in.
    for name, city in find_all_places(text):
        out.append(LocationCandidate(name, "landmark", 0.75, city=city, province="ON"))

    # 4. "City Hall" — generic, qualified by the story's city.
    for m in _CITY_HALL_RE.finditer(text):
        phrase = "City Hall"
        place = (m.group("place") or "").strip()
        if place and place.lower() not in _HALL_PREFIX_STOP:
            # "Montreal's city hall" -> "Montreal": the possessive is not
            # part of the place name.
            place = _POSSESSIVE_RE.sub("", place).strip()
            # A prefix only helps if the geocoder honours it.  Google
            # ignores an unknown one and answers with the *local* city hall
            # ("Berlin City Hall, Toronto, ON, Canada" -> Toronto City Hall),
            # which would pin a foreign story here.  So a prefix is kept only
            # when it names a city we know — then the query names it and the
            # guard measures the distance to it.  Otherwise the candidate is
            # dropped rather than guessed.
            if not detect_city(place):
                continue
            phrase = f"{place} City Hall"
        out.append(LocationCandidate(phrase, "landmark", 0.6))

    # 5. Highways (numbered + named)
    for m in _RE_HItoken.finditer(text):
        out.append(LocationCandidate(f"Highway {m.group(1)}", "highway", 0.6))
    for m in _RE_NAMED.finditer(text):
        key = m.group(1).lower()
        out.append(LocationCandidate(_NAMED_HIGHWAYS.get(key, m.group(1)), "highway", 0.6))

    # 6. Named roads
    for m in _RE_ROAD.finditer(text):
        phrase = m.group(1).strip()
        if _followed_by_saint(text, m.end()):
            continue
        if looks_like_road(phrase):
            out.append(LocationCandidate(phrase, "road", 0.5))

    # 7. "near <Proper Noun>" landmark mentions
    for m in _RE_NEAR.finditer(text):
        phrase = m.group(1).strip()
        if looks_like_road(phrase):
            out.append(LocationCandidate(phrase, "landmark", 0.4))
        else:
            hit = find_place(phrase)
            if hit:
                name, city = hit
                out.append(LocationCandidate(name, "landmark", 0.4, city=city, province="ON"))

    return _dedup_keep_order(out)


@dataclass
class GeocodePlan:
    """A ready-to-run geocoding query and the context it must be judged in."""
    query: str
    confidence: float
    city: str | None       # municipality the query targets
    kind: str
    # The candidate's *own* municipality, when it knows one (a curated place).
    # None for a generic candidate — a street name does not say which city it
    # is in, it inherits the story's.
    place_city: str | None = None


def best_query(
    candidates: list[LocationCandidate],
    *,
    city: str | None = None,
    province: str | None = None,
    country: str | None = "Canada",
) -> GeocodePlan | None:
    """Build the best geocoding query from candidates + source locale.

    Returns a :class:`GeocodePlan` or None when there's nothing to geocode.
    A curated place overrides the story's city, because the place knows which
    municipality it is in.
    """
    if not candidates:
        return None
    top = candidates[0]
    return _plan_for(top, city=city, province=province, country=country)


def _plan_for(
    cand: LocationCandidate,
    *,
    city: str | None,
    province: str | None,
    country: str | None,
) -> GeocodePlan:
    target_city = cand.city or city
    parts = [cand.text]
    if target_city:
        parts.append(target_city)
    target_province = cand.province or province
    if target_province:
        parts.append(target_province)
    if country:
        parts.append(country)
    return GeocodePlan(
        query=", ".join(parts),
        confidence=cand.confidence,
        city=target_city,
        kind=cand.kind,
        place_city=cand.city,
    )


def geocode_plans(
    candidates: list[LocationCandidate],
    *,
    city: str | None = None,
    province: str | None = None,
    country: str | None = "Canada",
    limit: int = 3,
) -> list[GeocodePlan]:
    """One plan per candidate, best first.

    The crawler tries them in order and keeps the first result that survives
    the cross-city guard, so a single bad candidate no longer costs an item
    its position.
    """
    plans: list[GeocodePlan] = []
    seen: set[str] = set()
    for cand in candidates:
        plan = _plan_for(cand, city=city, province=province, country=country)
        if plan.query.lower() in seen:
            continue
        seen.add(plan.query.lower())
        plans.append(plan)
        if len(plans) >= limit:
            break
    return plans


def is_self_locating(plan: GeocodePlan) -> bool:
    """True when the candidate names a place precisely enough to stand alone.

    A street address, an intersection of two roads and a numbered highway all
    say *where*.  A curated place does too — it names its own municipality.
    A bare street name ("Shamrock Drive") does not: there is one in British
    Columbia and one in Toronto, and when the story names no city at all,
    nothing says which one is meant.
    """
    return plan.kind in ("address", "intersection", "highway") or plan.place_city is not None
