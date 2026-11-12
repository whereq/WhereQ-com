"""Curated names of real places around Toronto (and nearby Ontario cities).

Why this exists
---------------
The crawler only places an item when the text names a **specific** place it can
geocode: a street address, an intersection, a named road, or a venue.  News
prose names those things far more often than a regular expression can
recognise — "Scotiabank Arena", "Kipling Station", "Upper Canada Mall" and
"Sunnybrook Health Sciences Centre" are ordinary words to a pattern matcher
but unambiguous places to a human, and to a geocoder.

This module is that knowledge, kept as **names only** — no coordinates.  The
geocoder already answers ~99.9% of the queries the crawler asks it, so the
curated list only has to supply the *names*; the coordinates still come from
the geocoder and the cross-city guard still decides whether the answer is
plausible.

Every entry carries the **municipality the place is actually in**, so a query
for a Brampton mall is not biased towards a Toronto result, and so the guard
is measured from the right centre.

Matching
--------
Case-insensitively, on word boundaries, longest name first — so "Kipling
Station" wins over a bare "Kipling".  Abbreviations are forgiving: a missing
apostrophe ("Queens Park") or a missing period ("St Lawrence Market") still
matches.
"""

from __future__ import annotations

import re

# ── curated places: canonical name -> municipality it sits in ────────────────
# Everything here is in Ontario; the province is implied by the city.
PLACES: dict[str, str] = {
    # ── downtown landmarks, venues and civic sites ─────────────────────────
    "CN Tower": "Toronto",
    "Rogers Centre": "Toronto",
    "Scotiabank Arena": "Toronto",
    "BMO Field": "Toronto",
    "Exhibition Place": "Toronto",
    "Ontario Place": "Toronto",
    "Woodbine Racetrack": "Toronto",
    "Fort York": "Toronto",
    "Casa Loma": "Toronto",
    "Royal Ontario Museum": "Toronto",
    "National Ballet School": "Toronto",
    "Humber River Hospital": "Toronto",
    "Art Gallery of Ontario": "Toronto",
    "TIFF Bell Lightbox": "Toronto",
    "St Lawrence Market": "Toronto",
    "Kensington Market": "Toronto",
    "Distillery District": "Toronto",
    "CF Toronto Eaton Centre": "Toronto",
    "Brookfield Place": "Toronto",
    "WaterPark Place": "Toronto",
    "Scotiabank Theatre": "Toronto",
    "Nathan Phillips Square": "Toronto",
    "Yonge-Dundas Square": "Toronto",
    "Union Station": "Toronto",
    "Toronto City Hall": "Toronto",
    "MaRS Discovery District": "Toronto",
    "Ontario Science Centre": "Toronto",
    "Fort York National Historic Site": "Toronto",
    "Aura at College Park": "Toronto",
    "Village at Bay Adelaide": "Toronto",
    "Air Canada Centre": "Toronto",
    "Sobeys Stadium": "Toronto",
    "Varsity Stadium": "Toronto",
    "Lamport Stadium": "Toronto",
    "Varsity Bowl": "Toronto",
    "Bloor Arena": "Toronto",
    "Ted Reeve Arena": "Toronto",
    "Scotiabank Pond": "Toronto",
    "Ford Performance Centre": "Toronto",
    "Toronto Public Library": "Toronto",
    "Toronto Eaton Centre": "Toronto",

    # ── parks, waterfront and green space ─────────────────────────────────
    "High Park": "Toronto",
    "Trinity Bellwoods Park": "Toronto",
    "Allan Gardens": "Toronto",
    "College Park": "Toronto",
    "Queen's Park": "Toronto",
    "Canoe Landing Park": "Toronto",
    "Tommy Thompson Park": "Toronto",
    "Trillium Park": "Toronto",
    "Withrow Park": "Toronto",
    "Berczy Park": "Toronto",
    "Kalair Family Park": "Brampton",
    "Corktown Common": "Toronto",
    "Garrison Common": "Toronto",
    "Millennium Park": "Toronto",
    "Colonel Samuel Smith Park": "Toronto",
    "Edwards Gardens": "Toronto",
    "Woodbine Park": "Toronto",
    "Evergreen Brick Works": "Toronto",
    "Moss Park": "Toronto",
    "Riverdale Park": "Toronto",
    "Taylor Creek Park": "Toronto",
    "Tom Thomson Park": "Toronto",
    "Humber Bay Park": "Toronto",
    "Etobicoke Creek Park": "Toronto",
    "Scarborough Bluffs": "Toronto",
    "Sunnyside Park": "Toronto",
    "Cherry Beach": "Toronto",
    "Centre Island": "Toronto",
    "Ward's Island": "Toronto",
    "Hanlan's Point": "Toronto",
    "Bluffer's Park": "Toronto",
    "Glenwood Hills": "Toronto",
    "Downsview Park": "Toronto",
    "Canadian National Exhibition": "Toronto",

    # ── hospitals and health institutions ───────────────────────────────────
    "Sunnybrook Health Sciences Centre": "Toronto",
    "University Health Network": "Toronto",
    "Mount Sinai Hospital": "Toronto",
    "SickKids": "Toronto",
    "Hospital for Sick Children": "Toronto",
    "St Michael's Hospital": "Toronto",
    "Women's College Hospital": "Toronto",
    "Toronto Rehabilitation Institute": "Toronto",
    "Princess Margaret Cancer Centre": "Toronto",
    "Michael Garron Hospital": "Toronto",
    "Baycrest Hospital": "Toronto",
    "Schwartz Reisman Institute": "Toronto",

    # ── schools ────────────────────────────────────────────────────────────
    "University of Toronto": "Toronto",
    "University of Toronto Mississauga": "Mississauga",
    "University of Toronto Scarborough": "Scarborough",
    "York University": "Toronto",
    "Toronto Metropolitan University": "Toronto",
    "Humber College": "Toronto",
    "George Brown College": "Toronto",
    "Centennial College": "Toronto",
    "Seneca College": "Toronto",
    "Etobicoke School of the Arts": "Toronto",
    "University of Toronto Schools": "Toronto",
    "St Michael's College School": "Toronto",
    "Harbord Collegiate": "Toronto",
    "Marc Garneau Collegiate Institute": "Toronto",
    "Jarvis Collegiate Institute": "Toronto",
    "Parkdale Collegiate Institute": "Toronto",
    "Danforth Collegiate and Technical Institute": "Toronto",
    "Earl Haig Secondary School": "Toronto",

    # ── Toronto neighbourhoods ─────────────────────────────────────────────
    "The Annex": "Toronto",
    "Leslieville": "Toronto",
    "Yorkville": "Toronto",
    "Roncesvalles": "Toronto",
    "Little Italy": "Toronto",
    "Greektown": "Toronto",
    "Liberty Village": "Toronto",
    "King West": "Toronto",
    "Queen West": "Toronto",
    "Harbourfront": "Toronto",
    "Financial District": "Toronto",
    "Entertainment District": "Toronto",
    "Forest Hill": "Toronto",
    "Rosedale": "Toronto",
    "Riverdale": "Toronto",
    "Corktown": "Toronto",
    "Parkdale": "Toronto",
    "Junction Triangle": "Toronto",
    "Davisville": "Toronto",
    "Willowdale": "Toronto",
    "Don Mills": "Toronto",
    "York Mills": "Toronto",
    "Agincourt": "Toronto",
    "Birchcliffe": "Toronto",
    "Clairlea": "Toronto",
    "Mimico": "Toronto",
    "Humber Summit": "Toronto",
    "Rexdale": "Toronto",
    "West Hill": "Toronto",
    "Highland Creek": "Toronto",
    "Guildwood": "Scarborough",
    "Woburn": "Toronto",
    "Dorset Park": "Toronto",
    "Centennial Park": "Toronto",
    "Morningside": "Toronto",
    "Oakwood Village": "Toronto",
    "Cabbagetown": "Toronto",
    "Little Portugal": "Toronto",
    "The Beaches": "Toronto",
    "Long Branch": "Toronto",
    "South Bloor": "Toronto",

    # ── TTC subway stations ────────────────────────────────────────────────
    "Bloor Station": "Toronto",
    "Bloor-Yonge Station": "Toronto",
    "Yonge-Bloor Station": "Toronto",
    "Spadina Station": "Toronto",
    "St George Station": "Toronto",
    "Museum Station": "Toronto",
    "Queen's Park Station": "Toronto",
    "St Andrew Station": "Toronto",
    "Osgoode Station": "Toronto",
    "St Patrick Station": "Toronto",
    "Dundas West Station": "Toronto",
    "Dundas East Station": "Toronto",
    "Queen West Station": "Toronto",
    "King West Station": "Toronto",
    "Bay West Station": "Toronto",
    "Dufferin Station": "Toronto",
    "Lansdowne Station": "Toronto",
    "Keele Station": "Toronto",
    "High Park Station": "Toronto",
    "Ossington Station": "Toronto",
    "Christie Station": "Toronto",
    "Bathurst Station": "Toronto",
    "St Clair West Station": "Toronto",
    "Eglinton West Station": "Toronto",
    "Glencairn Station": "Toronto",
    "Lawrence West Station": "Toronto",
    "Yorkdale Station": "Toronto",
    "Sheppard-Yonge Station": "Toronto",
    "North York Centre Station": "Toronto",
    "York Mills Station": "Toronto",
    "Sheppard West Station": "Toronto",
    "Downsview Station": "Toronto",
    "Finch West Station": "Toronto",
    "Mount Dennis Station": "Toronto",
    "Highway 407 Station": "Toronto",
    "Vaughan Metropolitan Centre Station": "Toronto",
    "Wilson Station": "Toronto",
    "Old Mill Station": "Toronto",
    "Jane and Finch Station": "Toronto",
    "Kipling Station": "Toronto",
    "Islington Station": "Toronto",
    "Royal York Station": "Toronto",
    "Eglinton Station": "Toronto",
    "Davisville Station": "Toronto",
    "St Clair Station": "Toronto",
    "Gordon Baker Station": "Toronto",
    "Broadview Station": "Toronto",
    "Chester Station": "Toronto",
    "Pape Station": "Toronto",
    "Don Mills Station": "Toronto",
    "Ellesmere Station": "Toronto",
    "Victoria Park Station": "Toronto",
    "Warden Station": "Toronto",
    "Science Centre Station": "Toronto",
    "Exhibition Station": "Toronto",
    "Kennedy Station": "Toronto",
    "Guildwood Station": "Scarborough",
    "Viscount Station": "Toronto",
    "McCowan Station": "Toronto",
    "Scarborough Centre Station": "Toronto",

    # ── neighbouring municipalities ────────────────────────────────────────
    "Square One": "Mississauga",
    "Celebration Square": "Mississauga",
    "Mississauga Civic Centre": "Mississauga",
    "Paramount Theatre": "Mississauga",
    "Living Arts Centre": "Mississauga",
    "Mississauga Memorial Arena": "Mississauga",
    "Erin Meadows Community Centre": "Mississauga",
    "Meadowvale Community Centre": "Mississauga",
    "Port Credit": "Mississauga",
    "Sherway Gardens": "Mississauga",
    "Cloverdale Mall": "Mississauga",
    "Woodbine Centre": "Mississauga",
    "Westgate Shopping Centre": "Etobicoke",
    "Town Centre": "Etobicoke",
    "Islington City Centre": "Etobicoke",
    "Upper Canada Mall": "Newmarket",
    "Newmarket Theatre": "Newmarket",
    "Markham Mall": "Markham",
    "Reignwood Centre": "Markham",
    "Markham Fair": "Markham",
    "Vaughan Mills": "Vaughan",
    "SmartCentres": "Vaughan",
    "Multifunational Centre": "Vaughan",
    "Vaughan Municipal Centre": "Vaughan",
    "Bramalea City Centre": "Brampton",
    "Brampton City Centre": "Brampton",
    "Heart City Centre": "Brampton",
    "CAA Centre": "Brampton",
    "Memorial Arena": "Brampton",
    "Constitution Recreation Centre": "Brampton",
    "Brampton Soccer Centre": "Brampton",
    "Richmond Hill Centre": "Richmond Hill",
    "Oakville Town Centre": "Oakville",
    "Bronte Creek": "Oakville",
    "Oakville Civic Centre": "Oakville",
    "Oakville Public Library": "Oakville",
    "Aurora Arena": "Aurora",
    "Keswick": "Georgina",
    "Newmarket Arena": "Newmarket",
    "Sports Centre": "Pickering",
    "Pickering Recreation Complex": "Pickering",
    "The Rose": "Brampton",

    # ── nearby Ontario cities ─────────────────────────────────────────────
    "Ottawa Convention Centre": "Ottawa",
    "TD Place Arena": "Ottawa",
    "Parliament Hill": "Ottawa",
    "ByWard Market": "Ottawa",
    "Shaw Centre": "Ottawa",
    "National Arts Centre": "Ottawa",
    "Canadian War Museum": "Ottawa",
    "University of Ottawa": "Ottawa",
    "Carleton University": "Ottawa",
    "Guelph City Hall": "Guelph",
    "Guelph Centre": "Guelph",
    "Grange Hill Arena": "Guelph",
    "University of Guelph": "Guelph",
    "Guelph General Hospital": "Guelph",
    "Speed River": "Guelph",
    "Tim Hortons Field": "Hamilton",
    "Copps Coliseum": "Hamilton",
    "Hamilton City Hall": "Hamilton",
    "Durand Building": "Hamilton",
    "Hamilton Health Sciences": "Hamilton",
    "McMaster University": "Hamilton",
    "FirstOntario Centre": "Hamilton",
    "Mattamy Athletic Centre": "Hamilton",
    "Budweiser Gardens": "London",
    "Budweiser Gardens Arena": "London",
    "London Health Sciences Centre": "London",
    "Western University": "London",
    "Kitchener Memorial Auditorium": "Kitchener",
    "Waterloo Memorial Recreation Complex": "Waterloo",
    "Meridian Centre": "St. Catharines",
    "Slush Puppie Place": "Kingston",
    "Rogers K-Rock Centre": "Kingston",
    "Quinte Sports & Wellness Centre": "Belleville",
    "Canada's Wonderland": "Vaughan",
}

