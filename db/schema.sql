-- =============================================================================
-- whereq.com — Database Schema
-- PostgreSQL 17
-- Generated: 2026-05-24
-- =============================================================================

-- Run against the whereq-com database:
--   psql -U whereq -d whereq-com -f db/schema.sql

-- ── Users ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(64) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    locale          VARCHAR(8) DEFAULT 'en',
    theme           VARCHAR(8) DEFAULT 'dark',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ── Places ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS places (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    address         VARCHAR(512),
    city            VARCHAR(128),
    country         VARCHAR(128),
    category        VARCHAR(64) DEFAULT 'general',
    kind            VARCHAR(32) DEFAULT 'poi',
    sub             VARCHAR(255),
    metadata_json   JSONB DEFAULT '{}',
    view_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_places_name ON places(name);
CREATE INDEX IF NOT EXISTS idx_places_kind ON places(kind);

-- ── Neighborhoods ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS neighborhoods (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    city                VARCHAR(128),
    country             VARCHAR(128),
    boundary_geojson    JSONB,
    walkability_score   INTEGER DEFAULT 0,
    transit_score       INTEGER DEFAULT 0,
    food_score          INTEGER DEFAULT 0,
    schools_score       INTEGER DEFAULT 0,
    overall_score       INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_neighborhoods_name ON neighborhoods(name);

-- ── Routes ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS routes (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name                VARCHAR(255) NOT NULL,
    description         TEXT,
    waypoints           JSONB DEFAULT '[]',
    total_distance_km   DOUBLE PRECISION,
    duration_minutes    INTEGER,
    is_public           BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_routes_user_id ON routes(user_id);

-- ── Stories ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stories (
    id          SERIAL PRIMARY KEY,
    place_id    INTEGER REFERENCES places(id) ON DELETE CASCADE,
    author_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title       VARCHAR(255) NOT NULL,
    content     TEXT NOT NULL,
    category    VARCHAR(64) DEFAULT 'personal',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stories_place_id ON stories(place_id);

-- ── Saved Places ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_places (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    place_id    INTEGER REFERENCES places(id) ON DELETE CASCADE,
    label       VARCHAR(128),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, place_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_places_user_id ON saved_places(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_places_place_id ON saved_places(place_id);

-- ── Notifications ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(255) NOT NULL,
    body        TEXT,
    kind        VARCHAR(32) DEFAULT 'info',
    is_read     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);

-- ── Friendships ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS friendships (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    friend_id   INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status      VARCHAR(16) DEFAULT 'pending',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, friend_id)
);
CREATE INDEX IF NOT EXISTS idx_friendships_user_id ON friendships(user_id);
CREATE INDEX IF NOT EXISTS idx_friendships_friend_id ON friendships(friend_id);

-- ── Newsletter Subscribers ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_newsletter_email ON newsletter_subscribers(email);

-- ── Alembic version tracking ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('001_initial')
    ON CONFLICT DO NOTHING;
