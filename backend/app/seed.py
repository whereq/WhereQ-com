"""
Seed script — populate the database with initial demo data.

Usage:
    cd backend
    python -m app.seed
"""

import asyncio

from sqlalchemy import select

from app.core.database import engine, AsyncSessionLocal, Base
from app.models.user import User
from app.models.place import Place
from app.models.neighborhood import Neighborhood
from app.models.story import Story


# ── Places (mapped from frontend mapData.ts PINS) ──────────────

PLACES = [
    # Memorials
    dict(name="Greybrick Theatre", latitude=43.6548, longitude=-79.3806,
         category="memorial", kind="memorial", sub="1923 · Demolished 1978",
         description="Once the city's grandest movie house. Marlene Dietrich performed here in 1932. "
                     "Today the lot is a parking garage; the marquee neon survives in a private collection.",
         city="Toronto", country="Canada"),
    dict(name="Old Foundry Steps", latitude=43.6480, longitude=-79.3900,
         category="memorial", kind="memorial", sub="Industrial heritage",
         description="The last remnant of the old industrial waterfront, these stone steps once led "
                     "workers down to the foundry floor.",
         city="Toronto", country="Canada"),

    # POIs
    dict(name="Pier Coffee", latitude=43.6500, longitude=-79.3850,
         category="coffee", kind="poi", city="Toronto", country="Canada"),
    dict(name="Sato Ramen", latitude=43.6525, longitude=-79.3790,
         category="food", kind="poi", city="Toronto", country="Canada"),
    dict(name="P-Garage", latitude=43.6560, longitude=-79.3940,
         category="parking", kind="poi", city="Toronto", country="Canada"),
    dict(name="Shell", latitude=43.6525, longitude=-79.3700,
         category="fuel", kind="poi", city="Toronto", country="Canada"),

    # Schools
    dict(name="Lincoln Elementary", latitude=43.6570, longitude=-79.3880,
         category="school", kind="school", sub="K–5 · public",
         metadata_json={"level": "elem", "grade": "K–5"},
         city="Toronto", country="Canada"),
    dict(name="Oakridge Elementary", latitude=43.6480, longitude=-79.3770,
         category="school", kind="school", sub="K–5 · charter",
         metadata_json={"level": "elem", "grade": "K–5"},
         city="Toronto", country="Canada"),
    dict(name="Riverside Academy", latitude=43.6500, longitude=-79.3960,
         category="school", kind="school", sub="K–8 · private",
         metadata_json={"level": "k8", "grade": "K–8"},
         city="Toronto", country="Canada"),
    dict(name="Mission Middle School", latitude=43.6610, longitude=-79.3820,
         category="school", kind="school", sub="6–8 · public",
         metadata_json={"level": "middle", "grade": "6–8"},
         city="Toronto", country="Canada"),
    dict(name="Bay High School", latitude=43.6610, longitude=-79.3910,
         category="school", kind="school", sub="9–12 · public",
         metadata_json={"level": "high", "grade": "9–12"},
         city="Toronto", country="Canada"),
    dict(name="City College · East", latitude=43.6570, longitude=-79.3710,
         category="school", kind="school", sub="community · 2-yr",
         metadata_json={"level": "college", "grade": "CC"},
         city="Toronto", country="Canada"),
    dict(name="Bayview University", latitude=43.6440, longitude=-79.3740,
         category="school", kind="school", sub="public · enrollment 18k",
         metadata_json={"level": "uni", "grade": "UNI"},
         city="Toronto", country="Canada"),

    # Pharmacies
    dict(name="Walgreens", latitude=43.6550, longitude=-79.3860,
         category="pharmacy", kind="pharmacy", sub="open 24h",
         city="Toronto", country="Canada"),
    dict(name="CVS Pharmacy", latitude=43.6520, longitude=-79.3760,
         category="pharmacy", kind="pharmacy", sub="closes 22:00",
         city="Toronto", country="Canada"),
    dict(name="Mission Drugs", latitude=43.6460, longitude=-79.3910,
         category="pharmacy", kind="pharmacy", sub="locally owned",
         city="Toronto", country="Canada"),

    # Clinics
    dict(name="Mission Walk-In", latitude=43.6495, longitude=-79.3830,
         category="clinic", kind="clinic", sub="wait ≈ 18 min",
         city="Toronto", country="Canada"),
    dict(name="East Quarter Urgent", latitude=43.6565, longitude=-79.3730,
         category="clinic", kind="clinic", sub="wait ≈ 42 min",
         city="Toronto", country="Canada"),

    # Plazas
    dict(name="Cornerstone Plaza", latitude=43.6590, longitude=-79.3840,
         category="plaza", kind="plaza", sub="market · Sat 9–14",
         city="Toronto", country="Canada"),
    dict(name="Foundry Square", latitude=43.6460, longitude=-79.3800,
         category="plaza", kind="plaza", sub="food trucks",
         city="Toronto", country="Canada"),
    dict(name="Riverside Plaza", latitude=43.6580, longitude=-79.3930,
         category="plaza", kind="plaza", sub="fountain",
         city="Toronto", country="Canada"),

    # Libraries
    dict(name="Mission Branch Library", latitude=43.6525, longitude=-79.3825,
         category="library", kind="library", sub="open until 20:00",
         city="Toronto", country="Canada"),
]


