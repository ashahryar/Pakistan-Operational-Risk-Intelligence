from pipeline.risk.config import load_config
from pipeline.risk.engine import run_engine
from tests.risk._helpers import alert, days, event, gauge, gold, rain

CFG = load_config()
RES = [{"reservoir_name": "Tarbela", "observed_at": "2026-09-16T06:00:00", "water_level": 1542.0, "live_storage": 5.1,
        "combined_live_storage": 10.8, "observation_time_basis": "source_observed", "admin_unit_id": None,
        "resolution_status": "not_attempted"}]


def test_unresolved_geography_is_not_force_mapped():
    out = run_engine(gold(gauge=[gauge(None, "2026-07-01", 100.0, status="unresolved")],
                          rainfall=[rain(None, "2026-07-01", 5.0, status="ambiguous")]), CFG)
    assert out["rows"] == []                                    # no fabricated admin unit / row
    assert len(out["unresolved"]) == 2 and all("admin_unit_id" not in u for u in out["unresolved"])
    assert {u["resolution_status"] for u in out["unresolved"]} == {"unresolved", "ambiguous"}


def test_unresolved_alerts_and_events_are_preserved_separately():
    out = run_engine(gold(hazard_alert=[alert(None, "2026-07-01", status="unresolved")],
                          disaster_event=[event(None, "2026-07-01", status="unresolved")]), CFG)
    assert out["rows"] == [] and {u["domain"] for u in out["unresolved"]} == {"hazard_alert", "disaster_event"}


def test_reservoir_is_never_forced_into_an_admin_unit():
    out = run_engine(gold(reservoir=RES), CFG)
    assert out["rows"] == []                                    # reservoir alone creates no geography x date cell
    assert out["reservoir_context"][0]["geography"] == "not_attributable_to_an_admin_unit"


def test_reservoir_does_not_leak_into_other_rows():
    out = run_engine(gold(reservoir=RES, rainfall=[rain(7, "2026-09-16", 2.0)]), CFG)
    assert len(out["rows"]) == 1 and "reservoir" not in out["rows"][0]["signal_states"]


def test_caveated_unit_never_drives_status_but_is_still_reported():
    gauges = [gauge(33, d, 1000.0 + i, station="Mangla") for i, d in enumerate(days("2026-05-01", 40))]
    out = run_engine(gold(gauge=gauges), CFG, caveated_units={33})
    last = out["rows"][-1]
    assert last["risk_status"] == "INSUFFICIENT_DATA" and last["signal_states"]["gauge"] == "GEOGRAPHY_CAVEAT"
    assert last["gauge_signal"] is None and last["top_risk_domain"] is None


def test_unit_labels_are_taken_from_the_supplied_canonical_lookup_only():
    info = {7: {"name": "Lahore", "level": 2, "province": "Punjab"}}
    out = run_engine(gold(rainfall=[rain(7, "2026-07-01", 1.0)]), CFG, unit_info=info)
    assert (out["rows"][0]["admin_unit_name"], out["rows"][0]["admin_level"], out["rows"][0]["province"]) == ("Lahore", 2, "Punjab")
    other = run_engine(gold(rainfall=[rain(8, "2026-07-01", 1.0)]), CFG, unit_info=info)
    assert other["rows"][0]["admin_unit_name"] is None          # unknown unit: not guessed
