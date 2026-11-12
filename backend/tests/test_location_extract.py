"""Unit tests for the location extractor (no DB / network).

The extractor decides whether an item gets a pin, so these tests are mostly
about *precision*: the phrases that used to become pins must not, and the
phrases that name a real place must.

Run from backend/:  pytest tests/test_location_extract.py
"""

from app.services.gta_places import find_place, is_street_name
from app.services.location_extract import (
    best_query,
    extract_locations,
    geocode_plans,
    is_self_locating,
    looks_like_road,
)


def texts(title: str, body: str = "") -> list[str]:
    return [c.text for c in extract_locations(title, body)]


def top(title: str, body: str = ""):
    cands = extract_locations(title, body)
    return cands[0] if cands else None


# ── precision: the phrases that used to become pins ────────────────────────
def test_two_capitalised_words_are_not_an_intersection():
    """The old rule accepted any "Proper and Proper", which turned names,
    companies and job titles into intersections."""
    for phrase in (
        "George Russell & Ferrari dominated the race",
        "Afef Benefif & AbdulMalik Shibli were named",
        "Job Creation & Trade minister Smith spoke",
        "British Columbia & Quebec signed the agreement",
        "Quebec & Nova Scotia will meet Monday",
        "Olivia Chow & Brad Bradford attended",
        "Apple Podcasts & Spotify are available",
        "Black & Indigenous history month",
    ):
        assert not looks_like_road(phrase), phrase
        assert texts(phrase) == [], phrase


def test_a_court_is_not_a_street():
    for phrase in ("Supreme Court", "Divisional Court", "District Court",
                   "Quebec Superior Court", "The Ontario Court", "The Court"):
        assert not looks_like_road(phrase), phrase
    # ...but a street that happens to be called Court still counts.
    assert looks_like_road("Bessie Court")


def test_saint_is_not_street():
    """"Fort St. John" is a city in British Columbia; "St" there is Saint."""
    assert top("Pipes fail in Fort St. John", "") is None


def test_a_person_is_not_a_street():
    assert top("Quebec Premier Paul St-Pierre Plamondon spoke", "") is None


def test_a_bare_city_name_is_not_a_location():
    """A city is not a point — this is what put thousands of items on one pin."""
    assert top("Toronto", "A story about Toronto") is None
    assert top("TORONTO — The mayor spoke on Tuesday", "") is None


def test_an_electoral_ward_is_not_a_place():
    """"Parkdale-High Park" is a ward made of two neighbourhood names."""
    assert top("Ward 4 Parkdale-High Park remains a flashpoint", "") is None
    assert top("Ward 11 University-Rosedale election heats up", "") is None


# ── precision: real intersections survive ──────────────────────────────────
def test_real_intersections_are_found():
    assert "Yonge & Dundas" in texts("Stabbing near Yonge and Dundas")
    assert "College & Welleseley Streets" in texts(
        "Queens Park Crescent closed between College and Welleseley Streets")
    assert "Albion Road & Silverstone Drive" in texts(
        "Collision at Albion Road and Silverstone Drive")


def test_an_intersection_with_a_shared_street_type_is_found():
    """"near Peter Matthews and Alexander Knox drives" — the type is shared."""
    cands = texts("A road worker died near Peter Matthews and Alexander "
                  "Knox drives in Pickering")
    assert "Peter Matthews & Alexander Knox Drives" in cands


def test_a_shared_street_type_needs_a_context_word():
    """"the Canada and United States highways" is not an intersection."""
    assert texts("Traffic is heavy near Canada and United States highways") == []


def test_a_province_pair_is_not_an_intersection():
    assert texts("Quebec and Nova Scotia will meet Monday on trade") == []
    assert texts("British Columbia & Quebec signed the agreement") == []


def test_a_road_with_a_direction_is_found():
    assert "Driftwood Avenue & Finch Avenue West" in texts(
        "Crash on Driftwood Avenue and Finch Avenue West")


def test_a_street_address_wins():
    c = top("New bakery opens at 123 Queen Street West", "")
    assert c.kind == "address"
    assert c.text == "123 Queen Street West"


def test_a_house_number_is_not_an_address():
    """'112th Grey Cup' and '2025 Grey Cup' are not street addresses."""
    assert top("The 112th Grey Cup drew a big crowd", "") is None


# ── recall: curated place names ────────────────────────────────────────────
def test_a_curated_place_is_found():
    c = top("Blue Jays win at Scotiabank Arena", "")
    assert c.text == "Scotiabank Arena"
    assert c.kind == "landmark"
    assert c.city == "Toronto"


def test_a_curated_place_carries_its_own_municipality():
    c = top("Store opens at Upper Canada Mall", "")
    assert c.text == "Upper Canada Mall"
    assert c.city == "Newmarket"


def test_a_station_beats_a_bare_street_name():
    c = top("Service change at Kipling Station", "")
    assert c.text == "Kipling Station"


