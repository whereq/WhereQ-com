"""De-duplication of the two fuel feeds for the same physical station.

OSM and whereq.cloud both carry the same gas stations, ~100 m apart. The map
serves one "Fuel" category, so the OSM row is dropped whenever a priced
whereq.cloud station already covers it — the priced row wins, because it
carries the live price and the brand.

Shared by the places map endpoint and the nearby search so both show a station
exactly once.
"""

from geoalchemy2 import Geography
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from app.models.place import Place
from app.crawler.upstream.fuel_stations import FUEL_CATEGORY, FUEL_SOURCE

#: Rows within this radius count as the same station. Measured in metres — the
#: geography cast is what makes ST_DWithin's third argument metres (on a 4326
#: *geometry* it would be degrees).
DEDUP_M = 150

#: The bbox pre-filter for the join below: generous enough to never drop a true
#: match (150 m is ~0.0019° of longitude at 44°N, ~0.0038° at 70°N) and still
#: index-friendly — it is what lets the GiST index on `places.geom` do the work.
DEDUP_EXPAND_DEG = 0.005


def shadowed_stations(envelope=None):
    """Ids of the OSM fuel POIs that a whereq.cloud station already covers.

    The join is driven by the priced rows inside the viewport and probes the
    GiST index on ``places.geom`` — the whole set is computed once per request
    (a CTE), not per candidate row. ``envelope`` is an optional PostGIS
    geometry that bounds the priced side of the join.
    """
    osm = aliased(Place)
    priced = aliased(Place)
    q = (
        select(func.distinct(osm.id))
        .join(priced, and_(
            priced.geom.op("&&")(func.ST_Expand(osm.geom, DEDUP_EXPAND_DEG)),
            func.ST_DWithin(priced.geom.cast(Geography), osm.geom.cast(Geography), DEDUP_M),
        ))
        .where(
            osm.source == "osm",
            osm.kind == "poi",
            osm.category == "fuel",
            priced.source == FUEL_SOURCE,
            priced.kind == "poi",
            priced.category == FUEL_CATEGORY,
        )
    )
    if envelope is not None:
        q = q.where(priced.geom.op("&&")(envelope))
    return q
