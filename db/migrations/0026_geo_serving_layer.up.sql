-- Task 26 -- geographic serving layer (additive, idempotent).
-- Adds: geo.boundary_source, geo.boundary_admin_unit, geo.boundary_crosswalk, risk.operational_risk and the views
-- geo.current_boundary, risk.latest_operational_risk, geo.operational_risk_map.
-- Never alters or deletes geo.admin_unit / geo.name_alias / any existing table. Geometry is stored as validated
-- GeoJSON (jsonb) because PostGIS is not installed in this environment; 0026b adds native PostGIS geometry.
-- Rollback: 0026_geo_serving_layer.down.sql

CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS risk;

CREATE TABLE IF NOT EXISTS geo.boundary_source (
    source_id         SERIAL PRIMARY KEY,
    source_key        TEXT NOT NULL UNIQUE,            -- e.g. hdx_cod_ab_pak@v01
    source_name       TEXT NOT NULL,
    publisher         TEXT NOT NULL,
    original_source   TEXT,
    dataset_name      TEXT NOT NULL,
    dataset_version   TEXT NOT NULL,
    valid_on          DATE,
    license           TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    retrieved_at      DATE,
    checksum          TEXT NOT NULL,                   -- sha256 of the downloaded archive
    crs               TEXT NOT NULL,
    government_certified BOOLEAN NOT NULL DEFAULT FALSE,
    validation_json   JSONB,
    notes             TEXT,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS geo.boundary_admin_unit (
    boundary_id         SERIAL PRIMARY KEY,
    source_id           INTEGER NOT NULL REFERENCES geo.boundary_source(source_id),
    source_feature_id   TEXT NOT NULL,                 -- e.g. COD-AB p-code
    name                TEXT NOT NULL,
    level               SMALLINT NOT NULL CHECK (level IN (0, 1, 2)),
    parent_boundary_id  INTEGER REFERENCES geo.boundary_admin_unit(boundary_id),
    geometry_geojson    JSONB,                         -- GeoJSON geometry, WGS84 (CRS84), as published (no repair)
    geometry_type       TEXT,
    geometry_valid      BOOLEAN NOT NULL,
    validation_notes    TEXT,
    properties_json     JSONB,
    UNIQUE (source_id, level, source_feature_id)
);
CREATE INDEX IF NOT EXISTS ix_boundary_unit_level ON geo.boundary_admin_unit (source_id, level);
CREATE INDEX IF NOT EXISTS ix_boundary_unit_parent ON geo.boundary_admin_unit (parent_boundary_id);

CREATE TABLE IF NOT EXISTS geo.boundary_crosswalk (
    crosswalk_id        SERIAL PRIMARY KEY,
    boundary_id         INTEGER NOT NULL UNIQUE REFERENCES geo.boundary_admin_unit(boundary_id),
    pori_admin_unit_id  INTEGER REFERENCES geo.admin_unit(id),   -- NULL when unmatched/ambiguous
    match_status        TEXT NOT NULL CHECK (match_status IN ('exact', 'alias', 'manual_verified', 'ambiguous', 'unmatched')),
    match_basis         TEXT NOT NULL,
    confidence          TEXT,
    source_id           INTEGER NOT NULL REFERENCES geo.boundary_source(source_id),
    validation_status   TEXT,
    notes               TEXT,
    CHECK ((match_status IN ('exact', 'alias', 'manual_verified')) = (pori_admin_unit_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_boundary_crosswalk_unit ON geo.boundary_crosswalk (pori_admin_unit_id);
CREATE INDEX IF NOT EXISTS ix_boundary_crosswalk_status ON geo.boundary_crosswalk (match_status);

CREATE TABLE IF NOT EXISTS risk.operational_risk (
    admin_unit_id          INTEGER NOT NULL REFERENCES geo.admin_unit(id),
    risk_date              DATE NOT NULL,
    admin_unit_name        TEXT,
    admin_level            SMALLINT,
    province               TEXT,
    risk_status            TEXT NOT NULL CHECK (risk_status IN ('NO_SIGNAL', 'INSUFFICIENT_DATA', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL')),
    risk_basis             TEXT,
    risk_score             NUMERIC,                    -- NULL in engine v1.0.0 (no evidence-based weights)
    risk_confidence        TEXT,
    rainfall_signal        DOUBLE PRECISION,
    weather_signal         DOUBLE PRECISION,
    gauge_signal           DOUBLE PRECISION,
    air_quality_signal     DOUBLE PRECISION,
    hazard_alert_signal    DOUBLE PRECISION,
    disaster_event_signal  DOUBLE PRECISION,
    active_signal_count    INTEGER,
    observed_signal_count  INTEGER,
    missing_signal_count   INTEGER,
    top_risk_domain        TEXT,
    top_risk_contribution  DOUBLE PRECISION,
    data_coverage_pct      NUMERIC,
    source_count           INTEGER,
    source_record_count    INTEGER,
    signal_states          JSONB,
    business_signals       JSONB,
    ml_forecast_available  BOOLEAN,
    ml_reference_model     TEXT,
    ml_unavailable_reason  TEXT,
    calculation_version    TEXT NOT NULL,
    engine_version         TEXT,
    threshold_status       TEXT,
    is_current             BOOLEAN NOT NULL DEFAULT TRUE,   -- FALSE = absent from the latest engine load (never deleted)
    loaded_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (admin_unit_id, risk_date)
);
CREATE INDEX IF NOT EXISTS ix_operational_risk_date ON risk.operational_risk (risk_date) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_operational_risk_status ON risk.operational_risk (risk_status) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_operational_risk_province ON risk.operational_risk (province) WHERE is_current;

-- latest available risk date per canonical admin unit (no reference to today's date)
CREATE OR REPLACE VIEW risk.latest_operational_risk AS
SELECT DISTINCT ON (r.admin_unit_id) r.*
FROM risk.operational_risk r
WHERE r.is_current
ORDER BY r.admin_unit_id, r.risk_date DESC;

-- one current boundary per canonical unit: only matched crosswalk rows (exact/alias/manual_verified) with valid geometry
CREATE OR REPLACE VIEW geo.current_boundary AS
SELECT DISTINCT ON (cw.pori_admin_unit_id)
       cw.pori_admin_unit_id, b.boundary_id, b.source_id, b.source_feature_id AS boundary_feature_id,
       b.name AS boundary_name, b.level AS boundary_level, b.geometry_geojson, b.geometry_type,
       s.dataset_name AS boundary_source, s.dataset_version AS boundary_version, s.valid_on AS boundary_valid_on,
       cw.match_status, cw.match_basis, cw.confidence AS match_confidence
FROM geo.boundary_crosswalk cw
JOIN geo.boundary_admin_unit b ON b.boundary_id = cw.boundary_id
JOIN geo.boundary_source s ON s.source_id = b.source_id
WHERE cw.match_status IN ('exact', 'alias', 'manual_verified')
  AND cw.pori_admin_unit_id IS NOT NULL AND b.geometry_valid AND b.geometry_geojson IS NOT NULL
ORDER BY cw.pori_admin_unit_id, s.valid_on DESC NULLS LAST, s.source_id DESC;

-- map/API view: every canonical province/district, its boundary geometry (NULL if none) and its latest risk (NULL if none)
CREATE OR REPLACE VIEW geo.operational_risk_map AS
SELECT u.id AS admin_unit_id, u.name AS admin_unit_name, u.level AS admin_level,
       CASE WHEN u.level = 1 THEN u.name ELSE p.name END AS province,
       cb.geometry_geojson AS geometry, cb.boundary_source, cb.boundary_version, cb.boundary_feature_id,
       cb.match_status AS boundary_match_status,
       r.risk_date, r.risk_status, r.risk_score, r.risk_confidence, r.risk_basis, r.top_risk_domain,
       r.data_coverage_pct, r.calculation_version
FROM geo.admin_unit u
LEFT JOIN geo.admin_unit p ON p.id = u.parent_id AND p.level = 1
LEFT JOIN geo.current_boundary cb ON cb.pori_admin_unit_id = u.id
LEFT JOIN risk.latest_operational_risk r ON r.admin_unit_id = u.id
WHERE u.level IN (1, 2);