# ── venues found by the 2026-11-07 audit of the unplaced corpus ───────────
# Every name here was named in a story that stayed unplaced because the
# extractor had never heard of it, and every one of them was resolved by the
# production geocoder and checked with ``--check-places`` (the name resolves
# inside the municipality claimed here).  The full audit is in
# ``docs/UNPLACED_AUDIT.md``.
PLACES.update({
    "Toronto Pearson International Airport": "Toronto",
    "Meridian Hall": "Toronto",
    "Kew-Balmy Beach": "Toronto",
    "Sunny View Junior Senior Public School": "North York",
    "Downsview Long-Term Care Centre": "North York",
    "Pickering High School": "Pickering",
    "Union United Church": "Montreal",
})

# ── alternative spellings -> canonical name in PLACES ───────────────────────
ALIASES: dict[str, str] = {
    "U of T Mississauga": "University of Toronto Mississauga",
    "St. Lawrence Market": "St Lawrence Market",
    "St. Michael's Hospital": "St Michael's Hospital",
    "St. Clair Station": "St Clair Station",
    "St. Clair West Station": "St Clair West Station",
    "St. George Station": "St George Station",
    "St. Andrew Station": "St Andrew Station",
    "St. Patrick Station": "St Patrick Station",
    "Queens Park": "Queen's Park",
    "Queens Park Crescent": "Queen's Park",
    "Sick Kids": "SickKids",
    "CF Eaton Centre": "CF Toronto Eaton Centre",
    "Eaton Centre": "CF Toronto Eaton Centre",
    "SkyDome": "Rogers Centre",
    "Air Canada Centre": "Rogers Centre",
    "Bmo Field": "BMO Field",
    "Square One Shopping Centre": "Square One",
    "Ontario Science Centre": "Ontario Science Centre",
    "University Health Network": "University Health Network",
    "Scotia Plaza": "Brookfield Place",
    "First Canadian Place": "Brookfield Place",
    "Sun Life Centre": "Union Station",
    "Rogers Centre": "Rogers Centre",
    "Vaughan Civic Centre": "Vaughan Municipal Centre",
    "Mississauga Living Arts Centre": "Living Arts Centre",
    "Meridian Centre": "Meridian Centre",
    "Yonge Dundas Square": "Yonge-Dundas Square",
    "Yonge-Dundas Square": "Yonge-Dundas Square",
    "Toshiba Centre": "Halton Arena",
    "Mattamy Athletic Centre": "Mattamy Athletic Centre",
    "Canada's Wonderland": "Canada's Wonderland",
    "Walmart Centre": "Vaughan Mills",
    "CF Shops at Vaughan": "SmartCentres",
    "Vaughan Mills": "Vaughan Mills",
    "Markham Public Library": "Markham Mall",
    "Richmond Hill Centre": "Richmond Hill Centre",
    "Scarborough Town Centre": "Scarborough Town Centre",
    "Malvern Town Centre": "Malvern Town Centre",
    "Promenade Mall": "Square One",
    "Kipling GO Station": "Kipling Station",
    "Union GO Station": "Union Station",
    "Bloor GO Station": "Bloor Station",
    # The airport is written several ways in the copy.  Only the full phrase
    # is an alias: a bare "Toronto Pearson" is an *attribution* ("President and
    # CEO of Toronto Pearson") and "Toronto's Pearson airport" is a place a
    # story merely mentions — neither is where the story happened.
    "Toronto Pearson airport": "Toronto Pearson International Airport",
    # The beach is a neighbourhood, not a street.
    "Kew Beach": "Kew-Balmy Beach",
    # The festival is held at TIFF Bell Lightbox, but nobody writes it that
    # way.  A bare "TIFF" is not an alias: "TIFF CEO Cameron Bailey" is a
    # person's employer, not the place the story happened.
    "Toronto International Film Festival": "TIFF Bell Lightbox",
}

