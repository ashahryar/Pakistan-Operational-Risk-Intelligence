from pipeline.risk.config import load_config
from pipeline.risk.engine import run_engine
from tests.risk._helpers import days, gauge, gold, rain

CFG = load_config()


def test_missing_rainfall_creates_no_observation_and_no_row():
    out = run_engine(gold(rainfall=[rain(7, "2026-07-01", None)]), CFG)
    assert out["rows"] == []                       # a null rainfall value is not "0 mm"


def test_observed_zero_rainfall_is_kept_as_zero():
    rows = [rain(7, d, float(i % 3)) for i, d in enumerate(days("2026-06-01", 8))]
    rows.append(rain(7, "2026-06-20", 0.0))
    out = run_engine(gold(rainfall=rows), CFG)
    last = [r for r in out["rows"] if r["date"] == "2026-06-20"][0]
    assert last["rainfall_signal"] == 0.0 and last["signal_states"]["rainfall"] == "OBSERVED"


def test_empty_domains_do_not_create_false_zero_risk():
    out = run_engine(gold(rainfall=[rain(7, d, 5.0 + i) for i, d in enumerate(days("2026-06-01", 8))]), CFG)
    for r in out["rows"]:
        assert r["gauge_signal"] is None and r["air_quality_signal"] is None and r["weather_signal"] is None
        assert r["signal_states"]["gauge"] == "MISSING" and r["hazard_alert_signal"] is None
        assert r["disaster_event_signal"] is None            # missing != "no event"


def test_empty_gold_produces_no_rows_at_all():
    assert run_engine(gold(), CFG)["rows"] == []


def test_score_stays_null_when_evidence_is_insufficient_and_when_disabled():
    out = run_engine(gold(gauge=[gauge(3, "2026-07-01", 100.0)]), CFG)
    assert out["rows"][0]["risk_status"] == "INSUFFICIENT_DATA" and out["rows"][0]["risk_score"] is None
    full = run_engine(gold(rainfall=[rain(7, d, float(i)) for i, d in enumerate(days("2026-05-01", 40))]), CFG)
    assert all(r["risk_score"] is None for r in full["rows"])   # score.enabled is false: no evidence-based weights
