"""Task 33 -- end-to-end train / evaluate / predict for one target over all horizons. Pure: records in, a result dict out (no DB, no files, no wall clock;
`as_of` is the dataset's own latest observation date).

Flow per horizon h:
    eligibility (min observed days per entity) -> supervised frame -> purged temporal split (70/15/15 by target date) -> requirement checks
    -> baselines scored on validation and test -> candidates fit on TRAIN only and scored on VALIDATION -> best candidate by validation MAE
    -> refit on train+validation -> scored ONCE on test -> decision.
Decision: the ML model is used only if its MAE is lower than the best baseline's on validation AND on test (best baseline chosen on validation).
Otherwise the deployed predictor is that baseline and the rows are labelled BASELINE_ONLY: a model that does not beat a trivial baseline is not shipped as ML.
Entities without enough history, with stale data, or without complete features get INSUFFICIENT_DATA rows (null prediction + reason): nothing is imputed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import pandas as pd

from pipeline.ml import contracts as C
from pipeline.ml.dataset import (
    FEATURE_COLUMNS,
    build_daily_series,
    build_supervised,
    data_fingerprint,
    history_summary,
    latest_origin_features,
    missing_data_impact,
)
from pipeline.ml.evaluation import beats, regression_metrics, skill
from pipeline.ml.models import BASELINES, candidate_models, fit_predict
from pipeline.ml.splitting import assert_no_overlap, temporal_split

MIN_OBSERVED_DAYS = 180          # an entity needs this many real observed days before it can be modelled
MIN_TRAIN_ROWS = 100
MIN_EVAL_ROWS = 20               # validation and test, each
MAX_STALENESS_DAYS = 3           # the entity's latest observation must be this close to the dataset's latest date
DEFAULT_HORIZONS = (1, 3, 7)


@dataclass(frozen=True)
class TargetSpec:
    name: str                    # e.g. "air_quality_index"
    domain: str
    unit: str
    entity_key: str
    date_key: str
    value_key: str
    source: str                  # human-readable provenance of the observations
    entity_type: str = "admin_unit"


def _entity_unit_id(entity_id) -> Optional[int]:
    try:
        return int(entity_id)
    except (TypeError, ValueError):
        return None


def _row(spec, unit, h, as_of, status, reason, prediction, run, origin=None) -> dict:
    origin = origin or as_of
    model = status != C.STATUS_INSUFFICIENT
    return {"admin_unit_id": unit["id"], "entity_type": spec.entity_type, "entity_id": str(unit["id"]),
            "prediction_date": (pd.Timestamp(origin) + pd.Timedelta(days=h)).date().isoformat(), "horizon_days": h, "target": spec.name, "unit": spec.unit,
            "prediction": None if prediction is None else round(float(prediction), 3), "status": status, "reason": reason,
            "model_name": run["deployed_name"] if model else None, "model_version": run["model_version"] if model else None,
            "model_type": run["deployed_type"] if model else C.MODEL_TYPE_NONE,
            "training_cutoff": run["training_cutoff"] if model else None, "feature_cutoff": pd.Timestamp(origin).date().isoformat(),
            "model_run_id": run["model_run_id"],
            "provenance": {"provenance": C.PROVENANCE, "data_source": spec.source, "domain": spec.domain, "model_run_id": run["model_run_id"],
                           "ml_prediction_version": C.ML_PREDICTION_VERSION, "kind": "forecast_of_observed_quantity",
                           "validated_against_baseline": run["validated_against_baseline"], "evaluation": run["evaluation_summary"],
                           "note": C.NOT_A_RISK_STATUS}}


def run_horizon(series: pd.DataFrame, spec: TargetSpec, h: int, units: list[dict], as_of: pd.Timestamp, fingerprint: str) -> dict:
    hist = history_summary(series)
    eligible = [e for e, s in hist.items() if s["observed_days"] >= MIN_OBSERVED_DAYS]
    run = {"target": spec.name, "domain": spec.domain, "horizon_days": h, "unit": spec.unit, "entity_ids": eligible,
           "model_run_id": f"{spec.name}-h{h}-{fingerprint[:10]}", "model_version": f"{C.ML_PREDICTION_VERSION}+{fingerprint[:10]}",
           "requirements": {"min_observed_days": MIN_OBSERVED_DAYS, "min_train_rows": MIN_TRAIN_ROWS, "min_eval_rows": MIN_EVAL_ROWS, "max_staleness_days": MAX_STALENESS_DAYS},
           "validated_against_baseline": False, "deployed_name": None, "deployed_type": C.MODEL_TYPE_NONE, "status": "NO_MODEL", "no_model_reason": None,
           "training_cutoff": None, "feature_cutoff": as_of.date().isoformat(), "evaluation_summary": None, "metrics": None, "split": None,
           "missing_data": None, "per_entity": {}, "history": hist}
    predictor, estimator = None, None
    if not eligible:
        run["no_model_reason"] = f"no entity has {MIN_OBSERVED_DAYS} observed days of history"
    else:
        frame = build_supervised(series[series["entity_id"].astype(str).isin(eligible)], h)
        run["missing_data"] = missing_data_impact(frame)
        sp = temporal_split(frame)
        run["split"] = {k: v for k, v in (sp["boundaries"] or {}).items()} | {"purged_rows": sp["purged"], "n_train": len(sp["train"]),
                                                                           "n_validation": len(sp["validation"]), "n_test": len(sp["test"])}
        if sp["boundaries"] is None or len(sp["train"]) < MIN_TRAIN_ROWS or len(sp["validation"]) < MIN_EVAL_ROWS or len(sp["test"]) < MIN_EVAL_ROWS:
            run["no_model_reason"] = (f"too few usable rows after the temporal split (train {len(sp['train'])}/{MIN_TRAIN_ROWS}, "
                                      f"validation {len(sp['validation'])}/{MIN_EVAL_ROWS}, test {len(sp['test'])}/{MIN_EVAL_ROWS})")
        else:
            assert_no_overlap(sp)
            tr, va, te = sp["train"], sp["validation"], sp["test"]
            ytr_va, yte = va["target"].to_numpy(float), te["target"].to_numpy(float)
            base = {n: {"validation": regression_metrics(ytr_va, f(va)), "test": regression_metrics(yte, f(te))} for n, f in BASELINES.items()}
            best_base = min(base, key=lambda n: base[n]["validation"]["mae"])
            cand_val, fitted = {}, {}
            for name in candidate_models():
                est, pred = fit_predict(name, tr, va)
                cand_val[name] = regression_metrics(ytr_va, pred)
                fitted[name] = est
            chosen = min(cand_val, key=lambda n: cand_val[n]["mae"])
            final, test_pred = fit_predict(chosen, pd.concat([tr, va]), te)                     # refit on train+validation; test is scored once
            model_test = regression_metrics(yte, test_pred)
            model_val = cand_val[chosen]
            wins_val, wins_test = beats(model_val, base[best_base]["validation"]), beats(model_test, base[best_base]["test"])
            validated = bool(wins_val and wins_test)
            per_entity = {}
            for e in eligible:
                m = te["entity_id"].astype(str) == e
                if m.any():
                    per_entity[e] = {"test_rows": int(m.sum()), "model_mae": regression_metrics(te.loc[m, "target"], test_pred[m.to_numpy()])["mae"],
                                     "baseline_mae": regression_metrics(te.loc[m, "target"], BASELINES[best_base](te[m]))["mae"]}
            run.update(validated_against_baseline=validated, status="VALIDATED" if validated else "BASELINE_ONLY", per_entity=per_entity,
                       training_cutoff=sp["boundaries"]["validation_end"],
                       deployed_name=chosen if validated else best_base, deployed_type=C.MODEL_TYPE_ML if validated else C.MODEL_TYPE_BASELINE,
                       metrics={"baselines": base, "best_baseline": best_base, "candidates_validation": cand_val, "selected_model": chosen,
                                "selected_model_validation": model_val, "selected_model_test": model_test,
                                "skill_vs_best_baseline": {"validation": skill(model_val["mae"], base[best_base]["validation"]["mae"]),
                                                           "test": skill(model_test["mae"], base[best_base]["test"]["mae"])},
                                "model_beats_best_baseline": {"validation": bool(wins_val), "test": bool(wins_test)},
                                "metric_note": "MAE is the decision metric; R2 is relative to the evaluated period's own mean and can be negative under a level shift"})
            run["evaluation_summary"] = {"selected_model": chosen, "best_baseline": best_base, "test_mae_model": model_test["mae"],
                                         "test_mae_baseline": base[best_base]["test"]["mae"], "skill_test": run["metrics"]["skill_vs_best_baseline"]["test"],
                                         "n_test": len(te), "model_beats_baseline": validated}
            estimator = final if validated else None
            predictor = estimator.predict if validated else (lambda X, b=BASELINES[best_base]: b(X))
    # ------------------------------------------------------------------ prediction rows (one per unit)
    rows = []
    raw_ids = {str(i): i for i in series["entity_id"].unique()}
    for unit in units:
        e = str(unit["id"])
        s = hist.get(e)
        if s is None:
            rows.append(_row(spec, unit, h, as_of, C.STATUS_INSUFFICIENT, f"no {spec.domain} observations exist for this area (0 observed days; at least {MIN_OBSERVED_DAYS} needed)", None, run))
        elif e not in eligible:
            rows.append(_row(spec, unit, h, as_of, C.STATUS_INSUFFICIENT, f"only {s['observed_days']} observed days (at least {MIN_OBSERVED_DAYS} needed)", None, run))
        elif predictor is None:
            rows.append(_row(spec, unit, h, as_of, C.STATUS_INSUFFICIENT, run["no_model_reason"], None, run))
        elif (as_of - pd.Timestamp(s["last_date"])).days > MAX_STALENESS_DAYS:
            rows.append(_row(spec, unit, h, as_of, C.STATUS_INSUFFICIENT, f"latest observation {s['last_date']} is more than {MAX_STALENESS_DAYS} days before {as_of.date()}", None, run))
        else:
            origin = pd.Timestamp(s["last_date"])
            f = latest_origin_features(series, raw_ids[e], origin)
            if f is None:
                rows.append(_row(spec, unit, h, as_of, C.STATUS_INSUFFICIENT, "the features at the latest observation are incomplete (missing days in the recent window); nothing is imputed", None, run, origin))
            else:
                x = pd.DataFrame([f.to_numpy(dtype=float)], columns=FEATURE_COLUMNS)
                pred = float(predictor(x)[0])
                rows.append(_row(spec, unit, h, as_of, C.STATUS_PREDICTED if run["deployed_type"] == C.MODEL_TYPE_ML else C.STATUS_BASELINE_ONLY, None, pred, run, origin))
    return {"run": run, "predictions": rows, "estimator": estimator}


def run_target(records: Iterable[dict], spec: TargetSpec, units: list[dict], horizons: Iterable[int] = DEFAULT_HORIZONS) -> dict:
    series = build_daily_series(records, spec.entity_key, spec.date_key, spec.value_key)
    if series.empty:
        raise ValueError("no observations: nothing to model")
    as_of = series.loc[series["observed"], "date"].max()
    fp = data_fingerprint(series, {"target": spec.name, "lags": FEATURE_COLUMNS, "min": [MIN_OBSERVED_DAYS, MIN_TRAIN_ROWS, MIN_EVAL_ROWS]})
    results = [run_horizon(series, spec, h, units, as_of, fp) for h in horizons]
    preds = [p for r in results for p in r["predictions"]]
    problems = [(p["entity_id"], p["horizon_days"], m) for p in preds for m in C.validate_prediction(p)]
    if problems:
        raise AssertionError(f"prediction contract violations: {problems[:5]}")
    counts = {s: sum(p["status"] == s for p in preds) for s in C.STATUSES}
    return {"as_of": as_of.date().isoformat(), "fingerprint": fp, "runs": [r["run"] for r in results], "predictions": preds,
            "estimators": {r["run"]["horizon_days"]: r["estimator"] for r in results}, "status_counts": counts, "history": history_summary(series)}