# Places that live outside the GTA but are still named in GTA-area copy.
PLACES.update({
    "Scarborough Town Centre": "Scarborough",
    "Malvern Town Centre": "Scarborough",
    "Scarborough Community Centre": "Scarborough",
    "Halton Arena": "Oakville",
})

# ── administrative areas that must NOT become a point ───────────────────────
# Toronto's municipal wards and the provincial/federal ridings are *areas*,
# not places.  Their names are built from real neighbourhood names ("Parkdale
# - High Park", "University-Rosedale"), so without this the extractor happily
# pins a council-race story in the middle of a neighbourhood.
BLOCKED_NAMES: tuple[str, ...] = (
    # Toronto wards
    "University Rosedale", "Parkdale High Park", "Scarborough Centre Don Valley East",
    "Scarborough Guildwood", "Scarborough North", "Scarborough Agincourt",
    "Etobicoke Centre", "Etobicoke Lakeshore", "Etobicoke North",
    "York South Weston", "York Centre", "Humber River Black Creek",
    "Davenport Spadina", "Toronto Centre", "Toronto St Lawrence",
    "Don Valley West", "Beaches East York", "Trinity Spadina",
    "Willowdale Broadview", "Mount Pleasant Toronto Centre",
    "Bayview Village Steeles", "Hillcrest Village", "Newtonbrook West",
    "Willowdale West",
    # provincial and federal ridings named in GTA copy
    "University Rosedale Ward", "York Centre Ward", "Scarborough Centre Ward",
)