def test_an_apostrophe_is_optional():
    assert find_place("a quiet day in Queens Park") == ("Queen's Park", "Toronto")
    assert find_place("St Lawrence Market was busy") == ("St Lawrence Market", "Toronto")


def test_curated_places_are_matched_case_insensitively():
    assert find_place("the ROYAL ONTARIO MUSEUM reopens") == (
        "Royal Ontario Museum", "Toronto")


# ── the venues the 2026-11-07 audit of the unplaced corpus added ──────────
def test_audit_venues_are_found():
    """Each of these named a real place in a story that stayed unplaced."""
    assert find_place("Toronto Pearson airport, Seneca Polytechnic form a "
                      "partnership") == ("Toronto Pearson International Airport",
                                         "Toronto")
    assert find_place("guests announced for Toronto's Meridian Hall on Nov. 7") == (
        "Meridian Hall", "Toronto")
    assert find_place("construction was suddenly halted at Sunny View Junior "
                      "Senior Public School") == (
        "Sunny View Junior Senior Public School", "North York")
    assert find_place("detention tanks located under a field in Kew Beach") == (
        "Kew-Balmy Beach", "Toronto")
    assert find_place("the consent of the defendants, the Downsview "
                      "Long-Term Care Centre Limited") == (
        "Downsview Long-Term Care Centre", "North York")
    assert find_place("specialized programming at Pickering High School") == (
        "Pickering High School", "Pickering")
    assert find_place("a public funeral service at Union United Church") == (
        "Union United Church", "Montreal")
    assert find_place("announcing the new venture at the Toronto "
                      "International Film Festival") == (
        "TIFF Bell Lightbox", "Toronto")


def test_an_audit_venue_carries_its_own_municipality():
    """A venue is queried in the municipality it is really in, not downtown."""
    cands = extract_locations("Construction halted at Sunny View Junior "
                              "Senior Public School", "")
    plan = best_query(cands, city="Toronto", province="ON")
    assert plan.query == ("Sunny View Junior Senior Public School, "
                           "North York, ON, Canada")


def test_an_attribution_is_not_a_venue():
    """"CEO of Toronto Pearson" and "TIFF CEO" name an employer, not a place.

    A story that merely mentions a venue is not a story that happened there,
    so these must not become a candidate — otherwise a US prosecution story
    gets pinned at Pearson airport and an honours story at TIFF Bell Lightbox.
    """
    assert top("said Deborah Flint, President and CEO of Toronto Pearson",
               "") is None
    assert top("Among the recipients is TIFF CEO Cameron Bailey", "") is None
    assert top("trespassed at a FedEx facility at Toronto's Pearson airport",
               "") is None


# ── "City Hall" is generic, not a curated place ───────────────────────────
def test_city_hall_is_a_generic_candidate():
    """Every city has one, so it must not be a curated place — it is
    qualified by the story's own city instead."""
    c = top("Crombie will reclaim the top job at City Hall", "")
    assert c.text == "City Hall"
    assert c.kind == "landmark"
    assert c.city is None          # no municipality of its own


def test_city_hall_is_matched_case_insensitively():
    assert "City Hall" in texts(
        "Toronto election 2026: who's in and who's out at city hall")


def test_city_hall_is_qualified_by_the_story_city():
    cands = extract_locations("Will Crombie reclaim the top job at City Hall?",
                              "")
    plan = best_query(cands, city="Mississauga", province="ON")
    assert plan.query == "City Hall, Mississauga, ON, Canada"


def test_city_hall_is_not_self_locating():
    """With no city detected the story's location is unknown, and "City
    Hall" is every city's City Hall — so it must not place the row."""
    cands = extract_locations("protesters forced their way into the lobby of "
                               "City Hall", "")
    plan = best_query(cands, city="Toronto", province="ON")
    assert not is_self_locating(plan)


def test_a_foreign_city_hall_is_not_a_candidate():
    """Google ignores an unknown prefix and answers with the *local* city
    hall ("Berlin City Hall, Toronto, ON, Canada" -> Toronto City Hall), so a
    foreign city hall must not become a candidate at all."""
    assert top("Marseille City Hall was stormed by protesters", "") is None
    assert top("Berlin City Hall was stormed by protesters", "") is None


def test_a_known_city_hall_keeps_its_name():
    assert "Montreal City Hall" in texts(
        "Montreal's city hall is hosting a public viewing")


def test_the_curated_city_hall_wins_over_the_generic_one():
    """"Toronto City Hall" is already curated — it must keep its own
    municipality rather than become a generic candidate."""
    c = top("critics at Toronto City Hall were skeptical of the plan", "")
    assert c.text == "Toronto City Hall"
    assert c.city == "Toronto"


def test_bare_street_names():
    assert is_street_name("Keele")
    assert is_street_name("Wellesley")
    assert not is_street_name("Keele Street")
    assert not is_street_name("Ferrari")


