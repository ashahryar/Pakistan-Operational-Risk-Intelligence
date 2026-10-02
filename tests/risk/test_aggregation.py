from pipeline.risk.aggregation import aggregate_cell, status_from_normalized
from pipeline.risk.config import enabled_geographic_domains, load_config
from pipeline.risk.contracts import RiskSignal
from pipeline.risk.engine import run_engine
from tests.risk._helpers import alert, days, gold, rain

CFG = load_config()
DOMAINS = enabled_geographic_domains(CFG)


def sig(domain, norm, hist=100, prov=None, label=None, quality="OBSERVED"):
    return RiskSignal(1, "2026-07-01", domain, f"{domain}_sig", 1.0, norm, "higher_is_more_risk", norm, "x", f"id-{domain}",
                      "source_observed", quality, label, prov, hist)


def test_cutpoints_map_normalized_values_provisionally():
    cut = CFG["provisional_status_cutpoints"]
    assert [status_from_normalized(v, cut) for v in (0.1, 0.75, 0.9, 0.98, None)] == ["LOW", "MODERATE", "HIGH", "CRITICAL", None]
    assert CFG["threshold_status"] == "PROVISIONAL"


def test_thin_history_cannot_drive_a_status():
    agg = aggregate_cell([sig("rainfall", 1.0, hist=6)], CFG, DOMAINS)
    assert agg["risk_status"] == "INSUFFICIENT_DATA" and agg["risk_basis"] == "OBSERVED_SIGNAL_ONLY" and agg["risk_score"] is None


def test_single_normalized_signal_is_threshold_based_and_multi_is_multi_signal():
    one = aggregate_cell([sig("rainfall", 0.95)], CFG, DOMAINS)
    two = aggregate_cell([sig("rainfall", 0.95), sig("air_quality", 0.2)], CFG, DOMAINS)
    assert (one["risk_status"], one["risk_basis"]) == ("HIGH", "THRESHOLD_BASED")
    assert (two["risk_status"], two["risk_basis"], two["top_risk_domain"]) == ("HIGH", "MULTI_SIGNAL", "rainfall")


def test_active_alert_is_preserved_and_alert_driven_with_provisional_mapping():
    out = run_engine(gold(hazard_alert=[alert(2, "2026-08-10", severity="Very Heavy")]), CFG)
    r = out["rows"][0]
    assert (r["risk_status"], r["risk_basis"], r["hazard_alert_signal"]) == ("HIGH", "ALERT_DRIVEN", 1.0)
    assert r["business_signals"]["ACTIVE_HAZARD_SIGNAL"] == {"present": True, "source_severity_labels": ["Very Heavy"]}


def test_alert_without_published_severity_is_observed_but_never_given_an_invented_severity():
    out = run_engine(gold(hazard_alert=[alert(2, "2026-08-10", severity=None)]), CFG)
    r = out["rows"][0]
    assert r["hazard_alert_signal"] == 1.0 and r["risk_status"] == "INSUFFICIENT_DATA" and r["risk_score"] is None


def test_unmapped_severity_label_is_preserved_not_mapped():
    r = run_engine(gold(hazard_alert=[alert(2, "2026-08-10", severity="green")]), CFG)["rows"][0]
    assert r["risk_status"] == "INSUFFICIENT_DATA"
    assert r["business_signals"]["ACTIVE_HAZARD_SIGNAL"]["source_severity_labels"] == ["green"]


def test_confidence_decreases_when_coverage_decreases():
    many = aggregate_cell([sig("rainfall", 0.95), sig("air_quality", 0.95), sig("gauge", 0.95)], CFG, DOMAINS)
    some = aggregate_cell([sig("rainfall", 0.95), sig("air_quality", 0.95)], CFG, DOMAINS)
    one = aggregate_cell([sig("rainfall", 0.95)], CFG, DOMAINS)
    order = {"INSUFFICIENT": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    assert order[many["risk_confidence"]] >= order[some["risk_confidence"]] >= order[one["risk_confidence"]]
    assert many["data_coverage_pct"] > one["data_coverage_pct"]
    assert aggregate_cell([sig("rainfall", 0.95, hist=3)], CFG, DOMAINS)["risk_confidence"] == "INSUFFICIENT"


def test_coverage_pct_counts_observed_domains_over_enabled_domains():
    agg = aggregate_cell([sig("rainfall", 0.5), sig("gauge", 0.5)], CFG, DOMAINS)
    assert agg["data_coverage_pct"] == round(100 * 2 / len(DOMAINS), 2)
    assert agg["observed_signal_count"] == 2 and agg["missing_signal_count"] == len(DOMAINS) - 2


def test_duplicate_source_records_do_not_multiply_risk():
    base = [rain(7, d, float(i)) for i, d in enumerate(days("2026-05-01", 40))]
    once = run_engine(gold(rainfall=base, hazard_alert=[alert(7, "2026-06-09")]), CFG)
    twice = run_engine(gold(rainfall=base + base, hazard_alert=[alert(7, "2026-06-09")] * 3), CFG)
    assert once["rows"] == twice["rows"]
