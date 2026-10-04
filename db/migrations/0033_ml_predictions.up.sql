-- Task 33 -- ML prediction layer storage (additive, idempotent). Separate schema `ml`: nothing in risk.*, geo.*, rag.*, dq.* or any other existing
-- table is read-modified or altered. Predictions are FUTURE values of observed quantities, never risk statuses; the risk engine is not touched.
-- Rollback: 0033_ml_predictions.down.sql

CREATE SCHEMA IF NOT EXISTS ml;

CREATE TABLE IF NOT EXISTS ml.model_runs (
    model_run_id              TEXT PRIMARY KEY,                  -- <target>-h<horizon>-<data fingerprint prefix>: re-running the same data is idempotent
    target                    TEXT NOT NULL,
    domain                    TEXT NOT NULL,
    unit                      TEXT,
    horizon_days              INTEGER NOT NULL CHECK (horizon_days >= 1),
    model_name                TEXT NOT NULL,                     -- the deployed predictor ('none' when no model could be built)
    model_version             TEXT NOT NULL,
    model_type                TEXT NOT NULL CHECK (model_type IN ('ml', 'baseline', 'none')),
    status                    TEXT NOT NULL CHECK (status IN ('VALIDATED', 'BASELINE_ONLY', 'NO_MODEL')),
    validated_against_baseline BOOLEAN NOT NULL,
    as_of                     DATE NOT NULL,                     -- the dataset's own latest observation date (not the wall clock)
    feature_cutoff            DATE NOT NULL,
    training_cutoff           DATE,
    train_start               DATE, train_end DATE,
    validation_start          DATE, validation_end DATE,
    test_start                DATE, test_end DATE,
    n_train                   INTEGER, n_validation INTEGER, n_test INTEGER,
    metrics                   JSONB,
    metadata                  JSONB NOT NULL DEFAULT '{}',
    is_current                BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ml_model_runs_target ON ml.model_runs (target, horizon_days) WHERE is_current;

CREATE TABLE IF NOT EXISTS ml.predictions (
    model_run_id     TEXT NOT NULL REFERENCES ml.model_runs(model_run_id),
    entity_type      TEXT NOT NULL,
    entity_id        TEXT NOT NULL,
    admin_unit_id    INTEGER REFERENCES geo.admin_unit(id),
    horizon_days     INTEGER NOT NULL CHECK (horizon_days >= 1),
    prediction_date  DATE NOT NULL,                              -- the date the prediction is FOR
    feature_cutoff   DATE NOT NULL,                              -- last observation date the features could use
    target           TEXT NOT NULL,
    unit             TEXT,
    prediction       DOUBLE PRECISION,                           -- NULL when status = INSUFFICIENT_DATA
    status           TEXT NOT NULL CHECK (status IN ('PREDICTED', 'BASELINE_ONLY', 'INSUFFICIENT_DATA')),
    reason           TEXT,
    model_name       TEXT, model_version TEXT,
    model_type       TEXT NOT NULL CHECK (model_type IN ('ml', 'baseline', 'none')),
    training_cutoff  DATE,
    provenance       JSONB NOT NULL,
    is_current       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (model_run_id, entity_id, horizon_days),
    CHECK ((status = 'INSUFFICIENT_DATA') = (prediction IS NULL)),
    CHECK (feature_cutoff < prediction_date)
);
CREATE INDEX IF NOT EXISTS ix_ml_predictions_unit ON ml.predictions (admin_unit_id, horizon_days) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_ml_predictions_date ON ml.predictions (prediction_date) WHERE is_current;
