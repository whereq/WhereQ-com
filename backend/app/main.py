from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base
from app.core.security import get_current_user
from app.maps.errors import MapsError, maps_error_handler, new_request_id
from app.api.routes import (
    auth, health, places, neighborhoods, route_tracking,
    saved_places, stories, users, notifications, friends, newsletter, ws_location,
    schools, local_content, hazards, maps, fuel, nearby, user_settings,
    place_cards, geo,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables in development only; use Alembic migrations in production
    if settings.is_dev:
        import app.models  # noqa: F401 — ensure all models registered
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="whereq API",
    description="Backend for whereq — location-based services platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Maps service (§5): every response carries X-Request-Id; MapsError renders the
# standard error envelope with the same id mirrored in the body.
app.add_exception_handler(MapsError, maps_error_handler)


@app.middleware("http")
async def _request_id_middleware(request, call_next):
    request.state.request_id = new_request_id()
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response

# ---------------------------------------------------------------------------
# Router registration.
#
# Public routes: browsing data is open to anonymous users.
# Protected routes: user-specific features and school boundary data require
# a valid token.
# ---------------------------------------------------------------------------
_auth = [Depends(get_current_user)]

# Public (anonymous browsing)
app.include_router(health.router,           prefix="/api")
app.include_router(newsletter.router,       prefix="/api")
app.include_router(ws_location.router,      prefix="/api")
app.include_router(auth.router,             prefix="/api")
app.include_router(places.router,           prefix="/api")
app.include_router(neighborhoods.router,    prefix="/api")
app.include_router(route_tracking.router,   prefix="/api")
app.include_router(stories.router,          prefix="/api")
app.include_router(local_content.router,    prefix="/api")
# Nearby: the map's "everything around me" search — the POIs, the fuel
# stations, the news and the schools within a radius, merged into one list.
# Public; the live fuel prices inside it are only included for a signed-in
# caller (the prices are licensed).
app.include_router(nearby.router,          prefix="/api")
# Schools: browsing/list/map/detail are public; boundary geometry is gated
# per-endpoint inside the router (GET /schools/at requires a token, and
# /schools/{id} omits boundary_geojson for anonymous callers).
app.include_router(schools.router,          prefix="/api")
# Hazards: map view is public; reporting/confirming require a token (enforced
# per-endpoint in the router).
app.include_router(hazards.router,          prefix="/api")
# Fuel: station prices + the aggregated price series, crawled from whereq.cloud.
# The whole router requires a session — the price data is licensed and metered
# upstream (the metered API key itself stays on the server).
app.include_router(fuel.router,             prefix="/api")
# Geography: the administrative areas (provinces, municipalities, wards,
# neighbourhoods) that contain the places, with their outlines. Public — the
# feed is open data (ODbL 1.0 / CC-BY 4.0) and the attribution travels on
# every row.
app.include_router(geo.router,              prefix="/api")

# Maps service (/api/maps/v1): opaque per-consumer API-key auth (server-to-
# server), enforced per-endpoint via require_maps_key — not the Keycloak dep.
# The admin sub-router is Keycloak staff-gated (require_staff).
app.include_router(maps.router,             prefix="/api")
app.include_router(maps.admin,             prefix="/api")

# Protected (valid token required)
app.include_router(users.router,            prefix="/api", dependencies=_auth)
app.include_router(saved_places.router,     prefix="/api", dependencies=_auth)
app.include_router(notifications.router,    prefix="/api", dependencies=_auth)
app.include_router(friends.router,          prefix="/api", dependencies=_auth)
# The caller's own settings (the nearby radius and category selection).
app.include_router(user_settings.router,   prefix="/api", dependencies=_auth)
app.include_router(place_cards.router,    prefix="/api", dependencies=_auth)
