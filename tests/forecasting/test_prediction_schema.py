"""
tests/forecasting/test_prediction_schema.py

Phase 1 / Task 9 (ADR-0001) -- end-to-end (minus the database) test of
the feature -> model -> prediction-record pipeline, and a fault-
injection-style guard proving a record with a missing station name is
never written to the output.

Uses tests/fixtures/forecasting/gauge_readings_sample.json -- 10 REAL
(station, river, report_datetime, discharge_cusecs) rows for the
Marala/CHENAB gauge, read live from pdma_gauge_readings during Task 9
data profiling (see tests/fixtures/README.md for provenance). No live
database connection is made in this test; no internet access; fully
deterministic (LinearRegression's ordinary-least-squares fit has no
randomness).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LinearRegression

from scripts.forecasting.features import LAG_FEATURE_COLUMNS, build_lag_features
from scripts.forecasting.gauge_discharge_forecast import (
    build_prediction_records,
    make_feature_matrix,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "forecasting" / "gauge_readings_sample.json"
)

REQUIRED_KEYS = {
    "station",
    "river",
    "based_on_report_datetime",
    "forecast_for",
    "predicted_discharge_cusecs",
    "model_name",
    "model_version",
    "source",
    "generated_at",
}


def _load_fixture_df() -> pd.DataFrame:
    records = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    df = pd.DataFrame(records)
    df["report_datetime"] = pd.to_datetime(df["report_datetime"])
    return df


def _fit_tiny_model_and_predict_latest():
    readings = _load_fixture_df()
    featured = build_lag_features(readings)
    complete = featured.dropna(subset=LAG_FEATURE_COLUMNS + ["discharge_cusecs"]).reset_index(drop=True)
    assert len(complete) > 0, "fixture must yield at least one feature-complete row"

    dummy_columns = pd.get_dummies(complete["station"], prefix="station", dtype=int).columns
    X = make_feature_matrix(complete, dummy_columns)
    y = complete["discharge_cusecs"].reset_index(drop=True)

    model = LinearRegression()
    model.fit(X, y)

    latest = (
        featured.dropna(subset=LAG_FEATURE_COLUMNS)
        .sort_values("report_datetime")
        .groupby("station", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    X_latest = make_feature_matrix(latest, dummy_columns)
    predicted = model.predict(X_latest)
    return latest, predicted


def test_predictions_have_required_keys_and_types():
    latest, predicted = _fit_tiny_model_and_predict_latest()
    records = build_prediction_records(
        latest, predicted, "gauge_discharge_forecast", "2026-09-11", "pdma_gauge_readings", "2026-09-11T00:00:00+00:00"
    )

    assert len(records) == 1  # single-station fixture -> exactly one forward record
    record = records[0]

    assert set(record.keys()) == REQUIRED_KEYS
    assert record["station"] == "Marala"
    assert record["river"] == "CHENAB"
    assert isinstance(record["predicted_discharge_cusecs"], float)
    assert isinstance(record["based_on_report_datetime"], str)
    assert isinstance(record["generated_at"], str)
    assert record["model_name"] == "gauge_discharge_forecast"
    assert record["source"] == "pdma_gauge_readings"


def test_predictions_are_json_serializable():
    latest, predicted = _fit_tiny_model_and_predict_latest()
    records = build_prediction_records(
        latest, predicted, "gauge_discharge_forecast", "2026-09-11", "pdma_gauge_readings", "2026-09-11T00:00:00+00:00"
    )
    # Must not raise -- every value has to be a plain JSON-representable
    # type (no numpy scalars, no pandas Timestamps left un-stringified).
    json.dumps(records)


def test_predictions_skip_record_with_missing_station():
    """
    Fault-injection-style guard: a row with a missing/NULL/empty
    station name must never be written to the output, even if it
    somehow reached build_prediction_records() (defense in depth --
    normal operation already filters this out at the SQL layer via
    `station IS NOT NULL`).
    """
    latest = pd.DataFrame(
        {
            "station": [None],
            "river": ["CHENAB"],
            "report_datetime": [pd.Timestamp("2026-06-18T12:00:00")],
        }
    )
    records = build_prediction_records(
        latest, [12345.6], "gauge_discharge_forecast", "2026-09-11", "pdma_gauge_readings", "2026-09-11T00:00:00+00:00"
    )
    assert records == []


def test_predictions_skip_record_with_blank_station():
    latest = pd.DataFrame(
        {
            "station": ["   "],
            "river": ["CHENAB"],
            "report_datetime": [pd.Timestamp("2026-06-18T12:00:00")],
        }
    )
    records = build_prediction_records(
        latest, [12345.6], "gauge_discharge_forecast", "2026-09-11", "pdma_gauge_readings", "2026-09-11T00:00:00+00:00"
    )
    assert records == []
