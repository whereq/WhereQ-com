-- =============================================================================
-- whereq.com — Database Schema
-- PostgreSQL 17 + PostGIS
-- =============================================================================
-- GENERATED from the Alembic migrations — do not edit by hand.
--
-- The Alembic migrations in `backend/alembic/versions/` are the source of
-- truth for the schema. This file is a snapshot of what they produce, kept
-- so you can read the shape of the database without running anything.
--
-- Regenerate it with:
--   docker compose -f docker/docker-compose.yml up -d postgres
--   docker compose -f docker/docker-compose.yml run --rm migrate
--   docker compose -f docker/docker-compose.yml exec -T postgres \
--     pg_dump -U whereq -d whereq --schema-only --no-owner --no-privileges \
--     --schema=public > db/schema.sql
--
-- Apply it to an empty database with:
--   psql -U whereq -d whereq -f db/schema.sql
--
-- Note: this snapshot assumes the PostGIS extension is already installed —
-- the migrations create it themselves (`CREATE EXTENSION IF NOT EXISTS postgis`).
-- =============================================================================

-- public
--

CREATE SCHEMA public;


--
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
--

CREATE TABLE public.board_category (
    id integer NOT NULL,
    board_id integer NOT NULL,
    code character varying(64) NOT NULL,
    label character varying(255),
    category_type character varying(32),
    description text
);


--
--

CREATE SEQUENCE public.board_category_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.board_category_id_seq OWNED BY public.board_category.id;


--
--

