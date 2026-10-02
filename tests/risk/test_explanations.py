from pipeline.risk.config import load_config
from pipeline.risk.engine import run_engine
from tests.risk._helpers import alert, days, gold, rain

CFG = load_config()


def _case():
    rows = [rain(7, d, float(i)) for i, d in enumerate(days("2026-05-01", 40))]
    return run_engine(gold(rainfall=rows, hazard_alert=[alert(7, "2026-06-09")]), CFG)


def test_explanations_match_actual_contributing_signals():
    out = _case()
    row = [r for r in out["rows"] if r["date"] == "2026-06-09"][0]
    exp = [e for e in out["explanations"] if e["date"] == "2026-06-09"][0]
    assert {d["domain"] for d in exp["drivers"]} == {"rainfall", "hazard_alert"}
    assert exp["risk_status"] == row["risk_status"] and exp["risk_basis"] == row["risk_basis"]
    rain_driver = [d for d in exp["drivers"] if d["domain"] == "rainfall"][0]
    assert rain_driver["normalized"] == row["rainfall_signal"] and rain_driver["value"] == 39.0


def test_missing_domains_and_quality_block_are_reported():
    exp = _case()["explanations"][0]
    assert "gauge" in exp["missing_domains"] and "rainfall" not in exp["missing_domains"]
    assert set(exp["data_quality"]) == {"coverage_pct", "risk_confidence"}


def test_every_row_has_exactly_one_explanation_and_reasons_are_non_empty():
    out = _case()
    assert len(out["explanations"]) == len(out["rows"])
    assert all(d["reason"] for e in out["explanations"] for d in e["drivers"])


def test_thin_history_explanation_states_the_limitation_instead_of_a_claim():
    out = run_engine(gold(rainfall=[rain(7, d, float(i)) for i, d in enumerate(days("2026-05-01", 3))]), CFG)
    assert out["explanations"][-1]["drivers"][0]["reason"] == "observed, but too little prior history to normalize"
