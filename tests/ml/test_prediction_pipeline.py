"""Task 33 -- tests of the ML prediction layer (pipeline/ml: dataset, features, temporal split, baselines, training, contract, insufficient history).

The series below are SYNTHETIC and exist only to test the transformation / decision LOGIC (for example a clean weekly cycle that a lag model must
beat persistence on, and a random walk that nothing may beat). They are never fed into the real model or reported as observations; the real-data
evaluation is scripts/ml/run_prediction_pipeline.py (tests/ml/test_prediction_real.py).
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.ml import contracts as C
from pipeline.ml.dataset import FEATURE_COLUMNS, build_daily_series, build_supervised, history_summary, latest_origin_features, missing_data_impact
from pipeline.ml.evaluation import beats, regression_metrics, skill
from pipeline.ml.models import BASELINES
from pipeline.ml.runner import MAX_STALENESS_DAYS, MIN_OBSERVED_DAYS, TargetSpec, run_target
from pipeline.ml.splitting import assert_no_overlap, temporal_split

REPO = Path(__file__).resolve().parents[2]
SPEC = TargetSpec("air_quality_index", "air_quality", "AQI", "admin_unit_id", "date", "aqi_avg", "synthetic test series")


def records(values, start="2025-01-01", uid=30, skip=()):
    d0 = pd.Timestamp(start)
    return [{"admin_unit_id": uid, "date": (d0 + pd.Timedelta(days=i)).date().isoformat(), "aqi_avg": float(v)} for i, v in enumerate(values) if i not in set(skip)]


def weekly(n=300, seed=1):
    rng = np.random.default_rng(seed)
    return [100 + 30 * np.sin(2 * np.pi * i / 7) + rng.normal(0, 1.0) for i in range(n)]


def walk(n=300, seed=2):
    return list(100 + np.cumsum(np.random.default_rng(seed).normal(0, 5, n)))


# ------------------------------------------------------------------ dataset construction
def test_series_is_placed_on_the_calendar_grid_and_missing_days_stay_nan():
    s = build_daily_series(records(range(10, 20), skip=(3, 4)), "admin_unit_id", "date", "aqi_avg")
    assert len(s) == 10 and int(s["observed"].sum()) == 8
    assert s.loc[~s["observed"], "value"].isna().all()                                    # never interpolated, forward-filled or zero-filled
    assert history_summary(s)["30"] == {"first_date": "2025-01-01", "last_date": "2025-01-10", "observed_days": 8, "calendar_days": 10, "missing_days": 2}


def test_duplicate_records_for_a_day_are_averaged_and_bad_values_are_not_observations():
    recs = records([10, 20, 30]) + [{"admin_unit_id": 30, "date": "2025-01-02", "aqi_avg": 40.0}, {"admin_unit_id": 30, "date": "2025-01-03", "aqi_avg": None}]
    s = build_daily_series(recs, "admin_unit_id", "date", "aqi_avg").set_index("date")["value"]
    assert s[pd.Timestamp("2025-01-02")] == 30.0                                           # (20 + 40) / 2
    assert s[pd.Timestamp("2025-01-03")] == 30.0 and s.notna().sum() == 3                  # the None record is not an observation; the real 30 stays


def test_target_is_the_observation_exactly_h_days_after_the_origin():
    s = build_daily_series(records(range(100, 140)), "admin_unit_id", "date", "aqi_avg")
    f = build_supervised(s, 3)
    row = f[f["origin_date"] == pd.Timestamp("2025-01-20")].iloc[0]
    assert row["target_date"] == pd.Timestamp("2025-01-23") and row["target"] == 100 + 22 and row["lag_0"] == 100 + 19 and row["lag_1"] == 100 + 18
    assert row["rolling_mean_3"] == np.mean([117, 118, 119]) and row["delta_1"] == 1.0


def test_horizon_must_be_positive_and_target_is_not_a_feature():
    s = build_daily_series(records(range(30)), "admin_unit_id", "date", "aqi_avg")
    with pytest.raises(ValueError):
        build_supervised(s, 0)
    assert "target" not in FEATURE_COLUMNS and not any("target" in c or "future" in c for c in FEATURE_COLUMNS)


# ------------------------------------------------------------------ feature cutoff and leakage
def test_future_observations_cannot_enter_historical_features():
    """THE leakage test: change every observation after day D to an absurd value -> every feature of every row whose origin is <= D is unchanged."""
    vals = weekly(120)
    base = build_supervised(build_daily_series(records(vals), "admin_unit_id", "date", "aqi_avg"), 1)
    D = 60
    mutated_vals = vals[: D + 1] + [1e9] * (len(vals) - D - 1)
    mut = build_supervised(build_daily_series(records(mutated_vals), "admin_unit_id", "date", "aqi_avg"), 1)
    cutoff = pd.Timestamp("2025-01-01") + pd.Timedelta(days=D)
    a, b = base[base["origin_date"] <= cutoff], mut[mut["origin_date"] <= cutoff]
    pd.testing.assert_frame_equal(a[FEATURE_COLUMNS].reset_index(drop=True), b[FEATURE_COLUMNS].reset_index(drop=True))
    assert (mut.loc[mut["origin_date"] > cutoff, "lag_0"].dropna() == 1e9).all()          # ...while the later rows really did change (the test is not vacuous)


def test_features_do_not_depend_on_how_much_data_comes_later():
    vals = weekly(150)
    full = build_supervised(build_daily_series(records(vals), "admin_unit_id", "date", "aqi_avg"), 1)
    short = build_supervised(build_daily_series(records(vals[:90]), "admin_unit_id", "date", "aqi_avg"), 1)       # no global statistic: same early features
    pd.testing.assert_frame_equal(full.iloc[:90][FEATURE_COLUMNS].reset_index(drop=True), short[FEATURE_COLUMNS].reset_index(drop=True))


def test_latest_origin_features_use_only_data_up_to_the_cutoff():
    s = build_daily_series(records(weekly(80)), "admin_unit_id", "date", "aqi_avg")
    cut = pd.Timestamp("2025-01-01") + pd.Timedelta(days=40)
    f1 = latest_origin_features(s, 30, cut)
    s2 = s.copy()
    s2.loc[s2["date"] > cut, "value"] = 7777.0
    f2 = latest_origin_features(s2, 30, cut)
    assert f1 is not None and f1.equals(f2)
    assert latest_origin_features(s, 30, pd.Timestamp("2030-01-01")) is None                          # no observation at the cutoff -> nothing is fabricated


def test_no_documents_rag_or_risk_engine_inputs_in_the_ml_modules():
    for name in ("dataset", "splitting", "models", "evaluation", "runner", "registry", "contracts"):
        src = (REPO / "pipeline" / "ml" / f"{name}.py").read_text(encoding="utf-8")
        imports = " ".join(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M))
        for banned in ("pipeline.rag", "pipeline.intelligence", "pipeline.risk", "api.", "dashboard"):
            assert banned not in imports, (name, banned)


# ------------------------------------------------------------------ missing-data policy
def test_a_missing_day_makes_dependent_rows_unusable_and_is_counted():
    s = build_daily_series(records(weekly(60), skip=(30,)), "admin_unit_id", "date", "aqi_avg")
    f = build_supervised(s, 1)
    day = lambda i: pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)  # noqa: E731
    r = f.set_index("origin_date")
    assert not r.loc[day(30), "usable"] and r.loc[day(30), "drop_reason"] == "missing_or_insufficient_history"
    assert not r.loc[day(29), "usable"] and r.loc[day(29), "drop_reason"] == "target_not_observed"
    assert r.loc[day(46), "usable"] and not r.loc[day(36), "usable"]                      # lag_13 / rolling_14 need 14 clean days after the gap
    impact = missing_data_impact(f)
    assert impact["dropped_rows"] > 13 and "target_not_observed" in impact["dropped_by_reason"] and impact["dropped_share"] > 0.2
    assert f["lag_0"].isna().sum() == 1                                                    # exactly the one missing day: nothing was filled


# ------------------------------------------------------------------ temporal split
def split_for(h=3, n=300):
    f = build_supervised(build_daily_series(records(weekly(n)), "admin_unit_id", "date", "aqi_avg"), h)
    return temporal_split(f)


@pytest.mark.parametrize("h", [1, 3, 7])
def test_temporal_split_is_ordered_purged_and_non_overlapping(h):
    sp = split_for(h)
    b = sp["boundaries"]
    assert_no_overlap(sp)
    tr, va, te = sp["train"], sp["validation"], sp["test"]
    assert tr["target_date"].max() <= pd.Timestamp(b["train_end"]) < va["origin_date"].min()
    assert va["target_date"].max() <= pd.Timestamp(b["validation_end"]) < te["origin_date"].min()
    assert sp["purged"] >= h                                                               # rows straddling a boundary are discarded, not reused
    assert len(tr) > len(va) and len(tr) > len(te) and len(tr) + len(va) + len(te) + sp["purged"] == int(build_supervised(
        build_daily_series(records(weekly(300)), "admin_unit_id", "date", "aqi_avg"), h)["usable"].sum())


def test_a_random_split_would_be_detected_as_leaking():
    sp = split_for(3)
    shuffled = pd.concat([sp["train"], sp["validation"], sp["test"]]).sample(frac=1.0, random_state=0)
    n = len(shuffled)
    bad = dict(sp, train=shuffled.iloc[: int(n * .7)], validation=shuffled.iloc[int(n * .7): int(n * .85)], test=shuffled.iloc[int(n * .85):])
    with pytest.raises(AssertionError):
        assert_no_overlap(bad)


# ------------------------------------------------------------------ baselines and metrics
def test_baselines_and_metrics():
    f = build_supervised(build_daily_series(records(range(100, 160)), "admin_unit_id", "date", "aqi_avg"), 1)
    u = f[f["usable"]]
    assert np.array_equal(BASELINES["persistence"](u), u["lag_0"].to_numpy()) and np.allclose(BASELINES["rolling_mean_7"](u), u["rolling_mean_7"])
    m = regression_metrics([1, 2, 3, 4], [1, 2, 3, 6])
    assert m == {"n": 4, "mae": 0.5, "rmse": 1.0, "r2": 0.2} and regression_metrics([5, 5], [5, 5])["r2"] is None
    assert regression_metrics([1, 2], [float("nan"), 1])["mae"] is None and skill(8, 10) == 0.2 and skill(None, 10) is None
    assert beats({"mae": 1}, {"mae": 2}) and not beats({"mae": 2}, {"mae": 2})


# ------------------------------------------------------------------ training, decision and prediction contract (needs scikit-learn)
sk = pytest.importorskip("sklearn")


def run(values, units=None, **kw):
    return run_target(records(values, **kw), SPEC, units or [{"id": 30}, {"id": 2}, {"id": 99}], horizons=(1,))


def test_a_model_that_beats_the_baselines_on_validation_and_test_is_labelled_predicted():
    out = run(weekly(300))
    run1 = out["runs"][0]
    assert run1["status"] == "VALIDATED" and run1["validated_against_baseline"] and run1["deployed_type"] == "ml"
    m = run1["metrics"]
    assert m["model_beats_best_baseline"] == {"validation": True, "test": True} and m["skill_vs_best_baseline"]["test"] > 0.5
    rows = {p["admin_unit_id"]: p for p in out["predictions"]}
    p = rows[30]
    assert p["status"] == "PREDICTED" and p["model_type"] == "ml" and p["provenance"]["provenance"] == "ML_MODEL" and p["provenance"]["validated_against_baseline"] is True
    assert p["feature_cutoff"] == out["as_of"] and p["prediction_date"] == (pd.Timestamp(out["as_of"]) + pd.Timedelta(days=1)).date().isoformat()
    assert p["training_cutoff"] == run1["split"]["validation_end"] < p["feature_cutoff"] and abs(p["prediction"] - 100) < 60
    assert out["estimators"][1] is not None


def test_a_model_that_does_not_beat_the_baseline_is_not_shipped_as_ml():
    out = run(walk(300))
    r1 = out["runs"][0]
    assert r1["status"] == "BASELINE_ONLY" and not r1["validated_against_baseline"] and r1["deployed_type"] == "baseline" and out["estimators"][1] is None
    p = next(p for p in out["predictions"] if p["admin_unit_id"] == 30)
    assert p["status"] == "BASELINE_ONLY" and p["model_type"] == "baseline" and p["model_name"] in BASELINES and p["provenance"]["validated_against_baseline"] is False


def test_units_without_enough_history_get_explicit_insufficient_data_never_a_number():
    out = run(weekly(300))
    for uid in (2, 99):
        p = next(p for p in out["predictions"] if p["admin_unit_id"] == uid)
        assert p["status"] == C.STATUS_INSUFFICIENT and p["prediction"] is None and p["model_type"] == "none" and p["model_name"] is None
        assert f"at least {MIN_OBSERVED_DAYS} needed" in p["reason"] and p["provenance"]["provenance"] == "ML_MODEL"
    short = run(weekly(MIN_OBSERVED_DAYS - 5))
    assert all(p["status"] == C.STATUS_INSUFFICIENT and p["prediction"] is None for p in short["predictions"])
    assert short["runs"][0]["status"] == "NO_MODEL" and "no entity has" in short["runs"][0]["no_model_reason"]
    assert short["status_counts"] == {"PREDICTED": 0, "BASELINE_ONLY": 0, "INSUFFICIENT_DATA": 3}


def test_too_few_rows_after_the_split_is_insufficient_even_with_enough_calendar_days():
    out = run(weekly(300), skip=tuple(range(0, 300, 4)))                                   # a quarter of the days missing: lag windows rarely complete
    r = out["runs"][0]
    assert r["status"] == "NO_MODEL" and "too few usable rows" in r["no_model_reason"] and out["status_counts"]["INSUFFICIENT_DATA"] == 3


def test_stale_or_incomplete_recent_data_is_insufficient_not_imputed():
    other = records(weekly(300), uid=5)                                                    # a second unit whose data ends earlier than the dataset's latest date
    stale = [r for r in other if r["date"] <= (pd.Timestamp("2025-01-01") + pd.Timedelta(days=300 - 1 - MAX_STALENESS_DAYS - 2)).date().isoformat()]
    out = run_target(records(weekly(300)) + stale, SPEC, [{"id": 30}, {"id": 5}], horizons=(1,))
    p5 = next(p for p in out["predictions"] if p["admin_unit_id"] == 5)
    assert p5["status"] == C.STATUS_INSUFFICIENT and "days before" in p5["reason"] and p5["prediction"] is None
    gap = run(weekly(300), skip=(299,))                                                    # the latest day is missing -> the origin moves back, features are complete
    assert next(p for p in gap["predictions"] if p["admin_unit_id"] == 30)["feature_cutoff"] == "2025-10-26"
    gap2 = run(weekly(300), skip=(297,), units=[{"id": 30}])                              # a gap inside the recent window -> incomplete features
    p = gap2["predictions"][0]
    assert p["status"] == C.STATUS_INSUFFICIENT and "incomplete" in p["reason"] and p["prediction"] is None


def test_test_period_values_never_influence_model_selection():
    base = weekly(300)
    a = run(base)["runs"][0]
    cut = pd.Timestamp(a["split"]["validation_end"])
    idx0 = pd.Timestamp("2025-01-01")
    mutated = [v if (idx0 + pd.Timedelta(days=i)) <= cut else v + 500 for i, v in enumerate(base)]
    b = run(mutated)["runs"][0]
    assert a["metrics"]["selected_model"] == b["metrics"]["selected_model"] and a["metrics"]["candidates_validation"] == b["metrics"]["candidates_validation"]
    assert a["metrics"]["baselines"]["persistence"]["validation"] == b["metrics"]["baselines"]["persistence"]["validation"]
    assert a["metrics"]["selected_model_test"] != b["metrics"]["selected_model_test"]    # only the test score moved


def test_runs_are_deterministic_and_idempotent():
    a, b = run(weekly(300)), run(weekly(300))
    assert a["fingerprint"] == b["fingerprint"] and a["predictions"] == b["predictions"] and a["runs"][0]["model_run_id"] == b["runs"][0]["model_run_id"]
    assert run(weekly(300, seed=9))["fingerprint"] != a["fingerprint"]                     # different data -> a new version


def test_as_of_is_the_datasets_latest_observation_not_the_wall_clock():
    out = run(weekly(300), start="2020-03-01")
    assert out["as_of"] == "2020-12-25" and all(p["feature_cutoff"] <= "2020-12-25" and p["prediction_date"] > "2020-12-25" for p in out["predictions"])


def test_every_prediction_row_satisfies_the_contract():
    out = run(weekly(300))
    for p in out["predictions"]:
        assert C.validate_prediction(p) == []
        assert set(C.CONTRACT_FIELDS) <= set(p)
    bad = dict(out["predictions"][0], status="PREDICTED", prediction=None)
    assert C.validate_prediction(bad)
    assert C.validate_prediction(dict(out["predictions"][-1], prediction=3.0))
    assert "feature_cutoff must be before prediction_date" in C.validate_prediction(dict(out["predictions"][0], feature_cutoff="2999-01-01"))
    assert C.validate_prediction({"status": "PREDICTED"})


def test_risk_score_is_not_part_of_the_prediction_contract():
    assert "risk_score" not in C.CONTRACT_FIELDS and "risk_status" not in C.CONTRACT_FIELDS
    assert "not a current risk classification" in C.NOT_A_RISK_STATUS