CREATE TABLE public.country (
    id integer NOT NULL,
    iso2 character varying(2) NOT NULL,
    name character varying(128),
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.country_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.country_id_seq OWNED BY public.country.id;


--
--

CREATE TABLE public.crawl_snapshot (
    id bigint NOT NULL,
    entity_type character varying(32),
    entity_ref character varying(255),
    province character varying(8),
    board character varying(128),
    slug character varying(255),
    lang character varying(8),
    source character varying(64),
    raw jsonb NOT NULL,
    content_sha256 character varying(64) NOT NULL,
    file_path character varying(1024),
    fetched_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.crawl_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.crawl_snapshot_id_seq OWNED BY public.crawl_snapshot.id;


--
--

CREATE TABLE public.friendships (
    id integer NOT NULL,
    user_id integer,
    friend_id integer,
    status character varying(16) DEFAULT 'pending'::character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.friendships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.friendships_id_seq OWNED BY public.friendships.id;


--
--

CREATE TABLE public.fuel_price_series (
    id integer NOT NULL,
    domain character varying(24) NOT NULL,
    source character varying(32),
    region character varying(24),
    geo character varying(160),
    item text NOT NULL,
    unit character varying(64),
    frequency character varying(16),
    latest_period character varying(32),
    latest_value double precision,
    prev_value double precision,
    points integer,
    spark jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.fuel_price_series_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.fuel_price_series_id_seq OWNED BY public.fuel_price_series.id;


--
--

CREATE TABLE public.fuel_sync_state (
    target_key character varying(128) NOT NULL,
    country character varying(2),
    state character varying(120),
    municipality character varying(160),
    bbox character varying(128),
    last_synced_at timestamp with time zone,
    last_attempt_at timestamp with time zone,
    station_count integer DEFAULT 0 NOT NULL,
    last_error text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE TABLE public.geo_concepts (
    kind character varying(24) NOT NULL,
    name character varying(64) NOT NULL,
    name_cn character varying(64),
    description text,
    description_cn text,
    rank integer DEFAULT 0 NOT NULL,
    upstream_places integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
--

CREATE TABLE public.geo_places (
    uid character varying(64) NOT NULL,
    kind character varying(24) NOT NULL,
    kind_source character varying(24),
    name character varying(255) NOT NULL,
    name_en character varying(255),
    name_zh character varying(255),
    name_local character varying(255),
    official_name character varying(255),
    source character varying(24) NOT NULL,
    source_id character varying(96),
    source_url character varying(512),
    license character varying(160),
    raw_admin_level integer,
    raw_place character varying(48),
    raw_boundary character varying(48),
    country_code character varying(2),
    province_code character varying(8),
    iso_code character varying(16),
    ref character varying(48),
    population integer,
    population_date character varying(16),
    wikidata character varying(32),
    wikipedia character varying(255),
    website character varying(255),
    capital character varying(160),
    centroid_lon double precision,
    centroid_lat double precision,
    bbox_min_lon double precision,
    bbox_min_lat double precision,
    bbox_max_lon double precision,
    bbox_max_lat double precision,
    area_km2 double precision,
    has_boundary boolean DEFAULT false NOT NULL,
    boundary_geojson jsonb,
    geom public.geometry(MultiPolygon,4326),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
--

CREATE TABLE public.geo_sync_state (
    target_key character varying(160) NOT NULL,
    kind character varying(24),
    source character varying(24),
    country character varying(2),
    bbox character varying(128),
    last_synced_at timestamp with time zone,
    last_attempt_at timestamp with time zone,
    place_count integer DEFAULT 0 NOT NULL,
    boundary_count integer DEFAULT 0 NOT NULL,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
--

CREATE TABLE public.geocode_cache (
    id integer NOT NULL,
    query_sha256 character varying(64) NOT NULL,
    query text NOT NULL,
    latitude double precision,
    longitude double precision,
    formatted_address character varying(512),
    confidence double precision,
    provider character varying(16) DEFAULT 'google'::character varying,
    hit_count integer DEFAULT 0,
    raw jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.geocode_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.geocode_cache_id_seq OWNED BY public.geocode_cache.id;


--
--

CREATE TABLE public.geocode_provider_usage (
    id integer NOT NULL,
    provider character varying(32) NOT NULL,
    period character varying(16) NOT NULL,
    count integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.geocode_provider_usage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.geocode_provider_usage_id_seq OWNED BY public.geocode_provider_usage.id;


--
--

CREATE TABLE public.hazards (
    id integer NOT NULL,
    type character varying(24) DEFAULT 'hazard'::character varying NOT NULL,
    severity character varying(8) DEFAULT 'med'::character varying NOT NULL,
    title character varying(200) NOT NULL,
    description text,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    geom public.geometry(Point,4326),
    reporter_id integer,
    confirmations integer DEFAULT 0 NOT NULL,
    status character varying(8) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone NOT NULL
);


--
--

CREATE SEQUENCE public.hazards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.hazards_id_seq OWNED BY public.hazards.id;


--
--

CREATE TABLE public.local_content (
    id bigint NOT NULL,
    source_id integer,
    type character varying(16) DEFAULT 'news'::character varying NOT NULL,
    category character varying(32) DEFAULT 'other'::character varying NOT NULL,
    title character varying(512) NOT NULL,
    summary text,
    description text,
    source_name character varying(128),
    source_url character varying(1024),
    external_id character varying(255),
    event_time timestamp with time zone,
    event_end_time timestamp with time zone,
    publish_time timestamp with time zone,
    latitude double precision,
    longitude double precision,
    geom public.geometry(Point,4326),
    address character varying(512),
    city character varying(128),
    province character varying(16),
    country character varying(8),
    geocode_status character varying(16) DEFAULT 'none'::character varying,
    geocode_source character varying(32),
    confidence_score double precision,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    image_url character varying(1024),
    expires_at timestamp with time zone,
    content_sha256 character varying(64),
    dedup_key character varying(64),
    raw jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.local_content_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.local_content_id_seq OWNED BY public.local_content.id;


--
--

CREATE TABLE public.local_content_location (
    id integer NOT NULL,
    content_id bigint NOT NULL,
    latitude double precision,
    longitude double precision,
    geom public.geometry(Point,4326),
    address character varying(512),
    label character varying(255),
    is_primary boolean DEFAULT false
);


--
--

CREATE SEQUENCE public.local_content_location_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.local_content_location_id_seq OWNED BY public.local_content_location.id;


--
--

CREATE TABLE public.local_content_tag (
    id integer NOT NULL,
    content_id bigint NOT NULL,
    tag character varying(64) NOT NULL
);


--
--

CREATE SEQUENCE public.local_content_tag_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.local_content_tag_id_seq OWNED BY public.local_content_tag.id;


--
--

CREATE TABLE public.maps_api_consumer (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    key_hash text NOT NULL,
    key_prefix text NOT NULL,
    scopes text[] DEFAULT '{}'::text[] NOT NULL,
    rate_limit_per_min integer DEFAULT 120 NOT NULL,
    monthly_quota integer DEFAULT 50000 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    revoked_at timestamp with time zone
);


--
--

CREATE TABLE public.maps_api_usage (
    id bigint NOT NULL,
    consumer_id uuid NOT NULL,
    day date NOT NULL,
    endpoint text NOT NULL,
    provider text NOT NULL,
    count integer DEFAULT 0 NOT NULL
);


--
--

CREATE SEQUENCE public.maps_api_usage_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.maps_api_usage_id_seq OWNED BY public.maps_api_usage.id;


--
--

CREATE TABLE public.neighborhoods (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    city character varying(128),
    country character varying(128),
    boundary_geojson jsonb,
    walkability_score integer DEFAULT 0,
    transit_score integer DEFAULT 0,
    food_score integer DEFAULT 0,
    schools_score integer DEFAULT 0,
    overall_score integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    description text,
    latitude double precision,
    longitude double precision,
    safety_score integer,
    user_id integer
);


--
--

CREATE SEQUENCE public.neighborhoods_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.neighborhoods_id_seq OWNED BY public.neighborhoods.id;


--
--

CREATE TABLE public.news_source (
    id integer NOT NULL,
    slug character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    kind character varying(16) DEFAULT 'rss'::character varying NOT NULL,
    url character varying(1024) NOT NULL,
    homepage_url character varying(512),
    default_type character varying(16) DEFAULT 'news'::character varying,
    default_category character varying(32),
    default_city character varying(128),
    default_province character varying(16),
    default_country character varying(8) DEFAULT 'CA'::character varying,
    enabled boolean DEFAULT true,
    crawl_interval_minutes integer DEFAULT 60,
    last_crawled_at timestamp with time zone,
    last_status character varying(16),
    last_error text,
    config jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.news_source_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.news_source_id_seq OWNED BY public.news_source.id;


--
--

CREATE TABLE public.newsletter_subscribers (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.newsletter_subscribers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.newsletter_subscribers_id_seq OWNED BY public.newsletter_subscribers.id;


--
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer,
    title character varying(255) NOT NULL,
    body text,
    kind character varying(32) DEFAULT 'info'::character varying,
    is_read boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
--

CREATE TABLE public.place_cards (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    kind character varying(16) DEFAULT 'business'::character varying NOT NULL,
    category character varying(64),
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    address character varying(512),
    city character varying(128),
    country character varying(128),
    radius_km double precision DEFAULT '5'::double precision NOT NULL,
    categories text[] DEFAULT '{}'::text[] NOT NULL,
    logo_url text,
    accent character varying(16),
    status character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    publish_token character varying(64),
    published_at timestamp with time zone,
    revoked_at timestamp with time zone,
    report_count integer DEFAULT 0 NOT NULL,
    view_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
--

CREATE SEQUENCE public.place_cards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.place_cards_id_seq OWNED BY public.place_cards.id;


--
--

CREATE TABLE public.places (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    address character varying(512),
    city character varying(128),
    country character varying(128),
    category character varying(64) DEFAULT 'general'::character varying,
    kind character varying(32) DEFAULT 'poi'::character varying,
    sub character varying(255),
    metadata_json jsonb DEFAULT '{}'::jsonb,
    view_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    source character varying(16) DEFAULT 'manual'::character varying NOT NULL,
    external_id character varying(64),
    geom public.geometry(Point,4326),
    user_id integer
);


--
--

CREATE SEQUENCE public.places_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.places_id_seq OWNED BY public.places.id;


--
--

CREATE TABLE public.program (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    label character varying(255)
);


--
--

CREATE SEQUENCE public.program_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.program_id_seq OWNED BY public.program.id;


--
--

CREATE TABLE public.province (
    id integer NOT NULL,
    country_id integer NOT NULL,
    code character varying(8) NOT NULL,
    name character varying(128),
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.province_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.province_id_seq OWNED BY public.province.id;


--
--

CREATE TABLE public.route_cache (
    key character varying(64) NOT NULL,
    distance_m integer NOT NULL,
    duration_s integer NOT NULL,
    duration_in_traffic_s integer,
    polyline text,
    bounds jsonb,
    provider character varying(16) DEFAULT 'google'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE TABLE public.routes (
    id integer NOT NULL,
    user_id integer,
    name character varying(255) NOT NULL,
    description text,
    waypoints jsonb DEFAULT '[]'::jsonb,
    total_distance_km double precision,
    duration_minutes integer,
    is_public boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.routes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.routes_id_seq OWNED BY public.routes.id;


--
--

CREATE TABLE public.saved_places (
    id integer NOT NULL,
    user_id integer,
    place_id integer,
    label character varying(128),
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.saved_places_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.saved_places_id_seq OWNED BY public.saved_places.id;


--
--

CREATE TABLE public.school (
    id bigint NOT NULL,
    province_id integer NOT NULL,
    board_id integer,
    slug character varying(255) NOT NULL,
    name character varying(512) NOT NULL,
    type character varying(32),
    status character varying(32),
    source_id character varying(64),
    board_name character varying(255),
    school_code character varying(64),
    address character varying(512),
    city character varying(255),
    municipality character varying(255),
    region character varying(128),
    phone character varying(64),
    phone2 character varying(64),
    fax character varying(64),
    website_url character varying(512),
    grade_range character varying(255),
    boundary_pdf_url character varying(512),
    lat double precision,
    lng double precision,
    principal character varying(255),
    vice_principal character varying(255),
    superintendent character varying(255),
    trustee character varying(255),
    bell_times jsonb,
    hs_id integer,
    hs_name character varying(512),
    hs_board_type character varying(32),
    hs_school_type character varying(32),
    hs_score double precision,
    hs_score_year integer,
    hs_score_average double precision,
    hs_rank integer,
    hs_rank_total integer,
    hs_rank_year integer,
    feeder_schools jsonb,
    extra jsonb,
    current_snapshot_id bigint,
    content_sha256 character varying(64),
    valid_from timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE TABLE public.school_board (
    id integer NOT NULL,
    province_id integer NOT NULL,
    slug character varying(128) NOT NULL,
    name character varying(255) NOT NULL,
    short_name character varying(64),
    type character varying(16),
    region character varying(128),
    website_url character varying(512),
    school_count_total integer,
    school_count_elementary integer,
    school_count_secondary integer,
    source_url character varying(512),
    crawled_at timestamp with time zone,
    current_snapshot_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.school_board_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.school_board_id_seq OWNED BY public.school_board.id;


--
--

CREATE TABLE public.school_boundary (
    id bigint NOT NULL,
    school_id bigint NOT NULL,
    polygon_index integer NOT NULL,
    geojson jsonb,
    geom public.geometry(Polygon,4326),
    source character varying(64),
    snapshot_id bigint,
    valid_from timestamp with time zone,
    valid_to timestamp with time zone,
    is_current boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.school_boundary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.school_boundary_id_seq OWNED BY public.school_boundary.id;


--
--

CREATE TABLE public.school_eqao (
    id bigint NOT NULL,
    school_id bigint NOT NULL,
    grade integer NOT NULL,
    year_mark character varying(16),
    rank integer,
    total integer,
    last5_avg integer,
    snapshot_id bigint
);


--
--

CREATE SEQUENCE public.school_eqao_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.school_eqao_id_seq OWNED BY public.school_eqao.id;


--
--

CREATE SEQUENCE public.school_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.school_id_seq OWNED BY public.school.id;


--
--

CREATE TABLE public.school_program (
    school_id bigint NOT NULL,
    program_id integer NOT NULL
);


--
--

CREATE TABLE public.school_score (
    id bigint NOT NULL,
    school_id bigint NOT NULL,
    year integer NOT NULL,
    rank integer,
    rank_total integer,
    rank_score double precision,
    avg_exam_mark double precision,
    year_label character varying(16),
    source character varying(32) DEFAULT 'housesigma'::character varying,
    snapshot_id bigint
);


--
--

CREATE SEQUENCE public.school_score_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.school_score_id_seq OWNED BY public.school_score.id;


--
--

CREATE TABLE public.school_version (
    id bigint NOT NULL,
    school_id bigint NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    is_current boolean DEFAULT true,
    content_sha256 character varying(64),
    snapshot_id bigint,
    attrs jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
--

CREATE SEQUENCE public.school_version_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.school_version_id_seq OWNED BY public.school_version.id;


--
--

CREATE TABLE public.stories (
    id integer NOT NULL,
    place_id integer,
    author_id integer,
    title character varying(255) NOT NULL,
    content text NOT NULL,
    category character varying(64) DEFAULT 'personal'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    is_published boolean DEFAULT true NOT NULL
);


--
--

CREATE SEQUENCE public.stories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.stories_id_seq OWNED BY public.stories.id;


--
--

CREATE TABLE public.user_settings (
    user_id integer NOT NULL,
    radius_km double precision DEFAULT 5.0 NOT NULL,
    categories text[] DEFAULT '{}'::text[] NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(64) NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255),
    is_active boolean DEFAULT true,
    locale character varying(8) DEFAULT 'en'::character varying,
    theme character varying(8) DEFAULT 'dark'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    keycloak_id character varying(64)
);


--
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
--

ALTER TABLE ONLY public.board_category ALTER COLUMN id SET DEFAULT nextval('public.board_category_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.country ALTER COLUMN id SET DEFAULT nextval('public.country_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.crawl_snapshot ALTER COLUMN id SET DEFAULT nextval('public.crawl_snapshot_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.friendships ALTER COLUMN id SET DEFAULT nextval('public.friendships_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.fuel_price_series ALTER COLUMN id SET DEFAULT nextval('public.fuel_price_series_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.geocode_cache ALTER COLUMN id SET DEFAULT nextval('public.geocode_cache_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.geocode_provider_usage ALTER COLUMN id SET DEFAULT nextval('public.geocode_provider_usage_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.hazards ALTER COLUMN id SET DEFAULT nextval('public.hazards_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.local_content ALTER COLUMN id SET DEFAULT nextval('public.local_content_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.local_content_location ALTER COLUMN id SET DEFAULT nextval('public.local_content_location_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.local_content_tag ALTER COLUMN id SET DEFAULT nextval('public.local_content_tag_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.maps_api_usage ALTER COLUMN id SET DEFAULT nextval('public.maps_api_usage_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.neighborhoods ALTER COLUMN id SET DEFAULT nextval('public.neighborhoods_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.news_source ALTER COLUMN id SET DEFAULT nextval('public.news_source_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.newsletter_subscribers ALTER COLUMN id SET DEFAULT nextval('public.newsletter_subscribers_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.place_cards ALTER COLUMN id SET DEFAULT nextval('public.place_cards_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.places ALTER COLUMN id SET DEFAULT nextval('public.places_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.program ALTER COLUMN id SET DEFAULT nextval('public.program_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.province ALTER COLUMN id SET DEFAULT nextval('public.province_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.routes ALTER COLUMN id SET DEFAULT nextval('public.routes_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.saved_places ALTER COLUMN id SET DEFAULT nextval('public.saved_places_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.school ALTER COLUMN id SET DEFAULT nextval('public.school_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.school_board ALTER COLUMN id SET DEFAULT nextval('public.school_board_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.school_boundary ALTER COLUMN id SET DEFAULT nextval('public.school_boundary_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.school_eqao ALTER COLUMN id SET DEFAULT nextval('public.school_eqao_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.school_score ALTER COLUMN id SET DEFAULT nextval('public.school_score_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.school_version ALTER COLUMN id SET DEFAULT nextval('public.school_version_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.stories ALTER COLUMN id SET DEFAULT nextval('public.stories_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
--

ALTER TABLE ONLY public.board_category
    ADD CONSTRAINT board_category_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.country
    ADD CONSTRAINT country_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.crawl_snapshot
    ADD CONSTRAINT crawl_snapshot_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.friendships
    ADD CONSTRAINT friendships_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.fuel_price_series
    ADD CONSTRAINT fuel_price_series_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.fuel_sync_state
    ADD CONSTRAINT fuel_sync_state_pkey PRIMARY KEY (target_key);


--
--

ALTER TABLE ONLY public.geocode_cache
    ADD CONSTRAINT geocode_cache_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.geocode_provider_usage
    ADD CONSTRAINT geocode_provider_usage_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.hazards
    ADD CONSTRAINT hazards_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.local_content_location
    ADD CONSTRAINT local_content_location_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.local_content
    ADD CONSTRAINT local_content_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.local_content_tag
    ADD CONSTRAINT local_content_tag_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.maps_api_consumer
    ADD CONSTRAINT maps_api_consumer_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.maps_api_usage
    ADD CONSTRAINT maps_api_usage_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.neighborhoods
    ADD CONSTRAINT neighborhoods_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.news_source
    ADD CONSTRAINT news_source_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.newsletter_subscribers
    ADD CONSTRAINT newsletter_subscribers_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.geo_concepts
    ADD CONSTRAINT pk_geo_concepts PRIMARY KEY (kind);


--
--

ALTER TABLE ONLY public.geo_places
    ADD CONSTRAINT pk_geo_places PRIMARY KEY (uid);


--
--

ALTER TABLE ONLY public.geo_sync_state
    ADD CONSTRAINT pk_geo_sync_state PRIMARY KEY (target_key);


--
--

ALTER TABLE ONLY public.place_cards
    ADD CONSTRAINT pk_place_cards PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.user_settings
    ADD CONSTRAINT pk_user_settings PRIMARY KEY (user_id);


--
--

ALTER TABLE ONLY public.places
    ADD CONSTRAINT places_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.program
    ADD CONSTRAINT program_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.province
    ADD CONSTRAINT province_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.route_cache
    ADD CONSTRAINT route_cache_pkey PRIMARY KEY (key);


--
--

ALTER TABLE ONLY public.routes
    ADD CONSTRAINT routes_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.saved_places
    ADD CONSTRAINT saved_places_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.school_board
    ADD CONSTRAINT school_board_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.school_boundary
    ADD CONSTRAINT school_boundary_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.school_eqao
    ADD CONSTRAINT school_eqao_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.school
    ADD CONSTRAINT school_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.school_program
    ADD CONSTRAINT school_program_pkey PRIMARY KEY (school_id, program_id);


--
--

ALTER TABLE ONLY public.school_score
    ADD CONSTRAINT school_score_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.school_version
    ADD CONSTRAINT school_version_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_pkey PRIMARY KEY (id);


--
--

ALTER TABLE ONLY public.board_category
    ADD CONSTRAINT uq_board_category UNIQUE (board_id, code);


--
--

ALTER TABLE ONLY public.school_board
    ADD CONSTRAINT uq_board_province_slug UNIQUE (province_id, slug);


--
--

ALTER TABLE ONLY public.school_eqao
    ADD CONSTRAINT uq_eqao_school_grade UNIQUE (school_id, grade, year_mark);


--
--

ALTER TABLE ONLY public.friendships
    ADD CONSTRAINT uq_friendship UNIQUE (user_id, friend_id);


--
--

ALTER TABLE ONLY public.geocode_cache
    ADD CONSTRAINT uq_geocode_cache_query UNIQUE (query_sha256);


--
--

ALTER TABLE ONLY public.geocode_provider_usage
    ADD CONSTRAINT uq_geocode_usage UNIQUE (provider, period);


--
--

ALTER TABLE ONLY public.local_content_tag
    ADD CONSTRAINT uq_local_content_tag UNIQUE (content_id, tag);


--
--

ALTER TABLE ONLY public.local_content
    ADD CONSTRAINT uq_local_source_external UNIQUE (source_id, external_id);


--
--

ALTER TABLE ONLY public.maps_api_usage
    ADD CONSTRAINT uq_maps_usage UNIQUE (consumer_id, day, endpoint, provider);


--
--

ALTER TABLE ONLY public.news_source
    ADD CONSTRAINT uq_news_source_slug UNIQUE (slug);


--
--

ALTER TABLE ONLY public.province
    ADD CONSTRAINT uq_province_country_code UNIQUE (country_id, code);


--
--

ALTER TABLE ONLY public.saved_places
    ADD CONSTRAINT uq_saved_user_place UNIQUE (user_id, place_id);


--
--

ALTER TABLE ONLY public.school_score
    ADD CONSTRAINT uq_score_school_year UNIQUE (school_id, year, source);


--
--

ALTER TABLE ONLY public.crawl_snapshot
    ADD CONSTRAINT uq_snapshot_entity_hash UNIQUE (entity_type, entity_ref, lang, content_sha256);


--
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
--

CREATE INDEX ix_board_category_board_id ON public.board_category USING btree (board_id);


--
--

CREATE UNIQUE INDEX ix_country_iso2 ON public.country USING btree (iso2);


--
--

CREATE INDEX ix_crawl_snapshot_content_sha256 ON public.crawl_snapshot USING btree (content_sha256);


--
--

CREATE INDEX ix_crawl_snapshot_entity_ref ON public.crawl_snapshot USING btree (entity_ref);


--
--

CREATE INDEX ix_crawl_snapshot_entity_type ON public.crawl_snapshot USING btree (entity_type);


--
--

CREATE INDEX ix_friendships_friend_id ON public.friendships USING btree (friend_id);


--
--

CREATE INDEX ix_friendships_id ON public.friendships USING btree (id);


--
--

CREATE INDEX ix_friendships_user_id ON public.friendships USING btree (user_id);


--
--

CREATE INDEX ix_fuel_price_series_domain ON public.fuel_price_series USING btree (domain);


--
--

CREATE INDEX ix_fuel_price_series_geo ON public.fuel_price_series USING btree (geo);


--
--

CREATE INDEX ix_fuel_price_series_region ON public.fuel_price_series USING btree (region);


--
--

CREATE INDEX ix_fuel_price_series_source ON public.fuel_price_series USING btree (source);


--
--

CREATE INDEX ix_geo_places_country_code ON public.geo_places USING btree (country_code);


--
--

CREATE INDEX ix_geo_places_geom ON public.geo_places USING gist (geom);


--
--

CREATE INDEX ix_geo_places_has_boundary ON public.geo_places USING btree (has_boundary);


--
--

CREATE INDEX ix_geo_places_kind ON public.geo_places USING btree (kind);


--
--

CREATE INDEX ix_geo_places_name ON public.geo_places USING btree (name);


--
--

CREATE INDEX ix_geo_places_source ON public.geo_places USING btree (source);


--
--

CREATE INDEX ix_geocode_cache_query_sha256 ON public.geocode_cache USING btree (query_sha256);


--
--

CREATE INDEX ix_geocode_provider_usage_provider ON public.geocode_provider_usage USING btree (provider);


--
--

CREATE INDEX ix_hazards_expires_at ON public.hazards USING btree (expires_at);


--
--

CREATE INDEX ix_hazards_geom ON public.hazards USING gist (geom);


--
--

CREATE INDEX ix_hazards_reporter_id ON public.hazards USING btree (reporter_id);


--
--

CREATE INDEX ix_hazards_status ON public.hazards USING btree (status);


--
--

CREATE INDEX ix_hazards_type ON public.hazards USING btree (type);


--
--

CREATE INDEX ix_local_content_category ON public.local_content USING btree (category);


--
--

CREATE INDEX ix_local_content_city ON public.local_content USING btree (city);


--
--

CREATE INDEX ix_local_content_content_sha256 ON public.local_content USING btree (content_sha256);


--
--

CREATE INDEX ix_local_content_dedup_key ON public.local_content USING btree (dedup_key);


--
--

CREATE INDEX ix_local_content_event_time ON public.local_content USING btree (event_time);


--
--

CREATE INDEX ix_local_content_expires_at ON public.local_content USING btree (expires_at);


--
--

CREATE INDEX ix_local_content_geom ON public.local_content USING gist (geom);


--
--

CREATE INDEX ix_local_content_location_content_id ON public.local_content_location USING btree (content_id);


--
--

CREATE INDEX ix_local_content_location_geom ON public.local_content_location USING gist (geom);


--
--

CREATE INDEX ix_local_content_publish_time ON public.local_content USING btree (publish_time);


--
--

CREATE INDEX ix_local_content_source_id ON public.local_content USING btree (source_id);


--
--

CREATE INDEX ix_local_content_source_url ON public.local_content USING btree (source_url);


--
--

CREATE INDEX ix_local_content_status ON public.local_content USING btree (status);


--
--

CREATE INDEX ix_local_content_status_type ON public.local_content USING btree (status, type);


--
--

CREATE INDEX ix_local_content_tag_content_id ON public.local_content_tag USING btree (content_id);


--
--

CREATE INDEX ix_local_content_tag_tag ON public.local_content_tag USING btree (tag);


--
--

CREATE INDEX ix_local_content_type ON public.local_content USING btree (type);


--
--

CREATE INDEX ix_maps_consumer_key_prefix ON public.maps_api_consumer USING btree (key_prefix);


--
--

CREATE INDEX ix_maps_usage_consumer_day ON public.maps_api_usage USING btree (consumer_id, day);


--
--

CREATE INDEX ix_neighborhoods_id ON public.neighborhoods USING btree (id);


--
--

CREATE INDEX ix_neighborhoods_name ON public.neighborhoods USING btree (name);


--
--

CREATE INDEX ix_neighborhoods_user_id ON public.neighborhoods USING btree (user_id);


--
--

CREATE INDEX ix_news_source_enabled ON public.news_source USING btree (enabled);


--
--

CREATE INDEX ix_news_source_slug ON public.news_source USING btree (slug);


--
--

CREATE UNIQUE INDEX ix_newsletter_subscribers_email ON public.newsletter_subscribers USING btree (email);


--
--

CREATE INDEX ix_newsletter_subscribers_id ON public.newsletter_subscribers USING btree (id);


--
--

CREATE INDEX ix_notifications_id ON public.notifications USING btree (id);


--
--

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);


--
--

CREATE INDEX ix_place_cards_id ON public.place_cards USING btree (id);


--
--

CREATE INDEX ix_place_cards_kind ON public.place_cards USING btree (kind);


--
--

CREATE UNIQUE INDEX ix_place_cards_publish_token ON public.place_cards USING btree (publish_token);


--
--

CREATE INDEX ix_place_cards_status ON public.place_cards USING btree (status);


--
--

CREATE INDEX ix_place_cards_user_id ON public.place_cards USING btree (user_id);


--
--

CREATE INDEX ix_places_external_id ON public.places USING btree (external_id);


--
--

CREATE INDEX ix_places_geom ON public.places USING gist (geom);


--
--

CREATE INDEX ix_places_id ON public.places USING btree (id);


--
--

CREATE INDEX ix_places_kind ON public.places USING btree (kind);


--
--

CREATE INDEX ix_places_name ON public.places USING btree (name);


--
--

CREATE INDEX ix_places_source ON public.places USING btree (source);


--
--

CREATE INDEX ix_places_user_id ON public.places USING btree (user_id);


--
--

CREATE UNIQUE INDEX ix_program_code ON public.program USING btree (code);


--
--

CREATE INDEX ix_province_country_id ON public.province USING btree (country_id);


--
--

CREATE INDEX ix_routes_id ON public.routes USING btree (id);


--
--

CREATE INDEX ix_routes_user_id ON public.routes USING btree (user_id);


--
--

CREATE INDEX ix_saved_places_id ON public.saved_places USING btree (id);


--
--

CREATE INDEX ix_saved_places_place_id ON public.saved_places USING btree (place_id);


--
--

CREATE INDEX ix_saved_places_user_id ON public.saved_places USING btree (user_id);


--
--

CREATE INDEX ix_school_board_id ON public.school USING btree (board_id);


--
--

CREATE INDEX ix_school_board_province_id ON public.school_board USING btree (province_id);


--
--

CREATE INDEX ix_school_board_type ON public.school_board USING btree (type);


--
--

CREATE INDEX ix_school_boundary_geom ON public.school_boundary USING gist (geom);


--
--

CREATE INDEX ix_school_boundary_is_current ON public.school_boundary USING btree (is_current);


--
--

CREATE INDEX ix_school_boundary_school_id ON public.school_boundary USING btree (school_id);


--
--

CREATE INDEX ix_school_city ON public.school USING btree (city);


--
--

CREATE INDEX ix_school_eqao_school_id ON public.school_eqao USING btree (school_id);


--
--

CREATE UNIQUE INDEX ix_school_hs_id ON public.school USING btree (hs_id);


--
--

CREATE INDEX ix_school_hs_rank ON public.school USING btree (hs_rank);


--
--

CREATE INDEX ix_school_hs_score ON public.school USING btree (hs_score);


--
--

CREATE INDEX ix_school_name ON public.school USING btree (name);


--
--

CREATE INDEX ix_school_province_id ON public.school USING btree (province_id);


--
--

CREATE INDEX ix_school_score_school_id ON public.school_score USING btree (school_id);


--
--

CREATE INDEX ix_school_score_year ON public.school_score USING btree (year);


--
--

CREATE INDEX ix_school_source_id ON public.school USING btree (source_id);


--
--

CREATE INDEX ix_school_type ON public.school USING btree (type);


--
--

CREATE INDEX ix_school_version_content_sha256 ON public.school_version USING btree (content_sha256);


--
--

CREATE INDEX ix_school_version_is_current ON public.school_version USING btree (is_current);


--
--

CREATE INDEX ix_school_version_school_id ON public.school_version USING btree (school_id);


--
--

CREATE INDEX ix_stories_id ON public.stories USING btree (id);


--
--

CREATE INDEX ix_stories_place_id ON public.stories USING btree (place_id);


--
--

CREATE INDEX ix_user_settings_user_id ON public.user_settings USING btree (user_id);


--
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
--

CREATE UNIQUE INDEX ix_users_keycloak_id ON public.users USING btree (keycloak_id);


--
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
--

CREATE UNIQUE INDEX uq_local_content_source_url ON public.local_content USING btree (source_url) WHERE (source_url IS NOT NULL);


--
--

CREATE UNIQUE INDEX uq_maps_consumer_key_hash ON public.maps_api_consumer USING btree (key_hash);


--
--

CREATE UNIQUE INDEX uq_places_source_external ON public.places USING btree (source, external_id) WHERE (external_id IS NOT NULL);


--
--

CREATE UNIQUE INDEX uq_school_prov_board_slug ON public.school USING btree (province_id, COALESCE(board_id, '-1'::integer), slug);


--
--

ALTER TABLE ONLY public.board_category
    ADD CONSTRAINT board_category_board_id_fkey FOREIGN KEY (board_id) REFERENCES public.school_board(id);


--
--

ALTER TABLE ONLY public.neighborhoods
    ADD CONSTRAINT fk_neighborhoods_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
--

ALTER TABLE ONLY public.place_cards
    ADD CONSTRAINT fk_place_cards_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.places
    ADD CONSTRAINT fk_places_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
--

ALTER TABLE ONLY public.user_settings
    ADD CONSTRAINT fk_user_settings_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.friendships
    ADD CONSTRAINT friendships_friend_id_fkey FOREIGN KEY (friend_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.friendships
    ADD CONSTRAINT friendships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.hazards
    ADD CONSTRAINT hazards_reporter_id_fkey FOREIGN KEY (reporter_id) REFERENCES public.users(id);


--
--

ALTER TABLE ONLY public.local_content_location
    ADD CONSTRAINT local_content_location_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.local_content(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.local_content
    ADD CONSTRAINT local_content_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.news_source(id);


--
--

ALTER TABLE ONLY public.local_content_tag
    ADD CONSTRAINT local_content_tag_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.local_content(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.maps_api_usage
    ADD CONSTRAINT maps_api_usage_consumer_id_fkey FOREIGN KEY (consumer_id) REFERENCES public.maps_api_consumer(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.province
    ADD CONSTRAINT province_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.country(id);


--
--

ALTER TABLE ONLY public.routes
    ADD CONSTRAINT routes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.saved_places
    ADD CONSTRAINT saved_places_place_id_fkey FOREIGN KEY (place_id) REFERENCES public.places(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.saved_places
    ADD CONSTRAINT saved_places_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.school_board
    ADD CONSTRAINT school_board_current_snapshot_id_fkey FOREIGN KEY (current_snapshot_id) REFERENCES public.crawl_snapshot(id);


--
--

ALTER TABLE ONLY public.school
    ADD CONSTRAINT school_board_id_fkey FOREIGN KEY (board_id) REFERENCES public.school_board(id);


--
--

ALTER TABLE ONLY public.school_board
    ADD CONSTRAINT school_board_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.province(id);


--
--

ALTER TABLE ONLY public.school_boundary
    ADD CONSTRAINT school_boundary_school_id_fkey FOREIGN KEY (school_id) REFERENCES public.school(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.school_boundary
    ADD CONSTRAINT school_boundary_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.crawl_snapshot(id);


--
--

ALTER TABLE ONLY public.school
    ADD CONSTRAINT school_current_snapshot_id_fkey FOREIGN KEY (current_snapshot_id) REFERENCES public.crawl_snapshot(id);


--
--

ALTER TABLE ONLY public.school_eqao
    ADD CONSTRAINT school_eqao_school_id_fkey FOREIGN KEY (school_id) REFERENCES public.school(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.school_eqao
    ADD CONSTRAINT school_eqao_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.crawl_snapshot(id);


--
--

ALTER TABLE ONLY public.school_program
    ADD CONSTRAINT school_program_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.program(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.school_program
    ADD CONSTRAINT school_program_school_id_fkey FOREIGN KEY (school_id) REFERENCES public.school(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.school
    ADD CONSTRAINT school_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.province(id);


--
--

ALTER TABLE ONLY public.school_score
    ADD CONSTRAINT school_score_school_id_fkey FOREIGN KEY (school_id) REFERENCES public.school(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.school_score
    ADD CONSTRAINT school_score_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.crawl_snapshot(id);


--
--

ALTER TABLE ONLY public.school_version
    ADD CONSTRAINT school_version_school_id_fkey FOREIGN KEY (school_id) REFERENCES public.school(id) ON DELETE CASCADE;


--
--

ALTER TABLE ONLY public.school_version
    ADD CONSTRAINT school_version_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.crawl_snapshot(id);


--
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_place_id_fkey FOREIGN KEY (place_id) REFERENCES public.places(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--