# Administrative divisions: provinces, states and countries.  These are
# *areas*, not places — "British Columbia & Quebec" is not an intersection,
# and neither is "near the Canada and United States highways".
ADMIN_REGIONS: frozenset[str] = frozenset({
    # Canadian provinces and territories
    "alberta", "british columbia", "manitoba", "new brunswick",
    "newfoundland and labrador", "nova scotia", "ontario",
    "prince edward island", "quebec", "saskatchewan",
    "northwest territories", "nunavut", "yukon",
    # US states
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    # countries and major regions
    "canada", "united states", "mexico", "france", "germany", "italy",
    "spain", "portugal", "ukraine", "russia", "china", "japan", "india",
    "israel", "iran", "iraq", "egypt", "nigeria", "kenya", "south africa",
    "brazil", "argentina", "australia", "new zealand", "south korea",
    "north korea", "vietnam", "philippines", "indonesia", "turkey",
    "greece", "sweden", "norway", "denmark", "finland", "poland",
    "netherlands", "belgium", "austria", "switzerland", "ireland",
    "scotland", "wales", "england", "caribbean", "puerto rico",
})


def is_admin_region(text: str) -> bool:
    """True when the phrase names an administrative division, not a place."""
    norm = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    return norm in ADMIN_REGIONS


# ── bare street names ───────────────────────────────────────────────────────
# Toronto-area streets that news copy routinely names *without* a type
# suffix ("Keele and Wilson", "College and Wellesley").  They are only used
# to qualify an intersection — never on their own, because a bare word like
# "College" or "Queen" is far too ambiguous to geocode by itself.
#
# Words that are also ordinary English or titles (King, Queen, Bay, Navy,
# University, Credit) are deliberately absent: "the King and Queen" is not an
# intersection, and "College and University" is not one either.
STREET_NAMES: frozenset[str] = frozenset({
    "Yonge", "Bloor", "Dundas", "Bathurst", "Keele", "Wilson",
    "Kipling", "Leslie", "Kennedy", "Spadina", "College", "Danforth",
    "Dufferin", "Eglinton", "Wellesley", "Adelaide", "Front",
    "Parliament", "McCowan", "Warden", "Woodbine",
    "Jane", "Albion", "Davenport", "Harbord", "Lippincott", "Palmerston",
    "Clinton", "Crawford", "Ossington", "Lansdowne", "Islington",
    "Royal York", "Weston", "Finch", "Sheppard", "Steeles", "Bovaird",
    "Rutherford", "Dixie", "Hurontario", "Lake Shore",
    "St Clair", "Lawrence", "Gerrard", "Dovercourt",
    "Sherbourne", "Jarvis", "Sumach", "Church", "Maitland", "Gloucester",
    "Mimico", "Renfrew", "Carlaw", "Booth",
    "Bleecker", "Coxwell", "Greenwood",
})

