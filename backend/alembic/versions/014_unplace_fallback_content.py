"""Unplace the content that was pinned to a city centre instead of a location.

The crawler used to drop a pin at the detected city centre for every item it
could not geocode, so the item would still appear on the map. A pin there
claims a specific place the item is not at: 3,395 of the 6,333 geolocated
rows sat on Toronto's default centre, and the map showed a dense cluster of
news at a point where none of it happened.

Those items are unplaced instead — no latitude, no longitude, no geometry.
The city stays on the row, so the item is still known to be about that city
and stays searchable; it just no longer claims to be somewhere it is not.

The pin at the city centre is what the *map* used to show, so every read path
that filters on ``geom IS NOT NULL`` (the map viewport, the taxonomy counts,
the nearby search) drops these rows consistently — nothing needs a filter of
its own.

Revision ID: 014_unplace_fallback_content
Revises: 013_user_settings
Create Date: 2026-11-06
"""
from alembic import op

revision = "014_unplace_fallback_content"
down_revision = "013_user_settings"
branch_labels = None
depends_on = None

# The city centres the crawler would have used, so the downgrade can put the
# pins back exactly where they were (app/services/geo_gazetteer.py).
_CITY_CENTROIDS = """
        ('Toronto', 43.6532, -79.3832),
        ('Scarborough', 43.7731, -79.2578),
        ('North York', 43.7615, -79.4111),
        ('Etobicoke', 43.6205, -79.5132),
        ('East York', 43.6906, -79.3279),
        ('York', 43.6896, -79.4783),
        ('Markham', 43.8561, -79.337),
        ('Vaughan', 43.8361, -79.4983),
        ('Richmond Hill', 43.8828, -79.4403),
        ('Newmarket', 44.0592, -79.4613),
        ('Aurora', 44.0065, -79.4504),
        ('King City', 43.927, -79.5288),
        ('Whitchurch-Stouffville', 43.971, -79.2441),
        ('Stouffville', 43.971, -79.2441),
        ('Georgina', 44.296, -79.429),
        ('Mississauga', 43.589, -79.6441),
        ('Brampton', 43.7315, -79.7624),
        ('Caledon', 43.8668, -79.8662),
        ('Pickering', 43.8384, -79.0868),
        ('Ajax', 43.8509, -79.0204),
        ('Whitby', 43.8975, -78.9428),
        ('Oshawa', 43.8971, -78.8658),
        ('Clarington', 43.9351, -78.6058),
        ('Bowmanville', 43.9123, -78.6882),
        ('Uxbridge', 44.109, -79.119),
        ('Oakville', 43.4675, -79.6877),
        ('Burlington', 43.3255, -79.799),
        ('Milton', 43.5183, -79.8774),
        ('Halton Hills', 43.6303, -79.9426),
        ('Hamilton', 43.2557, -79.8711),
        ('Ottawa', 45.4215, -75.6972),
        ('London', 42.9849, -81.2453),
        ('Kitchener', 43.4516, -80.4925),
        ('Waterloo', 43.4643, -80.5204),
        ('Cambridge', 43.3601, -80.3127),
        ('Guelph', 43.5448, -80.2482),
        ('Barrie', 44.3894, -79.6903),
        ('Kingston', 44.2312, -76.486),
        ('Windsor', 42.3149, -83.0364),
        ('Niagara Falls', 43.0896, -79.0849),
        ('St. Catharines', 43.1594, -79.2469),
        ('Brantford', 43.1394, -80.2644),
        ('Peterborough', 44.3091, -78.3197)
"""


def upgrade() -> None:
    # Unplace the city-centre pins.
    op.execute(
        "UPDATE local_content "
        "SET latitude = NULL, longitude = NULL, geom = NULL "
        "WHERE geocode_status = 'fallback_city'"
    )
    # The provider that actually geocoded the item is now recorded for real
    # (it used to be hard-coded to 'google'); give the column room for the
    # longer provider names.
    op.execute(
        "ALTER TABLE local_content ALTER COLUMN geocode_source TYPE VARCHAR(32)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE local_content ALTER COLUMN geocode_source TYPE VARCHAR(16)"
    )
    # Put the city-centre pins back where the crawler had put them.
    op.execute(
        "UPDATE local_content lc "
        "SET latitude = c.lat, longitude = c.lng, "
        "    geom = ST_SetSRID(ST_MakePoint(c.lng, c.lat), 4326) "
        "FROM (VALUES " + _CITY_CENTROIDS + ") AS c(city, lat, lng) "
        "WHERE lc.geocode_status = 'fallback_city' AND lc.city = c.city"
    )
