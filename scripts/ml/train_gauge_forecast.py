"""
scripts/ml/train_gauge_forecast.py

Task 22 -- gauge discharge forecasting, extending Task 9
(scripts/forecasting/gauge_discharge_forecast.py) with the leakage-safe Gold-layer feature set
from pipeline/ml/features.py.

KEY DIFFERENCES FROM TASK 9 (documented, not hidden):
  - Source: gold_gauge_daily (Task 21's daily-grain Gold dataset), not a live query against
    pdma_gauge_readings. Target is therefore discharge_avg (the daily mean of discharge_cusecs
    for that station/day), not the raw per-report discharge_cusecs Task 9 used.
  - Horizon: t+1 CALENDAR DAY (next day's discharge_avg), matching the daily grain actually
    available -- not Task 9's "next report" (which could be hours away).
  - Features: 12 lag/rolling columns (pipeline/ml/features.py::GAUGE_FEATURE_COLUMNS) vs. Task
    9's 3 (lag_1, lag_2, rolling_mean_3) -- lag_1/lag_2/rolling_mean_3 are reused verbatim from
    Task 9's own scripts/forecasting/features.py, the rest are new daily-grain extensions.
  - A SECOND, real finding from this task's own inspection: 20 of 41 gauge stations in
    gold_gauge_daily have exactly ONE distinct discharge_avg value across their ENTIRE history
    (effectively a constant), and 3 more have zero non-null values -- the same class of defect
    Task 9 found in current_level_ft, now also present in a majority of stations' daily-
    aggregated discharge. Training on a constant is not a real forecast (Task 9's own stated
    principle), so this script applies a data-driven qualifying filter (>= MIN_DISTINCT_VALUES
    distinct discharge_avg values) -- no station name is hard-coded.

Task 9's original artifact (data/models/gauge_discharge_forecast/2026-09-11/) is left completely
untouched -- this script writes to a NEW version directory.

Run inside the Airflow container (scikit-learn is in airflow_requirements.txt, not the host
venv -- same situation Task 9 was in):
  docker exec -e PYTHONPATH=/opt/project airflow_webserver \
      python scripts/ml/train_gauge_forecast.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.path import ANALYTICS_DATA, MODELS_DATA  # noqa: E402
from pipeline.ml.features import GAUGE_FEATURE_COLUMNS, GAUGE_TARGET, build_gauge_features, chronological_split  # noqa: E402

MODEL_NAME = "gauge_discharge_forecast"
MODEL_VERSION = datetime.now().strftime("%Y-%m-%d") + "-task22-daily"
TARGET_COLUMN = "target_t_plus_1"
MIN_DISTINCT_VALUES = 10  # data-driven station qualification bar -- see module docstring
TRAIN_PCT, VAL_PCT = 0.70, 0.15
GOLD_GAUGE_PATH = PROJECT_ROOT / "data" / "analytics" / "gold" / "datasets" / "gold_gauge_daily.jsonl"


def load_gold_gauge_daily(path: Path = GOLD_GAUGE_PATH) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select_qualifying_stations(df: pd.DataFrame) -> list[str]:
    """Every station with >= MIN_DISTINCT_VALUES distinct discharge_avg values in its history --
    live, data-driven, no hard-coded station list (matches Task 9's own stated principle)."""
    counts = df.groupby("station_name")[GAUGE_TARGET].nunique()
    return sorted(counts[counts >= MIN_DISTINCT_VALUES].index.tolist())


def make_feature_matrix(df: pd.DataFrame, dummy_columns: pd.Index) -> pd.DataFrame:
    dummies = pd.get_dummies(df["station_name"], prefix="station", dtype=int).reindex(columns=dummy_columns, fill_value=0)
    return pd.concat([df[GAUGE_FEATURE_COLUMNS].reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)


def evaluate(y_true, y_pred) -> dict:
    return {"mae": float(mean_absolute_error(y_true, y_pred)), "rmse": float(root_mean_squared_error(y_true, y_pred)),
           "r2": float(r2_score(y_true, y_pred)) if len(set(y_true)) > 1 else None}


def persistence_only_metrics(df: pd.DataFrame, target_col: str) -> dict | None:
    """Honest, cheap multi-horizon reporting (Step 12/14): persistence predicted = lag_1 for
    t+3/t+7 too, evaluated only where that target actually exists (no fabricated rows)."""
    usable = df.dropna(subset=["lag_1", target_col])
    if usable.empty:
        return None
    return evaluate(usable[target_col], usable["lag_1"])


def git_commit_hash() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def main():
    print("=" * 70)
    print("GAUGE DISCHARGE FORECAST -- TASK 22 (Gold-layer, daily grain)")
    print("=" * 70)

    records = load_gold_gauge_daily()
    if not records:
        print("No gold_gauge_daily data found -- run scripts/gold/run_gold.py first. Aborting.")
        sys.exit(1)

    featured = build_gauge_features(records)
    all_stations = sorted(featured["station_name"].unique().tolist())
    qualifying = select_qualifying_stations(featured)
    excluded = sorted(set(all_stations) - set(qualifying))
    print(f"Stations total: {len(all_stations)}  qualifying (>= {MIN_DISTINCT_VALUES} distinct "
         f"discharge_avg values): {len(qualifying)}  excluded as near-constant/empty: {len(excluded)}")
    print(f"Excluded: {excluded}")

    if not qualifying:
        print("No station clears the completeness bar -- aborting. No model trained.")
        sys.exit(1)

    scoped = featured[featured["station_name"].isin(qualifying)].reset_index(drop=True)
    complete = scoped.dropna(subset=GAUGE_FEATURE_COLUMNS + [TARGET_COLUMN]).reset_index(drop=True)
    print(f"Rows after feature completeness filter: {len(complete)} (of {len(scoped)} scoped rows)")

    if complete.empty:
        print("No complete rows after feature engineering -- aborting.")
        sys.exit(1)

    # chronological_split()'s quantile() call needs a real datetime dtype, not pandas 3's default
    # pyarrow-backed string column -- "date" stays the string display column, this is purely for
    # ordering/splitting.
    complete = complete.assign(_split_date=pd.to_datetime(complete["date"]))
    train_df, val_df, test_df = chronological_split(complete, time_col="_split_date", train_pct=TRAIN_PCT, val_pct=VAL_PCT)
    print(f"Train: {len(train_df)}  Val: {len(val_df)}  Test: {len(test_df)}")
    if train_df.empty or test_df.empty:
        print("Insufficient data for a chronological split -- aborting.")
        sys.exit(1)
    print(f"Train range: {train_df['date'].min()} -> {train_df['date'].max()}")
    if not val_df.empty:
        print(f"Val   range: {val_df['date'].min()} -> {val_df['date'].max()}")
    print(f"Test  range: {test_df['date'].min()} -> {test_df['date'].max()}")

    dummy_columns = pd.get_dummies(complete["station_name"], prefix="station", dtype=int).columns
    X_train, y_train = make_feature_matrix(train_df, dummy_columns), train_df[TARGET_COLUMN].reset_index(drop=True)
    X_val, y_val = make_feature_matrix(val_df, dummy_columns), val_df[TARGET_COLUMN].reset_index(drop=True)
    X_test, y_test = make_feature_matrix(test_df, dummy_columns), test_df[TARGET_COLUMN].reset_index(drop=True)

    linreg = LinearRegression().fit(X_train, y_train)
    forest = RandomForestRegressor(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1).fit(X_train, y_train)

    metrics = {"persistence": {}, "linear_regression": {}, "random_forest": {}}
    splits = {"train": (X_train, y_train, train_df), "val": (X_val, y_val, val_df), "test": (X_test, y_test, test_df)}
    for name, (X, y, split_df) in splits.items():
        if split_df.empty:
            continue
        metrics["persistence"][name] = evaluate(y, split_df["lag_1"].reset_index(drop=True))
        metrics["linear_regression"][name] = evaluate(y, linreg.predict(X))
        metrics["random_forest"][name] = evaluate(y, forest.predict(X))

    test_persistence_mae = metrics["persistence"]["test"]["mae"]
    skill = {
        "linear_regression": 1 - (metrics["linear_regression"]["test"]["mae"] / test_persistence_mae) if test_persistence_mae > 0 else None,
        "random_forest": 1 - (metrics["random_forest"]["test"]["mae"] / test_persistence_mae) if test_persistence_mae > 0 else None,
    }

    print("=" * 70)
    print("TEST METRICS (t+1 day, cusecs)")
    for model_name in ("persistence", "linear_regression", "random_forest"):
        m = metrics[model_name]["test"]
        print(f"  {model_name:<18} MAE={m['mae']:.1f}  RMSE={m['rmse']:.1f}  R2={m['r2']}")
    print(f"Skill vs persistence (test): {skill}")
    if skill["random_forest"] is not None and skill["random_forest"] <= 0 and skill["linear_regression"] <= 0:
        print("HONEST RESULT: neither ML model beats the persistence baseline on the held-out test set.")
    print("=" * 70)

    # Multi-horizon, persistence-only (Step 10/12): t+3 / t+7, reported not modeled.
    horizon_metrics = {"t_plus_1": metrics["persistence"]["test"],
                       "t_plus_3": persistence_only_metrics(test_df, "target_t_plus_3"),
                       "t_plus_7": persistence_only_metrics(test_df, "target_t_plus_7")}
    print(f"Persistence-only metrics across horizons (test): {horizon_metrics}")

    # Feature importance -- RandomForest only, explicitly NOT causal.
    importances = sorted(zip(X_train.columns, forest.feature_importances_), key=lambda kv: -kv[1])
    numeric_importances = [(name, float(score)) for name, score in importances if not name.startswith("station_")][:len(GAUGE_FEATURE_COLUMNS)]
    print(f"Top numeric feature importances (NOT causal): {numeric_importances[:5]}")

    model_dir = MODELS_DATA / MODEL_NAME / MODEL_VERSION
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"linear_regression": linreg, "random_forest": forest, "feature_columns": list(X_train.columns)},
               model_dir / "model.joblib")

    metadata = {
        "model_name": MODEL_NAME, "model_version": MODEL_VERSION, "training_date": datetime.now(timezone.utc).isoformat(),
        "predecessor_version": "2026-09-11 (Task 9 -- untouched)", "source_dataset": "data/analytics/gold/datasets/gold_gauge_daily.jsonl",
        "target_variable": TARGET_COLUMN, "target_description": "next-calendar-day discharge_avg (t+1)",
        "horizon": "t+1 day (modeled); t+3/t+7 persistence-only, see horizon_metrics",
        "feature_columns": list(X_train.columns), "numeric_feature_columns": GAUGE_FEATURE_COLUMNS,
        "min_distinct_values_threshold": MIN_DISTINCT_VALUES, "all_stations": all_stations,
        "qualifying_stations": qualifying, "excluded_stations_near_constant_or_empty": excluded,
        "train_rows": len(train_df), "val_rows": len(val_df), "test_rows": len(test_df),
        "train_range": [str(train_df["date"].min()), str(train_df["date"].max())],
        "val_range": [str(val_df["date"].min()), str(val_df["date"].max())] if not val_df.empty else None,
        "test_range": [str(test_df["date"].min()), str(test_df["date"].max())],
        "metrics": metrics, "skill_score_test": skill, "horizon_metrics_test": horizon_metrics,
        "top_numeric_feature_importances": numeric_importances,
        "feature_importance_caveat": "feature importance, NOT a causal claim",
        "sklearn_version": sklearn.__version__, "pandas_version": pd.__version__,
        "git_commit": git_commit_hash(), "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    (model_dir / "metrics.json").write_text(json.dumps({"metrics": metrics, "skill_score_test": skill,
                                                        "horizon_metrics_test": horizon_metrics}, indent=2), encoding="utf-8")

    latest = (featured[featured["station_name"].isin(qualifying)].dropna(subset=GAUGE_FEATURE_COLUMNS)
             .sort_values("date").groupby("station_name", as_index=False).tail(1).reset_index(drop=True))
    X_latest = make_feature_matrix(latest, dummy_columns)
    predictions = []
    for (_, row), rf_pred, lr_pred in zip(latest.iterrows(), forest.predict(X_latest), linreg.predict(X_latest)):
        predictions.append({"station": row["station_name"], "based_on_date": row["date"], "forecast_for": "t_plus_1_day",
                           "predicted_discharge_avg_random_forest": round(float(rf_pred), 1),
                           "predicted_discharge_avg_linear_regression": round(float(lr_pred), 1),
                           "model_version": MODEL_VERSION})
    (model_dir / "predictions.json").write_text(json.dumps(predictions, indent=2), encoding="utf-8")

    ml_dir = ANALYTICS_DATA / "ml"
    ml_dir.mkdir(parents=True, exist_ok=True)
    (ml_dir / "gauge_forecast_predictions_latest.json").write_text(json.dumps(predictions, indent=2), encoding="utf-8")

    print(f"Model artifact: {model_dir / 'model.joblib'}")
    print(f"Metadata: {model_dir / 'metadata.json'}")
    print(f"Predictions ({len(predictions)} stations): {model_dir / 'predictions.json'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
