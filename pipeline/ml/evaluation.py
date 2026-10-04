"""Task 33 -- regression metrics and the model-vs-baseline decision. The target is a continuous value (air quality index), so MAE / RMSE / R2 are the
appropriate metrics; classification metrics (precision, recall, F1, confusion matrix) would not apply and are not reported.
R2 is computed against the mean of the EVALUATED period's own truth, so it can be strongly negative under a level shift; MAE is the decision metric.
"""

from __future__ import annotations

import math

import numpy as np


def regression_metrics(y_true, y_pred) -> dict:
    y, p = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    if len(y) == 0 or len(y) != len(p) or not np.all(np.isfinite(p)):
        return {"n": int(len(y)), "mae": None, "rmse": None, "r2": None}
    err = p - y
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"n": int(len(y)), "mae": round(float(np.abs(err).mean()), 4), "rmse": round(math.sqrt(float((err ** 2).mean())), 4),
            "r2": round(1 - float((err ** 2).sum()) / ss_tot, 4) if ss_tot > 0 else None}


def skill(model_mae, baseline_mae):
    """1 - MAE_model / MAE_baseline (> 0 means the model has lower error than the baseline)."""
    if model_mae is None or not baseline_mae:
        return None
    return round(1 - model_mae / baseline_mae, 4)


def beats(model_metrics: dict, baseline_metrics: dict) -> bool:
    return model_metrics.get("mae") is not None and baseline_metrics.get("mae") is not None and model_metrics["mae"] < baseline_metrics["mae"]