# ── query building ─────────────────────────────────────────────────────────
def test_a_curated_place_overrides_the_story_city():
    """A Brampton mall must not be queried as if it were downtown Toronto."""
    cands = extract_locations("Store opens at Upper Canada Mall", "")
    plan = best_query(cands, city="Toronto", province="ON")
    assert plan.query == "Upper Canada Mall, Newmarket, ON, Canada"
    assert plan.city == "Newmarket"


def test_the_story_city_is_used_when_the_place_does_not_know_it():
    cands = extract_locations("Crash on Dundas Street", "")
    plan = best_query(cands, city="Toronto", province="ON")
    assert plan.query == "Dundas Street, Toronto, ON, Canada"


def test_plans_are_ordered_and_capped():
    cands = extract_locations(
        "Collision at Yonge and Dundas near Union Station",
        "Also at Scotiabank Arena and Bloor Street.")
    plans = geocode_plans(cands, city="Toronto", province="ON", limit=3)
    assert len(plans) <= 3
    assert plans[0].confidence >= plans[-1].confidence


def test_no_candidates_means_no_plan():
    assert best_query([], city="Toronto") is None
    assert geocode_plans([], city="Toronto") == []


# ── the request log must not carry the Maps key ────────────────────────────
def test_httpx_request_urls_are_not_logged():
    """httpx logs the full URL at INFO, and the Google Geocoding URL carries
    the server API key — that wrote a live credential into the logs."""
    from app.core.logging_setup import configure_logging

    configure_logging()
    import logging
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


# ── the whole article is read, not just the headline ───────────────────────
def test_a_venue_deep_in_the_article_is_found():
    body = ("TORONTO — The mayor spoke at length about the budget. " * 20 +
            "The event was held at Scotiabank Arena. " * 3)
    assert "Scotiabank Arena" in texts("Council votes on the budget", body)


def test_the_crawler_reads_the_description_too():
    """A street address or a venue is almost never in the headline."""
    from app.crawler.pipeline import _location_plans

    plans = _location_plans(
        "Council votes on the budget", "TORONTO — The mayor spoke at length.",
        "The ceremony was held at Scotiabank Arena on Saturday.",
        city="Toronto", province="ON")
    assert plans[0].query == "Scotiabank Arena, Toronto, ON, Canada"
    assert plans[0].kind == "landmark"


def test_the_crawler_tries_alternatives_when_the_first_fails():
    from app.crawler.pipeline import _location_plans

    plans = _location_plans(
        "Council votes on the budget", "TORONTO — summary.",
        "The ceremony was held at Scotiabank Arena, near Yonge Street.",
        city="Toronto", province="ON")
    assert len(plans) > 1
    # The most confident candidate comes first.
    assert plans[0].kind == "landmark"
    assert plans[0].confidence >= plans[1].confidence


# ── the guard: is this where the story is? ─────────────────────────────────
def test_the_guard_is_measured_from_the_storys_city():
    """A place that names its own municipality still has to be where the
    story is — a Toronto story is not a London (Ontario) one."""
    from app.crawler.pipeline import _guard_for
    from app.services.location_extract import GeocodePlan

    toronto_place = GeocodePlan("Western University, London, ON, Canada", 0.75,
                                 "London", "landmark", place_city="London")
    center, km = _guard_for(toronto_place, detected=True, story_city="Toronto")
    assert center == (43.6532, -79.3832)
    # A curated place gets the regional allowance, so a neighbouring
    # municipality is still allowed but the other side of the province is not.
    assert km == 60.0
    from app.services.geo_gazetteer import haversine_km
    assert haversine_km(center, (43.4643, -80.5204)) > km


def test_a_generic_candidate_gets_the_strict_guard():
    from app.crawler.pipeline import _guard_for
    from app.services.location_extract import GeocodePlan

    road = GeocodePlan("Danforth Avenue, Toronto, ON, Canada", 0.5, "Toronto", "road")
    _, km = _guard_for(road, detected=True, story_city="Toronto")
    assert km == 20.0
    _, km = _guard_for(road, detected=False, story_city="Toronto")
    assert km == 60.0


def test_a_bare_street_name_cannot_place_a_story_with_no_city():
    """Nothing in the sentence says whether "Shamrock Drive" is the British
    Columbia one or the Toronto one."""
    from app.services.location_extract import GeocodePlan, is_self_locating

    road = GeocodePlan("Shamrock Drive, Toronto, ON, Canada", 0.5, "Toronto", "road")
    assert not is_self_locating(road)

    address = GeocodePlan("9600 Bathurst St, Toronto, ON, Canada", 0.9, "Toronto", "address")
    assert is_self_locating(address)

    intersection = GeocodePlan("College & Wellesley, Toronto, ON, Canada", 0.85,
                               "Toronto", "intersection")
    assert is_self_locating(intersection)

    # A curated place names its own municipality, so it stands on its own.
    curated = GeocodePlan("Scotiabank Arena, Toronto, ON, Canada", 0.75, "Toronto",
                           "landmark", place_city="Toronto")
    assert is_self_locating(curated)
