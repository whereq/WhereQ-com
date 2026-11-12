"""Administrative geography — the read shapes for the geo router.

The feed is a second vocabulary of place — provinces, regions, municipalities,
cities, towns, wards, neighbourhoods — with real outlines. These schemas are
what the map layer and the place card read.

Two vocabularies coexist (OpenStreetMap and geoBoundaries) and the two are
**not** merged: every row carries its ``source`` and its ``license``, and the
attribution travels with the data.
"""

from pydantic import BaseModel, ConfigDict, Field


class GeoConceptRead(BaseModel):
    """One kind of administrative place — the vocabulary, explained."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    name: str
    name_cn: str | None = None
    description: str | None = None
    description_cn: str | None = None
    # Broadest first: 0 = country, 19 = unclassified.
    rank: int = 0
    # How many of this kind *we* hold — the ones the app can actually draw.
    places: int = 0
    # The feed's own count for the whole dataset.
    upstream_places: int = 0


class GeoPlaceRead(BaseModel):
    """One administrative place."""

    model_config = ConfigDict(from_attributes=True)

    uid: str
    kind: str
    name: str
    name_en: str | None = None
    name_zh: str | None = None
    name_local: str | None = None
    official_name: str | None = None
    # Which vocabulary: "osm" or "geoboundaries".
    source: str
    source_url: str | None = None
    # ODbL 1.0 / CC-BY 4.0 — the attribution the UI owes the source.
    license: str | None = None
    country_code: str | None = None
    province_code: str | None = None
    population: int | None = None
    area_km2: float | None = None
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    # True when **we** hold the outline — not merely when the feed says one
    # exists. The two can differ: an outline we already fetched is an outline
    # we have, whatever the upstream reports today.
    has_boundary: bool = False


class GeoPlaceDetail(GeoPlaceRead):
    """One administrative place, in full — with its provenance."""

    kind_source: str | None = None
    source_id: str | None = None
    raw_admin_level: int | None = None
    raw_place: str | None = None
    raw_boundary: str | None = None
    iso_code: str | None = None
    ref: str | None = None
    population_date: str | None = None
    wikidata: str | None = None
    wikipedia: str | None = None
    website: str | None = None
    capital: str | None = None
    bbox_min_lon: float | None = None
    bbox_min_lat: float | None = None
    bbox_max_lon: float | None = None
    bbox_max_lat: float | None = None


class GeoBoundaryRead(BaseModel):
    """One place's outline, as GeoJSON."""

    uid: str
    name: str
    kind: str
    source: str
    license: str | None = None
    source_url: str | None = None
    # A GeoJSON geometry (Polygon or MultiPolygon).
    geometry: dict = Field(default_factory=dict)
    # How much the outline was simplified, in metres (0 = full resolution).
    simplified_m: float = 0.0
    # The area of the drawn outline, in square kilometres.
    area_km2: float | None = None
    # Where the place is — the feed's own centroid, not a guess from the
    # outline (a multipolygon's first island is not its middle).
    centroid_lon: float | None = None
    centroid_lat: float | None = None


class GeoBoundaryListRead(BaseModel):
    """The outlines of a viewport — and whether the answer was truncated.

    ``total`` is how many outlines matched; ``truncated`` says whether the
    ``limit`` cut the answer short. A client that draws polygons must be able
    to tell "that is all of them" from "that is the first two hundred", or it
    will silently draw a map with holes in it.
    """

    total: int = 0
    truncated: bool = False
    items: list[GeoBoundaryRead] = []


class GeoAtRead(BaseModel):
    """The containment stack for a point — broadest first."""

    uid: str
    kind: str
    name: str
    source: str
    license: str | None = None
    centroid_lon: float | None = None
    centroid_lat: float | None = None


class GeoAtResponse(BaseModel):
    """Everything that contains a point."""

    lat: float
    lng: float
    # Broadest first: country → province → region → city → ward → neighbourhood.
    places: list[GeoAtRead] = []
