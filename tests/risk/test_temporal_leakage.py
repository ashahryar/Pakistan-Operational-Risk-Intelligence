from pipeline.risk.config import load_config
from pipeline.risk.engine import run_engine
from tests.risk._helpers import alert, days, event, gold, rain

CFG = load_config()


def _row(out, unit, date):
    return [r for r in out["rows"] if r["admin_unit_id"] == unit and r["date"] == date][0]


def test_future_observations_cannot_change_risk_at_t():
    base = [rain(7, d, float(i)) for i, d in enumerate(days("2026-05-01", 40))]
    t = "2026-06-09"                                           # 40th day (index 39)
    before = _row(run_engine(gold(rainfall=base), CFG), 7, t)
    future = base + [rain(7, d, 10_000.0) for d in days("2026-06-10", 15)]
    after = _row(run_engine(gold(rainfall=future), CFG), 7, t)
    assert before == after                                      # the whole row, not just one field


def test_same_day_value_is_never_part_of_its_own_baseline():
    base = [rain(7, d, 1.0) for d in days("2026-05-01", 39)]
    base.append(rain(7, "2026-06-09", 999.0))
    row = _row(run_engine(gold(rainfall=base), CFG), 7, "2026-06-09")
    assert row["rainfall_signal"] == 1.0                       # 999 ranks above all 39 PRIOR values; not diluted by itself


def test_future_alert_is_not_active_before_it_is_issued():
    out = run_engine(gold(hazard_alert=[alert(2, "2026-08-10")], rainfall=[rain(2, "2026-08-05", 3.0)]), CFG)
    assert _row(out, 2, "2026-08-05")["hazard_alert_signal"] is None
    assert _row(out, 2, "2026-08-10")["hazard_alert_signal"] == 1.0


def test_alert_without_validity_window_is_not_active_forever():
    out = run_engine(gold(hazard_alert=[alert(2, "2026-08-10")], rainfall=[rain(2, "2026-08-20", 3.0)]), CFG)
    assert _row(out, 2, "2026-08-20")["hazard_alert_signal"] is None


def test_alert_with_explicit_validity_window_covers_inside_dates_only():
    out = run_engine(gold(hazard_alert=[alert(2, "2026-08-10", valid_until="2026-08-12T00:00:00")],
                          rainfall=[rain(2, "2026-08-11", 3.0), rain(2, "2026-08-13", 3.0)]), CFG)
    assert _row(out, 2, "2026-08-11")["hazard_alert_signal"] == 1.0
    assert _row(out, 2, "2026-08-13")["hazard_alert_signal"] is None


def test_event_counts_are_date_correct_and_exclude_future_events():
    events = [event(4, "2026-07-01", "e1"), event(4, "2026-07-10", "e2"), event(4, "2026-09-01", "e3")]
    out = run_engine(gold(disaster_event=events), CFG)
    assert _row(out, 4, "2026-07-01")["business_signals"]["RECENT_DISASTER_SIGNAL"]["records_in_window"] == 1
    assert _row(out, 4, "2026-07-10")["business_signals"]["RECENT_DISASTER_SIGNAL"]["records_in_window"] == 2
    assert _row(out, 4, "2026-09-01")["business_signals"]["RECENT_DISASTER_SIGNAL"]["records_in_window"] == 1   # 07-xx aged out


def test_removing_future_events_does_not_change_an_earlier_row():
    a = run_engine(gold(disaster_event=[event(4, "2026-07-01", "e1"), event(4, "2026-07-20", "e2")]), CFG)
    b = run_engine(gold(disaster_event=[event(4, "2026-07-01", "e1")]), CFG)
    assert _row(a, 4, "2026-07-01") == _row(b, 4, "2026-07-01")
