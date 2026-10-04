"""Task 33 -- train, evaluate and (optionally) publish the ML prediction layer for the selected target.

Target: next-day / 3-day / 7-day ahead air quality index (`aqi_avg`) per admin unit, from the Gold layer `gold_air_quality` (granularity
`daily_district`, geography already resolved to an admin unit). Chosen because it is the only Gold domain with BOTH dense calendar history (350
consecutive days) AND resolved geography; gauge discharge has history but ~97 % unresolved geography (no station -> unit link is invented here),
rainfall is event-driven (78 dates), weather is a single date. See docs/architecture/ML_RISK_PREDICTION_STATUS.md.

Writes tracked artifacts under data/models/risk_prediction/<run id>/ and data/analytics/ml/prediction_evaluation_report.json. With --load it
upserts ml.model_runs / ml.predictions (migration 0033; take a restore-verified backup first). Idempotent: the run id is derived from the data
fingerprint, so re-running on the same data changes nothing. No documents/RAG content and no risk-engine output is read.

Usage: python scripts/ml/run_prediction_pipeline.py [--load] [--database NAME]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from pipeline.ml.registry import MODEL_ROOT, run_metadata, save_run  # noqa: E402
from pipeline.ml.runner import DEFAULT_HORIZONS, TargetSpec, run_target  # noqa: E402

GOLD_AQ = PROJECT_ROOT / "data" / "analytics" / "gold" / "datasets" / "gold_air_quality.jsonl"
REPORT = PROJECT_ROOT / "data" / "analytics" / "ml" / "prediction_evaluation_report.json"
SPEC = TargetSpec(name="air_quality_index", domain="air_quality", unit="AQI", entity_key="admin_unit_id", date_key="date", value_key="aqi_avg",
                  source="gold_air_quality (daily_district, source epa_punjab)")


def load_records(path: Path = GOLD_AQ) -> list[dict]:
    """Resolved daily-district air-quality observations only (rows without an admin unit are never assigned one)."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r.get("granularity") == "daily_district" and r.get("admin_unit_id") is not None]


def load_units(database: Optional[str] = None) -> list[dict]:
    from scripts.database.apply_serving_migration import engine_for
    with engine_for(database).connect() as c:
        return [dict(r._mapping) for r in c.execute(text("SELECT id, level, name FROM geo.admin_unit WHERE level IN (1, 2) ORDER BY level, id"))]


