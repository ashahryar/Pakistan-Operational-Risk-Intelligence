"""
scripts/forecasting/gauge_discharge_forecast.py

Phase 1 / Task 9 (ADR-0001) -- baseline, classical, chronologically-
evaluated one-report-ahead discharge forecast for PDMA river gauge
stations.

TARGET VARIABLE NOTE (why discharge_cusecs, not current_level_ft):
Live data profiling on 2026-09-11 found that pdma_gauge_readings'
current_level_ft (and danger_level_ft) columns are effectively constant
per station across their entire history -- e.g. Marala reads exactly
11 for all 314 readings spanning 81 days; only 2 distinct values exist
per station over the whole range. This is consistent with the
documented parse_gauge.py hard-coded-column defect (extracting a fixed
reference/design value rather than the fluctuating daily reading).
Forecasting a constant is not a real forecast, so the originally
planned target was replaced with discharge_cusecs, which IS genuinely
time-varying (100+ distinct values per station) and physically
plausible in magnitude. See docs/ml/FORECASTING_BASELINE.md.

WHAT THIS SCRIPT DOES (run standalone, matches the existing
parser/loader script convention -- no DAG wiring in Task 9):

  1. Reads pdma_gauge_readings (read-only) and selects, live, every
     (station, river) pair that clears a minimum data-completeness bar
     -- no station list is hard-coded, so this stays correct as new
     data lands.
  2. Builds leakage-free lag/rolling features (scripts/forecasting/
     features.py) and computes a chronological (never random) 70/15/15
     train/validation/test split.
  3. Fits a persistence baseline (predicted = last reading) and a
     scikit-learn LinearRegression on lag features + station identity,
     and reports MAE/RMSE/skill-score for both, on all three splits.
  4. Saves the fitted model + a metadata.json (features, stations,
     date ranges, metrics, sklearn version, git commit) under
     data/models/gauge_discharge_forecast/<version>/.
  5. Writes one forward (next-report) prediction per qualifying station
     to data/analytics/pdma/gauge_discharge_forecast.json, matching
     the existing data/analytics/<source>/*.json house style.

No database WRITE happens anywhere in this script -- every query is a
plain SELECT. No DAG references this script (Task 9 proves the model
locally first, per the approved plan).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sqlalchemy import bindparam, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from config.database import engine  # noqa: E402
from config.path import ANALYTICS_DATA, MODELS_DATA  # noqa: E402
from scripts.forecasting.features import (  # noqa: E402
    LAG_FEATURE_COLUMNS,
    build_lag_features,
    chronological_split,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

MODEL_NAME = "gauge_discharge_forecast"
MODEL_VERSION = datetime.now().strftime("%Y-%m-%d")

TARGET_COLUMN = "discharge_cusecs"
MIN_USABLE_READINGS = 50
MIN_DATE_SPAN_DAYS = 30
TRAIN_PCT = 0.70
VAL_PCT = 0.15


# ==========================================================
# DATA ACCESS (read-only)
# ==========================================================

def _query_to_dataframe(conn, query, params) -> pd.DataFrame:
    """
    Runs `query` via `conn.execute()` and materializes the result as a
    DataFrame by hand, deliberately NOT using pandas.read_sql().

    Why: pandas 3.0.5's SQLAlchemy-connectable detection
    (pandas.io.sql.pandasSQL_builder) calls
    `import_optional_dependency("sqlalchemy")`, which silently returns
    None against the SQLAlchemy 1.4.52 this project's Airflow image
    pins (Airflow 2.9.x requires SQLAlchemy <2.0) -- pandas then treats
    a real SQLAlchemy engine/connection as an untested bare DBAPI2
    object and raises `TypeError: Query must be a string unless using
    sqlalchemy.` on a `text()` query. This is a real, confirmed
    pandas/SQLAlchemy version mismatch in the existing image, not a
    bug in this script -- upgrading SQLAlchemy is out of scope (it is
    an Airflow-pinned core dependency; CLAUDE.md rule 8). Using
    `conn.execute()` directly (the same pattern scripts/database/
    load_pdma.py already uses for its INSERTs) sidesteps pandas'
    connectable-detection path entirely.
    """
    result = conn.execute(query, params)
    return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


def select_qualifying_stations() -> pd.DataFrame:
    """
    Live, data-driven station selection: every (station, river) pair
    with at least MIN_USABLE_READINGS non-null-target, non-null-
    timestamp readings spanning at least MIN_DATE_SPAN_DAYS. No station
    name is hard-coded here.
    """
    query = text("""
        SELECT station, river,
               count(*) AS usable_readings,
               min(report_datetime) AS first_reading,
               max(report_datetime) AS last_reading
        FROM pdma_gauge_readings
        WHERE discharge_cusecs IS NOT NULL
          AND report_datetime IS NOT NULL
          AND station IS NOT NULL
        GROUP BY station, river
        HAVING count(*) >= :min_readings
           AND (max(report_datetime) - min(report_datetime)) >= make_interval(days => :min_days)
        ORDER BY usable_readings DESC
    """)
    with engine.connect() as conn:
        return _query_to_dataframe(
            conn, query, {"min_readings": MIN_USABLE_READINGS, "min_days": MIN_DATE_SPAN_DAYS}
        )


def load_readings(stations: pd.DataFrame) -> pd.DataFrame:
    """
    Pulls every non-null-target, non-null-timestamp reading for exactly
    the qualifying (station, river) pairs returned by
    select_qualifying_stations().
    """
    columns = ["station", "river", "report_datetime", "discharge_cusecs"]
    if stations.empty:
        return pd.DataFrame(columns=columns)

    station_names = sorted(stations["station"].unique().tolist())
    query = text("""
        SELECT station, river, report_datetime, discharge_cusecs
        FROM pdma_gauge_readings
        WHERE discharge_cusecs IS NOT NULL
          AND report_datetime IS NOT NULL
          AND station IN :stations
        ORDER BY station, report_datetime
    """).bindparams(bindparam("stations", expanding=True))

    with engine.connect() as conn:
        df = _query_to_dataframe(conn, query, {"stations": station_names})

    # Keep only the exact (station, river) pairs that actually qualified
    # -- a station name paired with a different, non-qualifying river
    # value elsewhere in the table must not silently sneak in.
    qualifying_pairs = set(zip(stations["station"], stations["river"]))
    mask = df.apply(lambda r: (r["station"], r["river"]) in qualifying_pairs, axis=1)
    return df[mask].reset_index(drop=True)


# ==========================================================
# FEATURE MATRIX
# ==========================================================

def make_feature_matrix(df: pd.DataFrame, dummy_columns: pd.Index) -> pd.DataFrame:
    """
    Builds the model input matrix: the numeric lag features plus a
    one-hot station dummy, reindexed to `dummy_columns` so train/val/
    test/prediction matrices always share the exact same columns in
    the exact same order.
    """
    dummies = pd.get_dummies(df["station"], prefix="station", dtype=int)
    dummies = dummies.reindex(columns=dummy_columns, fill_value=0)
    return pd.concat(
        [df[LAG_FEATURE_COLUMNS].reset_index(drop=True), dummies.reset_index(drop=True)],
        axis=1,
    )


def evaluate(y_true, y_pred) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
    }


def build_prediction_records(
    latest_df: pd.DataFrame,
    predicted_values,
    model_name: str,
    model_version: str,
    source: str,
    generated_at: str,
) -> list[dict]:
    """
    Pure function: pairs each row of `latest_df` (one row per station,
    already feature-complete) with its corresponding predicted value
    and returns the flat, JSON-ready record list written to
    data/analytics/pdma/gauge_discharge_forecast.json.

    Defensive guard (fault-injection-style, tested directly in
    tests/forecasting/test_prediction_schema.py): a row with a missing/
    NULL/empty station name is skipped, never written to the output --
    in normal operation this can't happen (load_readings() already
    filters `station IS NOT NULL` at the SQL level), but this function
    does not trust its caller and re-checks anyway.
    """
    records = []
    for (_, row), predicted in zip(latest_df.iterrows(), predicted_values):
        station = row.get("station")
        if station is None or (isinstance(station, float) and pd.isna(station)) or not str(station).strip():
            continue
        records.append(
            {
                "station": station,
                "river": row["river"],
                "based_on_report_datetime": row["report_datetime"].isoformat(),
                "forecast_for": "next_report",
                "predicted_discharge_cusecs": round(float(predicted), 1),
                "model_name": model_name,
                "model_version": model_version,
                "source": source,
                "generated_at": generated_at,
            }
        )
    return records


# ==========================================================
# MAIN
# ==========================================================

def main():
    print("=" * 60)
    print("GAUGE DISCHARGE FORECAST -- TASK 9 BASELINE")
    print("=" * 60)

    stations = select_qualifying_stations()
    print(
        f"Qualifying stations (>= {MIN_USABLE_READINGS} readings, "
        f">= {MIN_DATE_SPAN_DAYS} days span): {len(stations)}"
    )

    if stations.empty:
        print("=" * 60)
        print("NO STATIONS MEET THE COMPLETENESS THRESHOLD -- ABORTING")
        print("No model trained, no predictions written. See the")
        print("documented fallback in docs/ml/FORECASTING_BASELINE.md.")
        print("=" * 60)
        sys.exit(1)

    for _, row in stations.iterrows():
        print(
            f"  {row['station']:<15} {row['river']:<10} "
            f"readings={row['usable_readings']:<5} "
            f"{row['first_reading']} -> {row['last_reading']}"
        )

    readings = load_readings(stations)
    print(f"Total readings loaded: {len(readings)}")

    featured = build_lag_features(readings)
    complete = featured.dropna(subset=LAG_FEATURE_COLUMNS + [TARGET_COLUMN]).reset_index(drop=True)
    print(f"Rows usable after lag/rolling feature computation: {len(complete)}")

    train_df, val_df, test_df = chronological_split(complete, train_pct=TRAIN_PCT, val_pct=VAL_PCT)
    print(f"Train: {len(train_df)}  Val: {len(val_df)}  Test: {len(test_df)}")

    if train_df.empty or test_df.empty:
        print("Insufficient data for a chronological split -- aborting.")
        sys.exit(1)

    print(f"Train range: {train_df['report_datetime'].min()} -> {train_df['report_datetime'].max()}")
    if not val_df.empty:
        print(f"Val   range: {val_df['report_datetime'].min()} -> {val_df['report_datetime'].max()}")
    print(f"Test  range: {test_df['report_datetime'].min()} -> {test_df['report_datetime'].max()}")

    dummy_columns = pd.get_dummies(complete["station"], prefix="station", dtype=int).columns
    station_list = sorted(complete["station"].unique().tolist())

    X_train = make_feature_matrix(train_df, dummy_columns)
    y_train = train_df[TARGET_COLUMN].reset_index(drop=True)
    X_val = make_feature_matrix(val_df, dummy_columns)
    y_val = val_df[TARGET_COLUMN].reset_index(drop=True)
    X_test = make_feature_matrix(test_df, dummy_columns)
    y_test = test_df[TARGET_COLUMN].reset_index(drop=True)

    model = LinearRegression()
    model.fit(X_train, y_train)

    metrics = {"persistence": {}, "linear_regression": {}}
    splits = {"train": (X_train, y_train, train_df), "val": (X_val, y_val, val_df), "test": (X_test, y_test, test_df)}
    for split_name, (X_split, y_split, df_split) in splits.items():
        if df_split.empty:
            continue
        persistence_pred = df_split["lag_1"].reset_index(drop=True)
        linreg_pred = model.predict(X_split)
        metrics["persistence"][split_name] = evaluate(y_split, persistence_pred)
        metrics["linear_regression"][split_name] = evaluate(y_split, linreg_pred)

    test_persistence_mae = metrics["persistence"]["test"]["mae"]
    test_linreg_mae = metrics["linear_regression"]["test"]["mae"]
    skill_score = (1 - (test_linreg_mae / test_persistence_mae)) if test_persistence_mae > 0 else None

    print("=" * 60)
    print("METRICS (MAE / RMSE, cusecs)")
    for split_name in ("train", "val", "test"):
        if split_name not in metrics["persistence"]:
            continue
        p = metrics["persistence"][split_name]
        l = metrics["linear_regression"][split_name]
        print(
            f"  {split_name:<5} persistence MAE={p['mae']:.1f} RMSE={p['rmse']:.1f}  "
            f"linreg MAE={l['mae']:.1f} RMSE={l['rmse']:.1f}"
        )
    print(f"Skill score (test, 1 - linreg_mae/persistence_mae): {skill_score}")
    print("=" * 60)

    # ------------------------------------------------------
    # SAVE MODEL ARTIFACT + METADATA
    # ------------------------------------------------------
    model_dir = MODELS_DATA / MODEL_NAME / MODEL_VERSION
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "model.joblib"
    joblib.dump({"model": model, "feature_columns": list(X_train.columns)}, model_path)

    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        # .git is not mounted into the Airflow container (docker-compose.yml
        # only mounts specific project subdirectories), so this is expected
        # to fail with "not a git repository" when run inside the container
        # -- caught, not fatal. Metadata.json's git_commit is simply null
        # in that case; run on the host to capture a real commit hash.
        git_commit = None

    metadata = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "target_variable": TARGET_COLUMN,
        "source_table": "pdma_gauge_readings",
        "min_usable_readings": MIN_USABLE_READINGS,
        "min_date_span_days": MIN_DATE_SPAN_DAYS,
        "stations": station_list,
        "feature_columns": list(X_train.columns),
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "test_rows": len(test_df),
        "train_range": [str(train_df["report_datetime"].min()), str(train_df["report_datetime"].max())],
        "val_range": (
            [str(val_df["report_datetime"].min()), str(val_df["report_datetime"].max())]
            if not val_df.empty else None
        ),
        "test_range": [str(test_df["report_datetime"].min()), str(test_df["report_datetime"].max())],
        "metrics": metrics,
        "skill_score_test": skill_score,
        "sklearn_version": sklearn.__version__,
        "git_commit": git_commit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=4), encoding="utf-8")
    print(f"Model artifact saved: {model_path}")
    print(f"Metadata saved: {model_dir / 'metadata.json'}")

    # ------------------------------------------------------
    # PREDICTIONS: one next-report forecast per qualifying station,
    # using each station's most recent reading as the lag inputs.
    # ------------------------------------------------------
    latest = (
        featured.dropna(subset=LAG_FEATURE_COLUMNS)
        .sort_values("report_datetime")
        .groupby("station", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    X_latest = make_feature_matrix(latest, dummy_columns)
    latest_predictions = model.predict(X_latest)

    generated_at = datetime.now(timezone.utc).isoformat()
    predictions = build_prediction_records(
        latest, latest_predictions, MODEL_NAME, MODEL_VERSION, "pdma_gauge_readings", generated_at
    )

    predictions_dir = ANALYTICS_DATA / "pdma"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = predictions_dir / "gauge_discharge_forecast.json"
    predictions_path.write_text(json.dumps(predictions, indent=4), encoding="utf-8")
    print(f"Predictions written: {predictions_path} ({len(predictions)} records)")
    print("=" * 60)


if __name__ == "__main__":
    main()
