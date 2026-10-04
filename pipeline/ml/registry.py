"""Task 33 -- model metadata and versioning (a lightweight, file-based record; deliberately NOT MLflow or an external registry).

A run id / version is derived from the target, the horizon and a fingerprint of the observed data and settings, so the same data and code always give
the same id (re-running is idempotent) and a change in the data gives a new version. Tracked artifacts per run: metadata.json, metrics.json,
predictions.json. The fitted estimator (model.joblib) is written only when an ML model was actually validated and is git-ignored (reproducible).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pipeline.ml.contracts import ML_PREDICTION_VERSION

MODEL_ROOT = Path("data") / "models" / "risk_prediction"


def run_metadata(run: dict, as_of: str, fingerprint: str) -> dict:
    """The model/version/provenance record of one run (also what is stored in ml.model_runs)."""
    s = run.get("split") or {}
    return {"model_run_id": run["model_run_id"], "model_version": run["model_version"], "ml_prediction_version": ML_PREDICTION_VERSION,
            "target": run["target"], "domain": run["domain"], "unit": run["unit"], "horizon_days": run["horizon_days"],
            "status": run["status"], "validated_against_baseline": run["validated_against_baseline"],
            "model_name": run["deployed_name"] or "none", "model_type": run["deployed_type"], "no_model_reason": run["no_model_reason"],
            "as_of": as_of, "feature_cutoff": run["feature_cutoff"], "training_cutoff": run["training_cutoff"], "data_fingerprint": fingerprint,
            "entity_ids": run["entity_ids"], "requirements": run["requirements"],
            "train_period": s.get("train_target_range"), "validation_period": s.get("validation_target_range"), "test_period": s.get("test_target_range"),
            "n_train": s.get("n_train"), "n_validation": s.get("n_validation"), "n_test": s.get("n_test"), "purged_rows": s.get("purged_rows"),
            "missing_data": run["missing_data"], "metrics": run["metrics"], "per_entity": run["per_entity"]}


def save_run(result_run: dict, estimator, as_of: str, fingerprint: str, root: Path, predictions: list[dict]) -> Path:
    d = Path(root) / result_run["model_run_id"]
    d.mkdir(parents=True, exist_ok=True)
    meta = run_metadata(result_run, as_of, fingerprint)
    (d / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (d / "metrics.json").write_text(json.dumps(result_run["metrics"], indent=2, sort_keys=True), encoding="utf-8")
    (d / "predictions.json").write_text(json.dumps(predictions, indent=2, sort_keys=True), encoding="utf-8")
    if estimator is not None:
        import joblib
        joblib.dump(estimator, d / "model.joblib")
    return d


def load_estimator(run_dir: Path) -> Optional[object]:
    p = Path(run_dir) / "model.joblib"
    if not p.exists():
        return None
    import joblib
    return joblib.load(p)
