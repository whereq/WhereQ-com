"""Administrative geography — whereq.cloud's geography feed.

The feed is a **second vocabulary of place**, not a new kind of POI: the
provinces, regions, municipalities, cities, towns, wards and neighbourhoods
that *contain* the places the map already draws, with real, drawable
boundaries.

Two things make it worth its own tables:

* **Boundaries.** ``neighborhoods`` stores a centroid and six scores — the
  "Guides" of the app have never had an outline. These places have one, and
  it is the outline that turns a name into an area on the map.
* **Containment.** A place is in several things at once (a neighbourhood, in
  a ward, in a city, in a province). The feed keeps both vocabularies side by
  side — the OpenStreetMap one and the formal geoBoundaries one — rather than
  merging them, so a card can say which of them a point falls in.

The geometry is stored twice, like the school catchments: ``boundary_geojson``
(JSONB, the raw outline the API serves) and ``geom`` (PostGIS, for the
point-in-polygon and viewport queries). Both are open data — OSM under ODbL
1.0, geoBoundaries under CC-BY 4.0 — so the licence travels with every row
and the UI shows the attribution.
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GeoPlace(Base):
    """One administrative place — a province, a municipality, a ward, ….

    ``uid`` is the feed's own identifier (``osm:r1428125``,
    ``gb:CAN:ADM1:82249235B5553315981608``) and is stable across refreshes,
    so it is the upsert identity.
    """

    __tablename__ = "geo_places"

    uid: Mapped[str] = mapped_column(String(64), primary_key=True)
    # The platform's own concept — "province", "municipality", "ward",
    # "neighbourhood"… — not the source's admin level.
    kind: Mapped[str] = mapped_column(String(24), index=True)
    # How the kind was derived ("place_tag", "admin_level", …).
    kind_source: Mapped[str | None] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(255), index=True)
    # The feed is bilingual: the local name, an English one and a Chinese one.
    name_en: Mapped[str | None] = mapped_column(String(255))
    name_zh: Mapped[str | None] = mapped_column(String(255))
    name_local: Mapped[str | None] = mapped_column(String(255))
    official_name: Mapped[str | None] = mapped_column(String(255))

    # Which vocabulary the row came from: "osm" (crowd-mapped wards,
    # districts, neighbourhoods, cities) or "geoboundaries" (the formal
    # administrative divisions). Both are kept — they overlap on purpose.
    source: Mapped[str] = mapped_column(String(24), index=True)
    source_id: Mapped[str | None] = mapped_column(String(96))
    source_url: Mapped[str | None] = mapped_column(String(512))
    # ODbL 1.0 / CC-BY 4.0 — the attribution the UI owes the source.
    license: Mapped[str | None] = mapped_column(String(160))

    # The source's own vocabulary, kept for provenance.
    raw_admin_level: Mapped[int | None] = mapped_column(Integer)
    raw_place: Mapped[str | None] = mapped_column(String(48))
    raw_boundary: Mapped[str | None] = mapped_column(String(48))

    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    province_code: Mapped[str | None] = mapped_column(String(8))
    iso_code: Mapped[str | None] = mapped_column(String(16))
    ref: Mapped[str | None] = mapped_column(String(48))

    population: Mapped[int | None] = mapped_column(Integer)
    population_date: Mapped[str | None] = mapped_column(String(16))
    wikidata: Mapped[str | None] = mapped_column(String(32))
    wikipedia: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    capital: Mapped[str | None] = mapped_column(String(160))

    centroid_lon: Mapped[float | None] = mapped_column(Float)
    centroid_lat: Mapped[float | None] = mapped_column(Float)
    # The place's own bounding box, from the feed. The viewport filter uses
    # these rather than the geometry, so a place we hold no outline for still
    # belongs in the viewport it sits in.
    bbox_min_lon: Mapped[float | None] = mapped_column(Float)
    bbox_min_lat: Mapped[float | None] = mapped_column(Float)
    bbox_max_lon: Mapped[float | None] = mapped_column(Float)
    bbox_max_lat: Mapped[float | None] = mapped_column(Float)
    area_km2: Mapped[float | None] = mapped_column(Float)

    has_boundary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # The raw outline — a GeoJSON **geometry** (Polygon or MultiPolygon),
    # unwrapped from the API's FeatureCollection. It is what the API serves.
    # ``none_as_null`` so "no outline" is a SQL NULL and not a JSON ``null``:
    # a stored JSON null would read back as a present-but-empty outline.
    boundary_geojson: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    # PostGIS MULTIPOLYGON (WGS84) with a GiST index (created in the
    # migration) for the viewport and point-in-polygon queries.
    geom = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False)
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GeoConcept(Base):
    """One kind of administrative place — the vocabulary, explained.

    The feed ships the concept with a bilingual name and description; the
    counts are ours, computed from what we actually hold.
    """

    __tablename__ = "geo_concepts"

    kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    name_cn: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    description_cn: Mapped[str | None] = mapped_column(Text)
    # Broadest first: 0 = country, 19 = unclassified.
    rank: Mapped[int] = mapped_column(Integer, default=0)
    # The feed's own count (the whole dataset), for reference.
    upstream_places: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GeoSyncState(Base):
    """Crawl bookkeeping for one geography coverage target.

    Mirrors ``fuel_sync_state``: the crawler rotates targets round-robin so a
    single tick never pulls a whole country, and this row remembers when the
    target was last crawled and whether it failed.
    """

    __tablename__ = "geo_sync_state"

    # Stable key derived from the target spec (e.g. "bbox:-80.3,43.6,-79.2,44.2").
    target_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    kind: Mapped[str | None] = mapped_column(String(24))
    source: Mapped[str | None] = mapped_column(String(24))
    country: Mapped[str | None] = mapped_column(String(2))
    bbox: Mapped[str | None] = mapped_column(String(128))

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    place_count: Mapped[int] = mapped_column(Integer, default=0)
    boundary_count: Mapped[int] = mapped_column(Integer, default=0)
    # Set when the last attempt failed; cleared on a successful crawl.
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
