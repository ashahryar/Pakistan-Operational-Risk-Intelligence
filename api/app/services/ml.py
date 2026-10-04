"""Task 33 -- read-only access to the ML prediction layer (ml.predictions / ml.model_runs). Values are served exactly as the pipeline stored them;
nothing is predicted, imputed or recomputed here. A prediction is a forecast of an observed quantity, never a risk status."""

from __future__ import annotations

from datetime import date
from typing import Optional

from api.app.db import fetch_all

_COLS = """model_run_id, entity_type, entity_id, admin_unit_id, horizon_days, prediction_date, feature_cutoff, target, unit, prediction, status,
           reason, model_name, model_version, model_type, training_cutoff, provenance"""


def _iso(v):
    return v.isoformat() if isinstance(v, date) else v


def _shape(r: dict) -> dict:
    d = {k: r[k] for k in ("model_run_id", "entity_type", "entity_id", "admin_unit_id", "horizon_days", "target", "unit", "status", "reason", "model_name",
                           "model_version", "model_type", "provenance")}
    d.update(prediction_date=_iso(r["prediction_date"]), feature_cutoff=_iso(r["feature_cutoff"]), training_cutoff=_iso(r["training_cutoff"]),
             prediction=None if r["prediction"] is None else float(r["prediction"]))
    return d


def list_predictions(admin_unit_id: Optional[int], prediction_date: Optional[date], horizon: Optional[int], status: Optional[str],
                     include_insufficient: bool, limit: int) -> list[dict]:
    rows = fetch_all(f"""SELECT {_COLS} FROM ml.predictions
        WHERE is_current AND (CAST(:u AS int) IS NULL OR admin_unit_id = :u) AND (CAST(:d AS date) IS NULL OR prediction_date = :d)
          AND (CAST(:h AS int) IS NULL OR horizon_days = :h) AND (CAST(:s AS text) IS NULL OR status = :s)
          AND (:inc OR status <> 'INSUFFICIENT_DATA')
        ORDER BY (status = 'INSUFFICIENT_DATA'), admin_unit_id, horizon_days LIMIT :limit""",
                     {"u": admin_unit_id, "d": prediction_date, "h": horizon, "s": status, "inc": include_insufficient, "limit": limit})
    return [_shape(r) for r in rows]


def unit_predictions(admin_unit_id: int) -> list[dict]:
    """The current, non-insufficient predictions of one area (what the intelligence layer may show)."""
    return list_predictions(admin_unit_id, None, None, None, False, 50)


def list_models() -> list[dict]:
    rows = fetch_all("""SELECT model_run_id, target, domain, unit, horizon_days, model_name, model_version, model_type, status, validated_against_baseline,
                        as_of, feature_cutoff, training_cutoff, train_start, train_end, validation_start, validation_end, test_start, test_end,
                        n_train, n_validation, n_test, metrics FROM ml.model_runs WHERE is_current ORDER BY target, horizon_days""")
    out = []
    for r in rows:
        d = dict(r)
        for k in ("as_of", "feature_cutoff", "training_cutoff", "train_start", "train_end", "validation_start", "validation_end", "test_start", "test_end"):
            d[k] = _iso(d[k])
        out.append(d)
    return out