# Words that turn a "<X> Road" phrase into an institution rather than a
# street: "The National Highway Traffic Safety Administration" is an agency,
# not a highway.
INSTITUTION_ADJECTIVES: frozenset[str] = frozenset({
    "national", "federal", "provincial", "state", "united", "interstate",
    "international", "royal", "imperial", "global", "public", "private",
    "municipal", "trans", "county",
})

# Administrative context: a place name right after "Ward 18", "the riding of",
# "electoral district" names an *area*, not a point.
_ADMIN_CONTEXT_RE = re.compile(
    r"\b(?:ward|riding|electoral|constituency|district|division|bureau|"
    r"constituent|census|riding of)\b[^.;:]{0,40}$",
    re.IGNORECASE,
)


def _alias_regex(name: str) -> str:
    """Build a forgiving match pattern for a place name.

    A missing period ("St Lawrence Market" vs "St. Lawrence Market") and a
    missing apostrophe ("Queens Park" vs "Queen's Park") must still match, so
    the punctuation is optional and whitespace is flexible.
    """
    pattern = re.escape(name)
    pattern = re.sub(r"\\\.", r"\\.?", pattern)          # "St\." -> "St\.?"
    pattern = re.sub(r"\\'", r"'?", pattern)            # "Queen\'s" -> "Queen'?s"
    pattern = pattern.replace(r"\ ", r"[\s\-]+")        # "Foo Bar" -> "Foo[\s\-]+Bar"
    return pattern