def upsert(result: dict, database: Optional[str] = None) -> dict:
    from scripts.database.apply_serving_migration import engine_for
    eng = engine_for(database)
    done = {"runs": 0, "predictions": 0}
    with eng.begin() as c:
        for run in result["runs"]:
            meta = run_metadata(run, result["as_of"], result["fingerprint"])
            s = run.get("split") or {}

            def rng(key):
                v = s.get(key) or (None, None)
                return v[0], v[1]
            ts, te = rng("train_target_range")
            vs, ve = rng("validation_target_range")
            xs, xe = rng("test_target_range")
            c.execute(text("UPDATE ml.model_runs SET is_current = FALSE WHERE target = :t AND horizon_days = :h AND model_run_id <> :id"),
                      {"t": run["target"], "h": run["horizon_days"], "id": run["model_run_id"]})
            c.execute(text("""INSERT INTO ml.model_runs (model_run_id, target, domain, unit, horizon_days, model_name, model_version, model_type, status,
                       validated_against_baseline, as_of, feature_cutoff, training_cutoff, train_start, train_end, validation_start, validation_end,
                       test_start, test_end, n_train, n_validation, n_test, metrics, metadata, is_current)
                       VALUES (:id, :t, :d, :u, :h, :mn, :mv, :mt, :st, :val, :asof, :fc, :tc, :ts, :te, :vs, :ve, :xs, :xe, :ntr, :nva, :nte,
                               CAST(:m AS jsonb), CAST(:meta AS jsonb), TRUE)
                       ON CONFLICT (model_run_id) DO UPDATE SET metrics = EXCLUDED.metrics, metadata = EXCLUDED.metadata, is_current = TRUE"""),
                      {"id": run["model_run_id"], "t": run["target"], "d": run["domain"], "u": run["unit"], "h": run["horizon_days"],
                       "mn": run["deployed_name"] or "none", "mv": run["model_version"], "mt": run["deployed_type"],
                       "st": run["status"], "val": run["validated_against_baseline"], "asof": result["as_of"], "fc": run["feature_cutoff"],
                       "tc": run["training_cutoff"], "ts": ts, "te": te, "vs": vs, "ve": ve, "xs": xs, "xe": xe, "ntr": s.get("n_train"),
                       "nva": s.get("n_validation"), "nte": s.get("n_test"), "m": json.dumps(run["metrics"]), "meta": json.dumps(meta, default=str)})
            done["runs"] += 1
        run_ids = [r["model_run_id"] for r in result["runs"]]
        c.execute(text("UPDATE ml.predictions SET is_current = FALSE WHERE target = :t AND NOT (model_run_id = ANY(:ids))"),
                  {"t": SPEC.name, "ids": run_ids})
        for p in result["predictions"]:
            c.execute(text("""INSERT INTO ml.predictions (model_run_id, entity_type, entity_id, admin_unit_id, horizon_days, prediction_date, feature_cutoff,
                       target, unit, prediction, status, reason, model_name, model_version, model_type, training_cutoff, provenance, is_current)
                       VALUES (:run, :et, :eid, :uid, :h, :pd, :fc, :t, :u, :pred, :st, :why, :mn, :mv, :mt, :tc, CAST(:prov AS jsonb), TRUE)
                       ON CONFLICT (model_run_id, entity_id, horizon_days) DO UPDATE SET prediction = EXCLUDED.prediction, status = EXCLUDED.status,
                       reason = EXCLUDED.reason, prediction_date = EXCLUDED.prediction_date, feature_cutoff = EXCLUDED.feature_cutoff,
                       provenance = EXCLUDED.provenance, is_current = TRUE"""),
                      {"run": p["model_run_id"], "et": p["entity_type"], "eid": p["entity_id"], "uid": p["admin_unit_id"], "h": p["horizon_days"],
                       "pd": p["prediction_date"], "fc": p["feature_cutoff"], "t": p["target"], "u": p["unit"], "pred": p["prediction"], "st": p["status"],
                       "why": p["reason"], "mn": p["model_name"], "mv": p["model_version"], "mt": p["model_type"], "tc": p["training_cutoff"],
                       "prov": json.dumps(p["provenance"])})
            done["predictions"] += 1
    return done


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--load", action="store_true", help="upsert ml.model_runs / ml.predictions (needs migration 0033)")
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    units = load_units(a.database)
    result = run_target(load_records(), SPEC, units, DEFAULT_HORIZONS)
    root = PROJECT_ROOT / MODEL_ROOT
    for run in result["runs"]:
        save_run(run, result["estimators"].get(run["horizon_days"]), result["as_of"], result["fingerprint"], root,
                 [p for p in result["predictions"] if p["model_run_id"] == run["model_run_id"]])
    report = {"target": SPEC.name, "source": SPEC.source, "as_of": result["as_of"], "fingerprint": result["fingerprint"], "status_counts": result["status_counts"],
              "units_considered": len(units), "history": result["history"], "runs": [run_metadata(r, result["as_of"], result["fingerprint"]) for r in result["runs"]],
              "note": "Predictions are forecasts of an observed quantity, not risk statuses. Anchored to the dataset's latest observation date, not the wall clock."}
    if not a.database:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({"as_of": result["as_of"], "status_counts": result["status_counts"],
                      "runs": [{"id": r["model_run_id"], "status": r["status"], "model": r["deployed_name"], "validated": r["validated_against_baseline"]} for r in result["runs"]]}, indent=2))
    if a.load:
        print("loaded:", upsert(result, a.database))
    return 0


if __name__ == "__main__":
    sys.exit(main())
