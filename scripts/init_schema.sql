-- ============================================================
-- SkyView Property Bot — PostgreSQL Schema
-- Run once: psql $POSTGRES_DSN -f scripts/init_schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ------------------------------------------------------------
-- general_policies: single-row table for property-wide settings
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS general_policies (
    row_id                INTEGER      PRIMARY KEY DEFAULT 1,
    pet_policy            TEXT         NOT NULL,
    checkout_time         VARCHAR(20)  NOT NULL,
    checkin_time          VARCHAR(20)  NOT NULL,
    late_checkout_policy  TEXT         NOT NULL,
    early_checkin_policy  TEXT         NOT NULL,
    noise_policy          TEXT         NOT NULL,
    visitor_policy        TEXT         NOT NULL,
    suite_directory       TEXT         NOT NULL,
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT single_row CHECK (row_id = 1)
);

-- ------------------------------------------------------------
-- buildings: one row per building
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS buildings (
    building_id  VARCHAR(50)   PRIMARY KEY,
    name         VARCHAR(100)  NOT NULL,
    address      TEXT          NOT NULL,
    amenities    JSONB         NOT NULL DEFAULT '[]',
    lift_access  TEXT          NOT NULL,
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- units: one row per rentable unit
-- Composite PK because unit_id is only unique within a building
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS units (
    building_id           VARCHAR(50)    NOT NULL REFERENCES buildings(building_id) ON DELETE RESTRICT,
    unit_id               VARCHAR(20)    NOT NULL,
    suite_name            VARCHAR(100)   NOT NULL,
    description           TEXT           NOT NULL,
    room_type             VARCHAR(50)    NOT NULL,
    floor                 SMALLINT       NOT NULL,
    max_pax               SMALLINT       NOT NULL,
    price_per_night       NUMERIC(10,2)  NOT NULL,
    wifi_ssid             VARCHAR(100)   NOT NULL,
    wifi_password         VARCHAR(100)   NOT NULL,
    parking_bay           VARCHAR(20),
    checkin_code          VARCHAR(20)    NOT NULL,
    extra_beds_available  BOOLEAN        NOT NULL DEFAULT FALSE,
    extra_bed_fee         VARCHAR(100),
    created_at            TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (building_id, unit_id)
);

CREATE INDEX IF NOT EXISTS idx_units_building   ON units(building_id);
CREATE INDEX IF NOT EXISTS idx_units_room_type  ON units(room_type);
CREATE INDEX IF NOT EXISTS idx_units_price      ON units(price_per_night);

-- ------------------------------------------------------------
-- guests: one row per unique phone number
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS guests (
    phone          VARCHAR(30)  PRIMARY KEY,
    language_pref  VARCHAR(10)  NOT NULL DEFAULT 'en',
    first_seen_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guests_last_active ON guests(last_active_at DESC);

-- ------------------------------------------------------------
-- bookings: one row per booking, created on BOOKED transition
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    booking_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    phone          VARCHAR(30)  NOT NULL REFERENCES guests(phone) ON DELETE RESTRICT,
    building_id    VARCHAR(50)  NOT NULL,
    unit_id        VARCHAR(20)  NOT NULL,
    status         VARCHAR(20)  NOT NULL DEFAULT 'confirmed'
                       CHECK (status IN ('confirmed','cancelled','checked_in','checked_out','no_show')),
    check_in_date  DATE,
    check_out_date DATE,
    guest_count    SMALLINT,
    booked_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    notes          TEXT,
    FOREIGN KEY (building_id, unit_id) REFERENCES units(building_id, unit_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_bookings_phone    ON bookings(phone);
CREATE INDEX IF NOT EXISTS idx_bookings_unit     ON bookings(building_id, unit_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status   ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_bookings_booked   ON bookings(booked_at DESC);

-- ------------------------------------------------------------
-- sessions: persistent conversation state (replaces in-memory dict)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    phone       VARCHAR(30)  PRIMARY KEY REFERENCES guests(phone) ON DELETE CASCADE,
    state       VARCHAR(20)  NOT NULL DEFAULT 'UNKNOWN'
                    CHECK (state IN ('UNKNOWN','PRE_BOOKING','BOOKED')),
    building    VARCHAR(50)  REFERENCES buildings(building_id) ON DELETE SET NULL,
    unit        VARCHAR(20),
    language    VARCHAR(10)  NOT NULL DEFAULT 'en',
    history     JSONB        NOT NULL DEFAULT '[]',
    booking_id  UUID         REFERENCES bookings(booking_id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_state    ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_building ON sessions(building);

-- ------------------------------------------------------------
-- interaction_logs: append-only log (replaces JSONL files)
-- No FK on phone — logs are immutable history even if guest is deleted
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interaction_logs (
    id                BIGSERIAL    PRIMARY KEY,
    logged_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    phone             VARCHAR(30)  NOT NULL,
    question          TEXT         NOT NULL,
    language_detected VARCHAR(10)  NOT NULL,
    guest_state       VARCHAR(20)  NOT NULL,
    building          VARCHAR(50),
    unit              VARCHAR(20),
    intent            VARCHAR(50)  NOT NULL,
    context           JSONB        NOT NULL DEFAULT '{}',
    model             VARCHAR(100) NOT NULL,
    prompt_version    VARCHAR(20)  NOT NULL,
    response          TEXT         NOT NULL,
    latency_ms        INTEGER      NOT NULL,
    input_tokens      INTEGER      NOT NULL,
    output_tokens     INTEGER      NOT NULL,
    booking_id        UUID
);

CREATE INDEX IF NOT EXISTS idx_logs_phone      ON interaction_logs(phone);
CREATE INDEX IF NOT EXISTS idx_logs_logged_at  ON interaction_logs(logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_intent     ON interaction_logs(intent);
CREATE INDEX IF NOT EXISTS idx_logs_model      ON interaction_logs(model);