def _compile(names: list[str]) -> re.Pattern[str]:
    # Longest first so the most specific name wins the match.
    ordered = sorted(set(names), key=lambda n: (-len(n), n))
    return re.compile(
        r"(?<![A-Za-z0-9])(?:" + "|".join(_alias_regex(n) for n in ordered) + r")(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


# alias -> (canonical name, municipality)
_ALL: dict[str, tuple[str, str]] = {}
for _name, _city in PLACES.items():
    _ALL[_name] = (_name, _city)
for _alias, _canon in ALIASES.items():
    if _canon in PLACES:
        _ALL[_alias] = (_canon, PLACES[_canon])

PLACE_RE = _compile(list(_ALL))
STREET_RE = _compile(list(STREET_NAMES))
BLOCK_RE = _compile(list(BLOCKED_NAMES))


def _norm(text: str) -> str:
    """Fold a matched name to a comparable key.

    The regex is forgiving — "St. Lawrence Market", "St Lawrence Market" and
    "Queens Park" all match the same entry — so the lookup key has to be
    folded the same way: punctuation and spacing removed, lower-cased.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# Lower-cased, punctuation-free index so a forgiving match finds its entry.
_ALL_LOWER: dict[str, tuple[str, str]] = {_norm(k): v for k, v in _ALL.items()}


def _blocked_spans(text: str) -> list[tuple[int, int]]:
    """Character spans covered by an administrative-area name."""
    return [(m.start(), m.end()) for m in BLOCK_RE.finditer(text)]


def _is_hyphen_compound(text: str, start: int, end: int) -> bool:
    """True when the match sits inside a hyphenated compound.

    "Parkdale-High Park" is a ward, not the neighbourhoods "Parkdale" and
    "High Park" — so a match touching a hyphen is part of a compound proper
    name and must not become a point.
    """
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return before == "-" or after == "-"


def _is_administrative(text: str, start: int) -> bool:
    """True when the match names an area rather than a place.

    "Ward 18 Willowdale" and "the north Toronto riding of Willowdale" are
    electoral areas; the neighbourhood name inside them is not where
    something happened.
    """
    return _ADMIN_CONTEXT_RE.search(text[max(0, start - 60):start]) is not None


def find_place(text: str) -> tuple[str, str] | None:
    """Return ``(canonical name, municipality)`` for a curated place in *text*.

    Longest name wins, so "Kipling Station" is preferred over a bare
    "Kipling".  Returns None when the text names no curated place.
    """
    if not text:
        return None
    m = PLACE_RE.search(text)
    if not m:
        return None
    if _is_hyphen_compound(text, m.start(), m.end()):
        return None
    if _is_administrative(text, m.start()):
        return None
    return _ALL_LOWER.get(_norm(m.group(0)))


def find_all_places(text: str) -> list[tuple[str, str]]:
    """Every curated place named in *text*, in order of appearance."""
    if not text:
        return []
    blocked = _blocked_spans(text)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in PLACE_RE.finditer(text):
        if _is_hyphen_compound(text, m.start(), m.end()):
            continue
        if _is_administrative(text, m.start()):
            continue
        if any(s < m.end() and m.start() < e for s, e in blocked):
            continue
        hit = _ALL_LOWER.get(_norm(m.group(0)))
        if hit and hit[0] not in seen:
            seen.add(hit[0])
            out.append(hit)
    return out


def is_street_name(text: str) -> bool:
    """True when *text* is exactly one of the bare street names."""
    if not text:
        return False
    return STREET_RE.fullmatch(text.strip()) is not None
