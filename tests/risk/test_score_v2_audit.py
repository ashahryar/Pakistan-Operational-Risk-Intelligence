"""Task 36 -- the evidence audit on the REAL Gold datasets (skipped when they are absent, e.g. in CI). Records the measured outcome: no numeric score is defensible yet."""

import json

import pytest

from scripts.risk import audit_score_v2 as A
from scripts.risk import run_risk_engine as RUN

pytestmark = pytest.mark.skipif(not (RUN.GOLD / "gold_air_quality.jsonl").exists(), reason="Gold datasets not present")


@pytest.fixture(scope="module")
def report():
    return A.run()


def test_audit_is_idempotent(report):
    assert A.run() == report and json.dumps(report, sort_keys=True) == json.dumps(A.run(), sort_keys=True)


def test_outcome_is_b_no_numeric_score_and_every_cell_abstains(report):
    assert report["outcome"] == "B" and report["numeric_score_enabled"] is False and report["scoring_enabled"] is False
    assert report["cells_scored"] == 0 and report["cells_abstained"] == report["cells_assessed"] == 1771 and report["evidence_based_weights_defined"] == []
    assert sum(report["contributing_group_histogram"].values()) == 1771 and "NOT defensible" in report["conclusion"]


def test_abstention_reasons_add_up(report):
    c, h = report["abstention_reason_counts"], report["contributing_group_histogram"]
    assert c["SCORE_V2_DISABLED"] == 1771 and c["NO_ELIGIBLE_SIGNAL"] == h["0"] and c["TOO_FEW_INDEPENDENT_SIGNAL_GROUPS"] == h["1"]
    assert c["NO_EVIDENCE_BASED_WEIGHTS"] == report["cells_with_at_least_one_eligible_signal_group"] == 484      # Task 38: 358 + 126 gauge cells
    assert report["cells_with_required_independent_groups"] == 8 == h["2"]                        # only 8 cells even meet the data contract


def test_domain_findings_match_the_coverage_facts(report):
    d = report["domains"]
    assert d["weather"]["distinct_dates"] == 1 and d["weather"]["historical_reference_available"] is False
    assert d["gauge"]["resolved_rows"] == 186 and d["gauge"]["eligibility_counts"].get("ELIGIBLE", 0) == 126 and d["gauge"]["decision"] == "ELIGIBLE_OBSERVATIONS_EXIST"
    assert d["gauge"]["distinct_geographies_resolved"] == 2          # Task 38: Chashma (Mianwali) and Trimmu (Jhang) only
    assert d["air_quality"]["distinct_geographies_resolved"] == 1 and d["air_quality"]["eligibility_counts"]["ELIGIBLE"] > 0
    assert d["hazard_alert"]["decision"] == d["disaster_event"]["decision"] == "CONTEXTUAL"
    assert d["rainfall"]["eligibility_counts"]["UNRESOLVED_GEOGRAPHY"] > 0 and d["rainfall"]["longest_unit_history_observations"] < 60


def test_every_assessed_signal_carries_provenance(report):
    assert report["provenance_coverage"]["pct"] == 100.0 and report["provenance_coverage"]["assessed_signals"] > 2000


def test_the_audit_never_touches_risk_rows_or_scores():
    rows = [json.loads(x) for x in (A.PROJECT_ROOT / "data" / "analytics" / "risk" / "gold_operational_risk.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1586 and all(r["risk_score"] is None for r in rows)
