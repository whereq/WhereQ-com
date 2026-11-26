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
from app.services.fuel_stations import FUEL_CATEGORY, FUEL_SOURCE

#: Rows within this radius count as the same station. Measured in metres — the
#: geography cast is what makes ST_DWithin's third argument metres (on a 4326
#: *geometry* it would be degrees).
#:
#: The number is measured, not guessed. Comparing the 899 OSM fuel POIs against
#: the 1,878 live priced stations in the same box (PROD, 2026-11-25, the exact
#: production predicate ``ST_DWithin(::geography, …, 150)``): the distance to
#: the nearest priced station is **p50 = 3.7 m, p95 = 43.3 m** — the two feeds
#: are the same stations, positioned within a few metres of each other.
#: 828 of the 863 matched pairs are inside **50 m**; above that the pairs thin
#: out (19 in 50–100 m, 8 in 100–150 m, 5 in 150–200 m, 0 in 200–250 m).
#: So 150 m sits in the sparse band above every real match and below the
#: "two different stations" distance — 50 m would under-dedup ~37 pairs, and
#: 300 m would merge pairs that are 312–332 m apart, which are *not* the same
#: station (they are commercial cardlock sites and Flying J truck stops).
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


async def shadowed_by_stations(db, points: list[tuple[float, float]]) -> set[int]:
    """Ids of the OSM fuel POIs covered by the given **station positions**.

    This is the same rule as :func:`shadowed_stations`, for the case where
    the stations are not in this app's database — they are read live from
    whereq.cloud. The join cannot be a join any more, so the candidates are
    fetched by a box around the positions and the 150 m test is done here.

    There are only a few hundred OSM fuel POIs in the whole province, so the
    candidate set is small and the Python-side test is cheap.
    """
    if not points:
        return set()
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]
    envelope = func.ST_MakeEnvelope(
        min(lngs) - DEDUP_EXPAND_DEG, min(lats) - DEDUP_EXPAND_DEG,
        max(lngs) + DEDUP_EXPAND_DEG, max(lats) + DEDUP_EXPAND_DEG, 4326)
    rows = (await db.execute(
        select(Place.id, Place.longitude, Place.latitude).where(
            Place.source == "osm",
            Place.kind == "poi",
            Place.category == "fuel",
            Place.geom.is_not(None),
            func.ST_Intersects(Place.geom, envelope),
        )
    )).all()

    shadowed: set[int] = set()
    for place_id, lng, lat in rows:
        if lng is None or lat is None:
            continue
        for slng, slat in points:
            if _metres_apart(lng, lat, slng, slat) <= DEDUP_M:
                shadowed.add(place_id)
                break
    return shadowed


def _metres_apart(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """Great-circle distance in metres between two points."""
    import math

    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
