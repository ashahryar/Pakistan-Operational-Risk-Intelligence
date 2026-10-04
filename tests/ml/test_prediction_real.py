"""Task 33 -- the ML prediction layer on the REAL Gold air-quality data (Lahore, admin unit 30). Skipped when the Gold file is not present (CI has no
local data) or scikit-learn is missing. These tests record the honest finding of the real run: enough history for an experiment, but no ML model beat
the simple baselines, so the stored predictions are BASELINE_ONLY and every other area is INSUFFICIENT_DATA."""

import pytest

pytest.importorskip("sklearn")
from scripts.ml.run_prediction_pipeline import GOLD_AQ, SPEC, load_records  # noqa: E402

pytestmark = pytest.mark.skipif(not GOLD_AQ.exists(), reason="Gold air-quality dataset not present")


@pytest.fixture(scope="module")
def result():
    from pipeline.ml.runner import run_target
    units = [{"id": 30, "level": 2, "name": "Lahore"}, {"id": 2, "level": 1, "name": "Punjab"}, {"id": 46, "level": 2, "name": "Sialkot"}]
    return run_target(load_records(), SPEC, units, horizons=(1, 3, 7))


def test_the_selected_domain_has_dense_history_and_resolved_geography(result):
    h = result["history"]
    assert list(h) == ["30"] and h["30"]["observed_days"] == 350 and h["30"]["missing_days"] == 0 and h["30"]["first_date"] == "2025-10-01"
    assert result["as_of"] == "2026-09-15"
    assert all(r["admin_unit_id"] is not None for r in load_records())                       # unresolved rows are never assigned a unit


def test_temporal_periods_are_ordered_and_disjoint(result):
    for run in result["runs"]:
        s = run["split"]
        assert s["train_target_range"][1] <= s["train_end"] < s["validation_origin_range"][0]
        assert s["validation_target_range"][1] <= s["validation_end"] < s["test_origin_range"][0]
        assert s["n_train"] > 200 and s["n_validation"] > 40 and s["n_test"] > 40 and run["missing_data"]["dropped_share"] < 0.1


def test_no_ml_model_beat_the_baselines_so_nothing_is_shipped_as_ml(result):
    assert result["status_counts"] == {"PREDICTED": 0, "BASELINE_ONLY": 3, "INSUFFICIENT_DATA": 6}
    for run in result["runs"]:
        assert run["validated_against_baseline"] is False and run["deployed_type"] == "baseline"
        beats = run["metrics"]["model_beats_best_baseline"]
        assert not (beats["validation"] and beats["test"])
    assert result["estimators"] == {1: None, 3: None, 7: None}


def test_lahore_rows_are_labelled_baseline_and_other_areas_are_insufficient(result):
    lahore = [p for p in result["predictions"] if p["admin_unit_id"] == 30]
    assert [p["status"] for p in lahore] == ["BASELINE_ONLY"] * 3 and all(p["prediction"] is not None and p["feature_cutoff"] == "2026-09-15" for p in lahore)
    assert all(p["provenance"]["validated_against_baseline"] is False and p["model_type"] == "baseline" for p in lahore)
    others = [p for p in result["predictions"] if p["admin_unit_id"] != 30]
    assert all(p["status"] == "INSUFFICIENT_DATA" and p["prediction"] is None and p["model_type"] == "none" for p in others)