NEIGHBORHOOD = dict(
    name="Downtown Core",
    description="Toronto's vibrant downtown core, home to the financial district, "
                "entertainment district, and the waterfront. A mix of historic "
                "architecture and modern skyscrapers with excellent transit.",
    city="Toronto",
    country="Canada",
    latitude=43.6532,
    longitude=-79.3832,
    safety_score=78,
    walkability_score=92,
    transit_score=88,
    food_score=85,
    schools_score=74,
    overall_score=83,
)


# Demo accounts for local development.
#
# These rows exist so the app has something to point foreign keys at while
# you are building. They carry NO password: authentication is delegated to
# the OIDC provider, and the backend never issues a session of its own
# (see app/core/security.py). A real user row is provisioned automatically
# on the first authenticated request.
USERS = [
    dict(username="demo", email="demo@example.invalid", locale="en", theme="dark"),
    dict(username="admin", email="admin@example.invalid", locale="en", theme="dark"),
]


async def seed():
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Check if already seeded
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none():
            print("Database already seeded, skipping.")
            return

        # Users
        users = []
        for u in USERS:
            user = User(
                username=u["username"],
                email=u["email"],
                locale=u["locale"],
                theme=u["theme"],
            )
            db.add(user)
            users.append(user)
        await db.flush()
        print(f"Created {len(users)} users")

        # Neighborhood
        nb = Neighborhood(**NEIGHBORHOOD)
        db.add(nb)
        await db.flush()
        print(f"Created neighborhood: {nb.name}")

        # Places
        places = []
        for p in PLACES:
            place = Place(**p)
            db.add(place)
            places.append(place)
        await db.flush()
        print(f"Created {len(places)} places")

        # Stories (attach to memorial places)
        memorial_places = [p for p in places if p.category == "memorial"]
        if memorial_places and users:
            story1 = Story(
                place_id=memorial_places[0].id,
                author_id=users[0].id,
                title="The Last Showing",
                content="My grandmother told me about the last film shown at the Greybrick — "
                        "a midnight screening of Casablanca in the summer of 1978. The marquee "
                        "lights flickered twice and then went dark forever.",
                category="memorial",
            )
            db.add(story1)

            if len(memorial_places) > 1:
                story2 = Story(
                    place_id=memorial_places[1].id,
                    author_id=users[0].id,
                    title="Foundry Memories",
                    content="These steps are the only piece of the old iron works that survived "
                            "the waterfront redevelopment. Workers would sit here during lunch, "
                            "watching barges on the river.",
                    category="memorial",
                )
                db.add(story2)
            print("Created stories")

        await db.commit()
        print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
