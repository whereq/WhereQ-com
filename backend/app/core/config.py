from datetime import datetime
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Database hosts that count as "local" — development mode is safe against these.
_LOCAL_DB_HOSTS = frozenset({
    "localhost", "127.0.0.1", "::1", "host.docker.internal",
})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/whereq"
    DATABASE_URL_SYNC: str = "postgresql://postgres:password@localhost:5432/whereq"

    # Security (legacy local JWT — retained only for password hashing utilities)
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10_080  # 7 days

    # Keycloak / OIDC (public SPA client) — authentication is delegated to an
    # external OpenID Connect provider. The backend only *verifies* RS256
    # access tokens; it never issues a session of its own.
    #
    # Leave KEYCLOAK_URL empty to run without authentication: the public
    # browsing endpoints work, and every protected endpoint answers 401 with
    # a clear "authentication is not configured" message. Point these at your
    # own realm to enable sign-in — see docs/SETUP.md.
    KEYCLOAK_URL: str = ""
    KEYCLOAK_REALM: str = "whereq"
    KEYCLOAK_CLIENT_ID: str = "whereq-spa"

    # Keycloak Admin (confidential service-account client) — used for any
    # server-to-server Admin REST calls (e.g. role assignment). Optional.
    KEYCLOAK_ADMIN_CLIENT_ID: str = "whereq-backend"
    KEYCLOAK_ADMIN_CLIENT_SECRET: str = ""

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:3743"]

    # ── Nearby search (the map's "everything around me" list) ───────────────
    #: Default radius of the nearby search, in kilometres — also the default
    #: the user's settings start from.
    NEARBY_DEFAULT_RADIUS_KM: float = 5.0
    #: Hard ceiling on the radius a caller may ask for.
    NEARBY_MAX_RADIUS_KM: float = 25.0

    # Optional
    GOOGLE_MAPS_API_KEY: str = ""
    # Server-side Google Maps key for backend web-service calls (Geocoding,
    # Places New, Routes, Static). MUST be a separate key WITHOUT an HTTP-referrer
    # restriction (the SPA's GOOGLE_MAPS_API_KEY is referrer-locked, so server
    # calls with it are blocked: API_KEY_HTTP_REFERRER_BLOCKED). Restrict this one
    # by IP and/or API allowlist instead. Falls back to GOOGLE_MAPS_API_KEY.
    GOOGLE_MAPS_SERVER_KEY: str = ""

    # ── Geocoding (multi-provider; free tiers first, Google last) ───────────
    # Priority order tried left→right; over-quota / unconfigured providers are
    # skipped. Keep "google" last so the paid API is the fallback of last resort.
    # Keyed free tiers first (largest daily quota first), then Nominatim as an
    # unlimited-but-rate-limited fallback, then Google (paid) last.
    GEOCODE_PROVIDER_ORDER: str = "geocode_maps_co,locationiq,geocodio,nominatim,google"
    GEOCODE_REGION_BIAS: str = "ca"     # legacy fallback country bias (ccTLD)
    GEOCODE_COUNTRY: str = "CA"          # default ISO country for components bias

    # Nominatim (OpenStreetMap) — no daily cap but strict 1 req/sec usage policy;
    # a contact email is required by the policy for production use.
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_EMAIL: str = ""
    NOMINATIM_RPS: float = 1.0
    NOMINATIM_DAILY_QUOTA: int = 100_000   # effectively unlimited; rate-limited instead

    # Geocodio (US/CA) — 2,500/day free
    GEOCODIO_API_KEY: str = ""
    GEOCODIO_DAILY_QUOTA: int = 2_500

    # LocationIQ — 5,000/day free
    LOCATIONIQ_API_KEY: str = ""
    LOCATIONIQ_DAILY_QUOTA: int = 5_000

    # geocode.maps.co — free API key; 25,000/day (5 req/sec burst, then 1 req/sec)
    GEOCODE_MAPS_CO_API_KEY: str = ""
    GEOCODE_MAPS_CO_DAILY_QUOTA: int = 25_000

    # Positionstack — 25,000/month free
    POSITIONSTACK_API_KEY: str = ""
    POSITIONSTACK_MONTHLY_QUOTA: int = 25_000

    # Google — paid fallback. Large cap so it's effectively "always allowed last".
    GOOGLE_GEOCODE_DAILY_QUOTA: int = 100_000

    # ── Crawler scheduler (whereq-crawler container) ────────────────────────
    CRAWLER_ENABLED: bool = True
    CRAWLER_TICK_SECONDS: int = 300        # how often to crawl sources that are due
    CRAWLER_RETENTION_SECONDS: int = 3600  # how often to expire stale rows
    CRAWLER_SEED_ON_START: bool = True     # upsert default sources on startup

    # OSM POI crawl (Local Essentials + Quick Categories). The scheduler
    # checks daily and only re-crawls when the newest OSM row is older than the
    # interval — so a fresh DB auto-populates and restarts don't re-hammer
    # Overpass.
    POI_CRAWL_ENABLED: bool = True
    POI_CRAWL_CHECK_SECONDS: int = 86_400      # how often to check due-ness (daily)
    POI_CRAWL_INTERVAL_DAYS: int = 7           # refresh cadence

    # ── Fuel stations (whereq.cloud data feed) ──────────────────────────────
    # North American fuel stations + live prices crawled from the whereq.cloud
    # API into `places` as POIs (category 'gas'). Public access is a demo
    # preview (oldest 100 rows); the live/full dataset is metered — set
    # WHEREQ_CLOUD_API_KEY (a wq_live_… key from whereq.cloud). The key stays
    # server-side; the browser never talks to whereq.cloud directly.
    WHEREQ_CLOUD_API_KEY: str = ""
    FUEL_CRAWL_ENABLED: bool = True
    # Coverage targets, crawled round-robin so no single tick pulls everything.
    # Grammar per target: "CC" | "CC:State" | "CC:State:Municipality" |
    # "bbox:minLon,minLat,maxLon,maxLat". CC is an ISO code from
    # whereq_cloud.FUEL_COUNTRIES (MX, US, CA); State is a full name or an
    # ISO code ("Ontario"/"ON", "Texas"/"TX").
    FUEL_CRAWL_TARGETS: str = "CA,US"
    # How many due targets one crawler tick may crawl (spreads the API load
    # across ticks; the full cycle still completes every interval).
    FUEL_CRAWL_TARGETS_PER_TICK: int = 1
    FUEL_CRAWL_CHECK_SECONDS: int = 3_600      # how often to look for due targets
    FUEL_CRAWL_INTERVAL_HOURS: int = 6         # refresh cadence per target
    FUEL_CRAWL_PAGE_SIZE: int = 500            # API max rows per page
    FUEL_CRAWL_MAX_STATIONS: int = 60_000      # safety cap per target crawl
    # The fuel API allows 30 requests/minute per key; we self-throttle to stay
    # under it (and to leave headroom for other whereq.cloud calls).
    FUEL_CRAWL_MIN_INTERVAL: float = 2.2       # seconds between API requests
    FUEL_CRAWL_MAX_RETRIES: int = 5            # retries per request (429/5xx)
    WHEREQ_CLOUD_TIMEOUT: float = 60.0          # per-request timeout (seconds)

    # ── Administrative geography (whereq.cloud) ─────────────────────────────────
    # The places that *contain* the places the map draws: provinces, regions,
    # municipalities, cities, towns, wards and neighbourhoods, with real
    # outlines. Two vocabularies (OpenStreetMap and geoBoundaries) are kept
    # side by side — the feed deliberately does not merge them. Both are open
    # data (ODbL 1.0 / CC-BY 4.0), so the attribution travels with each row.
    GEO_CRAWL_ENABLED: bool = True
    # Coverage targets, crawled round-robin so no single tick pulls everything.
    # Grammar per target: "kind:<concept>" | "kind:<concept>:<country>" |
    # "country:<CC>" | "source:<name>" | "bbox:minLon,minLat,maxLon,maxLat".
    GEO_CRAWL_TARGETS: str = "bbox:-80.3,43.6,-79.2,44.2"
    GEO_CRAWL_TARGETS_PER_TICK: int = 1
    GEO_CRAWL_CHECK_SECONDS: int = 21_600      # how often to look for due targets
    GEO_CRAWL_INTERVAL_HOURS: int = 168        # refresh cadence per target (a week)
    GEO_CRAWL_PAGE_SIZE: int = 200            # API max rows per page
    GEO_CRAWL_MAX_PLACES: int = 5_000         # safety cap per target crawl
    # Fetch each place's outline as well as the row. This is the expensive
    # half (one API request per place), but it is also the whole point — an
    # outline is what turns a name into an area on the map.
    GEO_CRAWL_FETCH_BOUNDARIES: bool = True
    # The geography endpoints allow 30 requests/minute, the same limit as the
    # fuel ones — so the boundary crawl of a few hundred places takes minutes,
    # not seconds. Being faster than the limit only earns a 429.
    GEO_CRAWL_MIN_INTERVAL: float = 2.2       # seconds between API requests
    GEO_CRAWL_MAX_RETRIES: int = 5            # retries per request (429/5xx)
    # How much the outline is simplified when it is *served*, in metres. The
    # stored geometry is full resolution — the point-in-polygon test must not
    # be fooled by a simplified edge.
    GEO_BOUNDARY_SIMPLIFY_M: float = 50.0

    # ── Aggregated fuel price series (whereq.cloud) ─────────────────────────
    # State/national/metro averages behind the charts: EIA weekly for the US,
    # StatCan monthly for Canada, CRE for Mexico. Refreshed far less often
    # than station prices (the underlying series are weekly/monthly).
    FUEL_PRICES_ENABLED: bool = True
    FUEL_PRICES_REGIONS: str = "ca,us"          # region slugs (ca, us, mx)
    FUEL_PRICES_INTERVAL_HOURS: int = 24         # refresh cadence (weekly/monthly series)
    FUEL_PRICES_CHECK_SECONDS: int = 3_600       # how often to check whether the series are stale

    # ── WhereQ Maps service (/api/maps/v1) ──────────────────────────────────
    # A keyed data API (geocode / autocomplete / reverse / route) consumed
    # server-to-server by other applications. Auth is an
    # opaque per-consumer key (wq_<env>_<random>), independent of Keycloak.
    MAPS_DEFAULT_RATE_LIMIT_PER_MIN: int = 120   # per-key token bucket default
    MAPS_DEFAULT_MONTHLY_QUOTA: int = 50_000     # per-key hard monthly cap default
    MAPS_ROUTE_CACHE_TTL_SECONDS: int = 3_600    # /route + /matrix cache TTL (ToS: short-term only)
    # For endpoints that must return clean §4 components (region as a 2-letter
    # code, postal_code, …) a consumer can ask for Google explicitly
    # (`?prefer_google=true`). The default is the same free-tiers-first chain
    # the crawler uses, so the service never spends paid quota on the
    # consumer's behalf unless they opt in. Set to True to make Google the
    # service-wide default (e.g. when every consumer needs its components).
    MAPS_GEOCODE_GOOGLE_PREFERRED: bool = False
    # Keycloak realm role required for staff-only surfaces (Maps API key
    # management, and ownership overrides on user-authored content).
    STAFF_ROLE: str = "whereq-admin"
    # The Maps-specific name is kept as an alias so existing deployments (and
    # the documented MAPS_ADMIN_ROLE setting) keep working.
    MAPS_ADMIN_ROLE: str = ""
    # Attribution string returned on user-facing results. The Google Maps
    # Platform Terms require the form "Map data ©<year> Google" — an
    # off-the-shelf "Powered by Google" is not ToS-shaped. The year is
    # computed at import so it does not go stale; override it only if you
    # have a good reason.
    MAPS_ATTRIBUTION: str = Field(
        default_factory=lambda: f"Map data ©{datetime.now().year} Google"
    )
    # /matrix dispatch guard: max total elements (origins × destinations).
    MAPS_MATRIX_MAX_ELEMENTS: int = 25
    # /staticmap in-process byte cache (emails/no-JS fallbacks): TTL + entry cap.
    MAPS_STATICMAP_CACHE_TTL_SECONDS: int = 86_400
    MAPS_STATICMAP_CACHE_MAX: int = 256

    @property
    def maps_google_key(self) -> str:
        """The key backend web-service calls should use (server key preferred)."""
        return self.GOOGLE_MAPS_SERVER_KEY or self.GOOGLE_MAPS_API_KEY

    @property
    def staff_roles(self) -> set[str]:
        """Realm roles that grant staff privileges.

        ``STAFF_ROLE`` is canonical; ``MAPS_ADMIN_ROLE`` is honoured as an
        alias so a deployment that only sets the older name still works.
        """
        roles = {self.STAFF_ROLE}
        if self.MAPS_ADMIN_ROLE:
            roles.add(self.MAPS_ADMIN_ROLE)
        return roles

    @property
    def nearby_default_radius_km(self) -> float:
        """The radius the nearby search starts from (and the default a user's
        settings are created with)."""
        return self.NEARBY_DEFAULT_RADIUS_KM

    @property
    def nearby_max_radius_km(self) -> float:
        """The largest radius a caller may ask for."""
        return self.NEARBY_MAX_RADIUS_KM

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def database_host(self) -> str | None:
        """Hostname of ``DATABASE_URL`` (None when it cannot be parsed)."""
        try:
            return urlparse(self.DATABASE_URL).hostname
        except ValueError:
            return None

    @property
    def unsafe_dev_mode(self) -> bool:
        """True when development mode is combined with a non-local database.

        Development mode enables two things that must never touch a shared or
        production database:

        * **SQL echo** — every statement *and its bound parameters* (emails,
          tokens, prices) is written to the log;
        * **``create_all``** — tables are created straight from the models,
          which silently hides a missing Alembic migration.

        The app refuses to start in that combination instead of quietly
        misbehaving in production.
        """
        if not self.is_dev:
            return False
        host = (self.database_host or "").strip().lower()
        if not host:
            return False  # unknown host — cannot prove it is remote
        return host not in _LOCAL_DB_HOSTS


settings = Settings()
