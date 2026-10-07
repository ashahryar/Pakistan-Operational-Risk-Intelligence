"""Task 39 -- the production risk output agrees with the evidence audit, abstention is self-explanatory, and no unsupported geography or score reaches it."""

import json
from collections import Counter
from pathlib import Path

import pytest

from pipeline.risk import scoring_v2 as S

ROOT = Path(__file__).resolve().parents[2]
RISK = ROOT / "data" / "analytics" / "risk"
pytestmark = pytest.mark.skipif(not (RISK / "gold_operational_risk.jsonl").exists(), reason="risk output not generated in this environment")


def _rows():
    return [json.loads(x) for x in (RISK / "gold_operational_risk.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def test_production_rows_equal_audit_cells_so_nothing_eligible_is_silently_ignored():
    audit = json.loads((RISK / "score_v2_audit.json").read_text(encoding="utf-8"))
    rows = _rows()
    assert len(rows) == audit["cells_assessed"] == 1771
    summary = json.loads((RISK / "risk_run_summary.json").read_text(encoding="utf-8"))
    assert summary["risk_rows"] == len(rows) and summary["gauge_geography"]["eligible_stations"] == 2
    assert summary["gauge_geography"]["mapping_version"] == "gauge-geo-3.0.0"


def test_risk_rows_are_unique_scoreless_and_explicit():
    rows = _rows()
    keys = [(r["admin_unit_id"], r["date"]) for r in rows]
    assert len(keys) == len(set(keys))
    assert all(r["risk_score"] is None and r["risk_status"] and r["risk_basis"] for r in rows)
    assert all(r["admin_unit_id"] is not None for r in rows)


def test_gauge_signals_exist_only_for_the_two_evidence_backed_units():
    gauge_units = Counter(r["admin_unit_name"] for r in _rows() if r["signal_states"].get("gauge") == "OBSERVED")
    assert set(gauge_units) == {"Mianwali", "Jhang"}, gauge_units         # no secondary-only, conflicting, caveated or unresolved station reaches a unit
    mapping = {m["station_name"]: m for m in json.loads((ROOT / "data" / "analytics" / "geo" / "gauge_station_mapping.json").read_text(encoding="utf-8"))}
    eligible = {m["admin_unit_name"] for m in mapping.values() if m["eligible_for_admin_risk"]}
    assert eligible == {"Mianwali", "Jhang"}


def test_no_unit_has_two_independent_groups_from_gauge_alone_so_the_score_stays_abstained():
    audit = json.loads((RISK / "score_v2_audit.json").read_text(encoding="utf-8"))
    assert audit["cells_with_required_independent_groups"] == 8 and audit["cells_scored"] == 0
    assert audit["evidence_based_weights_defined"] == [] and audit["scoring_enabled"] is False


def test_abstention_block_explains_available_missing_and_required_evidence():
    block = S.abstain_from_stored_row({"risk_score": None, "signals": {"rainfall": None, "weather": None, "gauge": 0.4, "air_quality": None,
                                                                        "hazard_alert": None, "disaster_event": 0.2}}, S.SERVING_CONFIG)
    assert block["score_status"] == S.ABSTAINED and block["abstention_reason"] == S.R_NO_WEIGHTS
    assert block["evidence_available"] == ["disaster_event", "gauge"] == block["observed_domains"]
    assert block["evidence_missing"] == ["air_quality", "rainfall", "weather"]           # numeric domains only: contextual ones are never 'missing numeric evidence'
    req = " ".join(block["evidence_required"])
    assert "2 independent eligible signal groups" in req and "30 prior observations" in req and "evidence reference" in req and "disabled" in req
    assert "does NOT mean low risk" in block["interpretation"]


def test_no_signals_at_all_is_distinguishable_from_a_low_status():
    none = S.abstain_from_stored_row({"risk_score": None, "signals": {d: None for d in S.SERVING_CONFIG["independence_groups"]}}, S.SERVING_CONFIG)
    assert none["evidence_available"] == [] and set(none["evidence_missing"]) == set(S.SERVING_CONFIG["numeric_domains"])


def test_a_stored_score_would_pass_through_without_an_abstention():
    ok = S.abstain_from_stored_row({"risk_score": 41.5, "signals": {}}, S.SERVING_CONFIG)
    assert ok["score_status"] == S.SCORED and ok["abstention_reason"] is None
