"""Task 22 -- run the leakage-safe feature pipeline (pipeline/ml/features.py) against the real
Gold datasets on disk (data/analytics/gold/datasets/, produced by scripts/gold/run_gold.py --
run that first). Pure Python/pandas, no pyspark, no database write.

Writes:
  data/analytics/ml/gauge_forecast_features.jsonl   (full feature rows, gitignored -- large)
  data/analytics/ml/feature_summary.json             (counts per feature table, tracked)
  data/analytics/ml/feature_quality_report.json       (missingness/completeness findings, tracked)

Usage: python scripts/ml/run_feature_pipeline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.ml.features import (  # noqa: E402
    GAUGE_FEATURE_COLUMNS, build_aqi_features, build_gauge_features, build_hazard_event_features, build_rainfall_features,
)

GOLD_DATASETS = PROJECT_ROOT / "data" / "analytics" / "gold" / "datasets"
ML_ROOT = PROJECT_ROOT / "data" / "analytics" / "ml"


def _read(name: str) -> list[dict]:
    path = GOLD_DATASETS / f"{name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    gauge_records = _read("gold_gauge_daily")
    rainfall_records = _read("gold_rainfall_daily")
    aqi_records = _read("gold_air_quality")
    hazard_records = _read("gold_hazard_alerts")
    disaster_records = _read("gold_disaster_events")

    gauge_df = build_gauge_features(gauge_records)
    rainfall_df = build_rainfall_features(rainfall_records)
    aqi_df, aqi_meta = build_aqi_features(aqi_records)
    as_of_dates = sorted(set(rainfall_df["date"]) | {r["issued_at"][:10] for r in hazard_records if r.get("issued_at")}
                        | {r["event_date"][:10] for r in disaster_records if r.get("event_date")}) if not rainfall_df.empty else []
    hazard_df = build_hazard_event_features(hazard_records, disaster_records, as_of_dates)

    ML_ROOT.mkdir(parents=True, exist_ok=True)
    if not gauge_df.empty:
        (ML_ROOT / "gauge_forecast_features.jsonl").write_text(
            "\n".join(json.dumps(row, default=str, sort_keys=True) for row in gauge_df.to_dict(orient="records")) + "\n",
            encoding="utf-8")

    complete_gauge = gauge_df.dropna(subset=GAUGE_FEATURE_COLUMNS + ["target_t_plus_1"]) if not gauge_df.empty else gauge_df
    summary = {
        "gauge": {"input_records": len(gauge_records), "feature_rows": len(gauge_df),
                 "complete_rows_t_plus_1": len(complete_gauge),
                 "stations": int(gauge_df["station_name"].nunique()) if not gauge_df.empty else 0},
        "rainfall": {"input_records": len(rainfall_records), "feature_rows": len(rainfall_df),
                    "rows_with_lag_1": int(rainfall_df["rainfall_lag_1"].notna().sum()) if not rainfall_df.empty else 0},
        "aqi": {"input_records": len(aqi_records), "daily_feature_rows": len(aqi_df), **aqi_meta},
        "hazard_event": {"as_of_dates": len(as_of_dates), "feature_rows": len(hazard_df)},
    }

    quality = {
        "gauge": {
            "fraction_complete_for_t_plus_1": (len(complete_gauge) / len(gauge_df)) if len(gauge_df) else None,
            "resolved_stations": int((gauge_df["resolution_status"] == "resolved").sum()) if not gauge_df.empty else 0,
            "unresolved_stations_rows": int((gauge_df["resolution_status"] != "resolved").sum()) if not gauge_df.empty else 0,
        },
        "rainfall": {
            "missing_rainfall_total_stays_null": int(rainfall_df["rainfall_total"].isna().sum()) if not rainfall_df.empty else 0,
            "note": "a missing rainfall_total is never coerced to 0 anywhere in this pipeline",
        },
        "weather": {"temporal_features_possible": False, "reason": "gold_weather_daily currently spans a single calendar date"},
        "aqi": aqi_meta,
    }

    (ML_ROOT / "feature_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (ML_ROOT / "feature_quality_report.json").write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
