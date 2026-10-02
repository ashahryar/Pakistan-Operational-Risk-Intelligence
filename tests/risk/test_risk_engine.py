import json
from pathlib import Path

import pytest

from pipeline.risk.config import DEFAULT_CONFIG_PATH, enabled_geographic_domains, load_config
from pipeline.risk.coverage import coverage_matrix
from pipeline.risk.engine import ml_fields, run_engine
from tests.risk._helpers import alert, aqi, days, event, gauge, gold, rain, weather

CFG = load_config()
REPO = Path(__file__).resolve().parents[2]


def full_gold():
    return gold(rainfall=[rain(7, d, float(i)) for i, d in enumerate(days("2026-05-01", 40))],
                gauge=[gauge(7, d, 100.0 + i) for i, d in enumerate(days("2026-05-01", 40))],
                air_quality=[aqi(7, d, 50.0 + i) for i, d in enumerate(days("2026-05-01", 40))] + [aqi(7, "2026-06-20", 1.0, "station_snapshot")],
                weather=[weather(7, d, 30.0) for d in days("2026-05-01", 3)],
                hazard_alert=[alert(7, "2026-06-09")], disaster_event=[event(7, "2026-06-09")],
                reservoir=[{"reservoir_name": "T", "observed_at": "2026-06-09T06:00:00"}])


def test_engine_output_is_deterministic_and_idempotent():
    a, b = run_engine(full_gold(), CFG), run_engine(full_gold(), CFG)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_row_order_of_input_does_not_change_output():
    g = full_gold()
    rev = {k: list(reversed(v)) for k, v in g.items()}
    assert json.dumps(run_engine(g, CFG)["rows"], sort_keys=True) == json.dumps(run_engine(rev, CFG)["rows"], sort_keys=True)


def test_all_domains_are_handled_according_to_declared_semantics():
    out = run_engine(full_gold(), CFG)
    row = [r for r in out["rows"] if r["date"] == "2026-06-09"][0]
    assert set(row["signal_states"]) == set(enabled_geographic_domains(CFG))
    assert row["signal_states"]["rainfall"] == "OBSERVED" and row["signal_states"]["gauge"] == "OBSERVED"
    assert row["signal_states"]["air_quality"] == "OBSERVED" and row["signal_states"]["hazard_alert"] == "OBSERVED"
    assert row["signal_states"]["disaster_event"] == "OBSERVED_NO_BASELINE"
    assert row["signal_states"]["weather"] == "MISSING"
    assert "documents" not in row["signal_states"] and "reservoir" not in row["signal_states"]
    assert [r["date"] for r in out["rows"] if r["date"] == "2026-06-20"] == []   # station_snapshot AQI is not a daily risk signal


def test_calculation_version_and_provisional_status_are_in_every_row():
    out = run_engine(full_gold(), CFG)
    assert out["rows"] and all(r["calculation_version"] == CFG["calculation_version"] and r["engine_version"] == CFG["engine_version"]
                               and r["threshold_status"] == "PROVISIONAL" for r in out["rows"])


def test_risk_configuration_is_versioned_and_marks_thresholds_provisional():
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    assert CFG["engine_version"] and CFG["calculation_version"] and CFG["score"]["enabled"] is False
    assert "PROVISIONAL" in text and "NOT authoritative" in text
    assert CFG["enabled_domains"]["documents"] is False


def test_config_missing_required_keys_is_rejected(tmp_path):
    bad = tmp_path / "c.yaml"
    bad.write_text("engine_version: v1\n")
    with pytest.raises(ValueError):
        load_config(bad)


def test_coverage_matrix_counts_are_correct():
    g = gold(rainfall=[rain(1, "2026-01-01", 1.0), rain(1, "2026-01-02", 2.0), rain(None, "2026-01-02", 3.0, status="unresolved")])
    c = coverage_matrix(g)["rainfall"]
    assert (c["total_source_observations"], c["resolved_observations"], c["unresolved_observations"]) == (3, 2, 1)
    assert (c["distinct_geographies_resolved"], c["distinct_dates"], c["resolved_pct"]) == (1, 2, 66.67)
    assert coverage_matrix(g)["gauge"]["resolved_pct"] is None      # empty domain: no fabricated 0%


PRED = [{"station": "Marala", "based_on_date": "2026-09-14", "predicted_discharge_avg_linear_regression": 5000.0}]


def test_ml_requires_qualifying_station_resolved_geography_and_same_day_prediction():
    ok = ml_fields(5, "2026-09-14", PRED, {"Marala": 5}, {"Marala"}, set())
    assert ok["ml_forecast_available"] and ok["ml_reference_model"] == "persistence" and "negative skill" in ok["ml_note"]
    assert not ml_fields(5, "2026-09-13", PRED, {"Marala": 5}, {"Marala"}, set())["ml_forecast_available"]
    assert not ml_fields(5, "2026-09-15", PRED, {"Marala": 5}, {"Marala"}, set())["ml_forecast_available"]
    assert ml_fields(5, "2026-09-14", PRED, {"Marala": 5}, set(), set())["ml_unavailable_reason"] == "station_not_a_qualifying_model_station"
    assert ml_fields(5, "2026-09-14", PRED, {"Marala": 5}, {"Marala"}, {5})["ml_unavailable_reason"] == "geography_caveat_excludes_unit"
    assert not ml_fields(5, "2026-09-14", PRED, {}, {"Marala"}, set())["ml_forecast_available"]


def test_ml_never_leaks_into_status_or_a_score():
    g = gold(gauge=[gauge(5, d, 100.0 + i, station="Marala") for i, d in enumerate(days("2026-08-01", 45))])
    with_ml = run_engine(g, CFG, ml_predictions=PRED, ml_qualifying={"Marala"})
    without = run_engine(g, CFG)

    def strip(rows):
        return [{k: v for k, v in r.items() if not k.startswith("ml_")} for r in rows]

    assert strip(with_ml["rows"]) == strip(without["rows"])
    assert any(r["ml_forecast_available"] for r in with_ml["rows"]) and all(r["risk_score"] is None for r in with_ml["rows"])


def test_real_gold_output_if_present_has_no_score_and_unique_keys():
    path = REPO / "data" / "analytics" / "risk" / "gold_operational_risk.jsonl"
    if not path.exists():
        pytest.skip("risk output not generated in this environment")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len({(r["admin_unit_id"], r["date"]) for r in rows}) == len(rows)
    assert all(r["risk_score"] is None for r in rows)
