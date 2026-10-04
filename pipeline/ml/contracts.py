"""Task 33 -- the prediction contract of the ML prediction layer. Pure Python (no pandas / sklearn): the API serves rows of this shape.

An ML prediction is a FUTURE value of an observed quantity (for example next-day air quality). It is NOT a current risk classification and never
replaces or feeds the deterministic risk engine; `risk_score` stays null. Every row carries model / version / cutoffs / provenance, and an explicit
status instead of a made-up number when the requirements for a prediction are not met.
"""

from __future__ import annotations

from typing import Optional

ML_PREDICTION_VERSION = "1.0.0"

STATUS_PREDICTED = "PREDICTED"                # a model validated against the baselines on held-out validation AND test periods produced the value
STATUS_BASELINE_ONLY = "BASELINE_ONLY"        # the ML model did not beat the best baseline: the value is that baseline's, labelled as such
STATUS_INSUFFICIENT = "INSUFFICIENT_DATA"     # requirements not met: prediction is null and `reason` says why
STATUSES = (STATUS_PREDICTED, STATUS_BASELINE_ONLY, STATUS_INSUFFICIENT)

PROVENANCE = "ML_MODEL"
MODEL_TYPE_ML, MODEL_TYPE_BASELINE, MODEL_TYPE_NONE = "ml", "baseline", "none"

CONTRACT_FIELDS = ("admin_unit_id", "entity_type", "entity_id", "prediction_date", "horizon_days", "target", "unit", "prediction", "status", "reason",
                   "model_name", "model_version", "model_type", "training_cutoff", "feature_cutoff", "model_run_id", "provenance")

NOT_A_RISK_STATUS = ("A forecast of an observed quantity at a future date. It is not a current risk classification, not a risk status and not a risk "
                     "score; the operational risk engine remains the source of truth for current status.")


def validate_prediction(row: dict) -> list[str]:
    """Problems with a contract row (empty list = valid). Used by the pipeline before loading and by the tests."""
    problems = [f"missing field: {f}" for f in CONTRACT_FIELDS if f not in row]
    if problems:
        return problems
    st = row["status"]
    if st not in STATUSES:
        problems.append(f"unknown status: {st}")
    if st == STATUS_INSUFFICIENT:
        if row["prediction"] is not None:
            problems.append("INSUFFICIENT_DATA must have a null prediction")
        if not row["reason"]:
            problems.append("INSUFFICIENT_DATA must state a reason")
        if row["model_type"] != MODEL_TYPE_NONE:
            problems.append("INSUFFICIENT_DATA must not name a model type")
    elif st in (STATUS_PREDICTED, STATUS_BASELINE_ONLY):
        if row["prediction"] is None or row["prediction"] != row["prediction"]:
            problems.append("a predicted row needs a finite prediction")
        if not row["model_name"] or not row["model_version"] or not row["training_cutoff"] or not row["feature_cutoff"]:
            problems.append("a predicted row needs model name/version and both cutoffs")
        if st == STATUS_PREDICTED and row["model_type"] != MODEL_TYPE_ML:
            problems.append("PREDICTED requires model_type ml")
        if st == STATUS_BASELINE_ONLY and row["model_type"] != MODEL_TYPE_BASELINE:
            problems.append("BASELINE_ONLY requires model_type baseline")
    if row["feature_cutoff"] and row["prediction_date"] and not (str(row["feature_cutoff"]) < str(row["prediction_date"])):
        problems.append("feature_cutoff must be before prediction_date")
    if row["horizon_days"] is None or int(row["horizon_days"]) < 1:
        problems.append("horizon_days must be >= 1")
    prov: Optional[dict] = row["provenance"]
    if not isinstance(prov, dict) or prov.get("provenance") != PROVENANCE:
        problems.append("provenance must be an object with provenance ML_MODEL")
    return problems
