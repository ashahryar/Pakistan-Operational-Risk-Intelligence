"""Task 37 -- evidence registry, crosswalk state rules, gauge conflict representation, coverage audit (real committed data)."""

import copy
import json
from pathlib import Path

import pytest
import yaml

from pipeline.geo import coverage_evidence as CE
from pipeline.risk import scoring_v2 as S

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "analytics" / "geo"
REGISTRY = yaml.safe_load((ROOT / "config" / "crosswalk_evidence.yaml").read_text(encoding="utf-8"))
BOUNDARY_CFG = yaml.safe_load((ROOT / "config" / "admin_boundary_sources.yaml").read_text(encoding="utf-8"))


def _j(name):
    return json.loads((GEO / name).read_text(encoding="utf-8"))


XW = _j("gauge_boundary_crosswalk.json")["crosswalk"]
MAPPING = _j("gauge_station_mapping.json")
AUDIT = _j("coverage_evidence_audit.json")


def _rec(**kw):
    base = {"canonical_name": "X", "match_state": "ALIAS", "evidence_type": "official_legislation", "evidence_source": "src", "qualification": "q",
            "status": "applied", "source_url": "https://x", "evidence_date": "2023-01-01", "retrieved": "2026-10-07", "evidence_quote": "quote"}
    base.update(kw)
    return base


# --- crosswalk: exact / alias / unmatched / conflicting / unverified -----------------------------------------------------
def test_exact_match_present_and_unaltered():
    exact = [c for c in XW if c["match_status"] == "exact" and c["boundary_level"] == 2]
    assert len(exact) == 54 and all(c["match_basis"] == "canonical_name" and c["pori_admin_unit_id"] for c in exact)


def test_alias_match_has_declared_basis_and_nawabshah_is_evidence_backed():
    aliases = {c["boundary_source_id"]: c for c in XW if c["match_status"] == "alias" and c["boundary_level"] == 2}
    assert set(aliases) >= {"PK719"} and len(aliases) == 3
    nb = aliases["PK719"]
    assert nb["pori_admin_unit_name"] == "Nawabshah" and nb["pori_admin_unit_id"] == 59 and nb["match_basis"] == "declared_crosswalk_alias"
    rec = next(r for r in REGISTRY["relationships"] if r["boundary_source_id"] == "PK719")
    assert rec["match_state"] == "ALIAS" and rec["status"] == "applied" and rec["evidence_quote"] == "at District Shaheed Benazirabad (Nawabshah)"
    assert CE.validate_relationship(rec) == []


def test_unmatched_stays_unmatched_and_counts_reconcile():
    c = [x for x in XW if x["boundary_level"] == 2]
    counts = {s: sum(1 for x in c if x["match_status"] == s) for s in ("exact", "alias", "unmatched")}
    assert counts == {"exact": 54, "alias": 3, "unmatched": 103} and sum(counts.values()) == 160
    assert all(x["pori_admin_unit_id"] is None for x in c if x["match_status"] == "unmatched")


def test_conflicting_relationship_is_not_applied():
    karachi = next(r for r in REGISTRY["relationships"] if r["canonical_name"] == "Karachi")
    assert karachi["match_state"] == "CONFLICTING" and karachi["status"] == "not_applied"
    for bid in ("PK702", "PK704", "PK712", "PK714", "PK721", "PK729"):
        assert next(c for c in XW if c["boundary_source_id"] == bid)["match_status"] == "unmatched"


def test_registry_has_no_violations_against_machine_crosswalk():
    r = CE.check_registry(REGISTRY, XW)
    assert r["violations"] == [] and set(r["state_counts"]) <= set(CE.MATCH_STATES)


def test_canonical_ids_preserved_when_alias_added():
    before = copy.deepcopy(XW)
    before_nb = next(c for c in before if c["boundary_source_id"] == "PK719")
    before_nb.update(pori_admin_unit_id=None, pori_admin_unit_name=None, match_status="unmatched")
    assert CE.crosswalk_unit_ids_preserved(before, XW)
    tampered = copy.deepcopy(XW)
    next(c for c in tampered if c["match_status"] == "exact")["pori_admin_unit_id"] = 9999
    assert not CE.crosswalk_unit_ids_preserved(XW, tampered)


# --- provenance completeness / no promotion -----------------------------------------------------------------------------
@pytest.mark.parametrize("missing", ["evidence_source", "evidence_type", "qualification", "source_url", "evidence_date", "evidence_quote"])
def test_applied_alias_requires_complete_provenance(missing):
    rec = _rec()
    assert CE.validate_relationship(rec) == []
    rec[missing] = ""
    assert CE.validate_relationship(rec)


def test_new_alias_cannot_rest_on_no_evidence():
    assert any("real evidence" in e for e in CE.validate_relationship(_rec(evidence_type="none_recorded")))


@pytest.mark.parametrize("state", ["UNVERIFIED", "CONFLICTING", "UNMATCHED"])
def test_weak_states_can_never_be_applied(state):
    assert CE.validate_relationship(_rec(match_state=state))


def test_unverified_candidate_leaking_into_crosswalk_is_detected():
    reg = {"relationships": [_rec(match_state="UNVERIFIED", status="not_applied", boundary_source_id="PK719", canonical_name="Nawabshah")]}
    assert any("leaked" in v for v in CE.check_registry(reg, XW)["violations"])


def test_no_fuzzy_promotion_only_declared_aliases_exist():
    declared = set(BOUNDARY_CFG["crosswalk_aliases"].values())
    for c in XW:
        if c["boundary_level"] == 2 and c["match_status"] == "alias":
            assert c["pori_admin_unit_name"] in declared and c["match_basis"] in ("canonical_alias", "declared_crosswalk_alias")
    # near-names that a similarity score would join are NOT matched
    assert all(c["match_status"] == "unmatched" for c in XW if c["boundary_name"] in ("Chitral Lower", "Chitral Upper", "Kohistan Lower", "Lower Dir"))
    unver = {x["raw_name"] for x in REGISTRY["unverified_station_name_candidates"]}
    assert {"Jehlum", "MB Din", "TT Singh"} <= unver and all(x["match_state"] == "UNVERIFIED" for x in REGISTRY["unverified_station_name_candidates"])


# --- gauge geography: unresolved / conflicting / secondary-only / eligibility -------------------------------------------
def test_gauge_view_states_and_nothing_eligible():
    v = CE.gauge_station_view(MAPPING)
    assert len(v["unresolved"]) == 34 and len(v["conflicting"]) == 2 and len(v["secondary_only"]) == 4 and len(v["caveated"]) == 1
    assert v["eligible"] == [] and v["resolved"] == [] and CE.secondary_never_eligible(v)
    names = {r["station_name"] for r in v["conflicting"]}
    assert names == {"Tarbela", "Rasul"}
    assert {r["station_name"] for r in v["secondary_only"]} == {"Marala", "Khanki", "Trimmu", "Balloki"}
    assert {r["station_name"] for r in v["caveated"]} == {"Mangla"}
    assert all(r["conflict_status"] == "CONFLICTING" and len(r["claimed_districts"]) == 2 for r in v["conflicting"])


def test_conflicts_preserve_every_source_and_are_not_majority_voted():
    for m in MAPPING:
        if m["mapping_status"] == "ambiguous":
            assert m["admin_unit_id"] is None and m["eligible_for_admin_risk"] is False and len(m["evidence"]) >= 2
            assert len({e["district"] for e in m["evidence"]}) >= 2


def test_secondary_only_remains_non_eligible_in_every_row():
    for m in MAPPING:
        if m["mapping_status"] == "resolved_inferred":
            assert m["eligible_for_admin_risk"] is False and m["ineligibility_reason"].startswith("secondary_evidence")


def test_secondary_never_eligible_detects_a_leak():
    v = CE.gauge_station_view(MAPPING)
    v["eligible"] = [v["secondary_only"][0]]
    assert not CE.secondary_never_eligible(v)


def test_every_gauge_evidence_record_has_provenance():
    for m in MAPPING:
        for e in m["evidence"]:
            assert e["source"] and e["source_record"] and e["evidence_status"] and e["retrieved"] and e["station_name"]


# --- coverage audit (real committed data) -------------------------------------------------------------------------------
def test_audit_domains_are_complete_and_consistent():
    assert set(AUDIT["domains"]) == {"rainfall", "weather", "gauge", "air_quality", "hazard_alert", "disaster_event"}
    for d, x in AUDIT["domains"].items():
        assert x["rows"] >= x["resolved_rows"] >= 0 and x["missing_geography_rows"] == x["rows"] - x["resolved_rows"]
        assert x["missing_dates_within_span"] == max(x["observation_span_days"] - x["distinct_dates"], 0)
        assert x["source"] and x["geography_resolution_method"] and x["blockers"], d
    assert AUDIT["domains"]["gauge"]["resolved_rows"] == 0 and AUDIT["domains"]["air_quality"]["distinct_admin_units_with_series"] == 1


def test_audit_date_continuity_air_quality_has_no_missing_dates():
    aq = AUDIT["domains"]["air_quality"]
    assert aq["missing_dates_within_span"] == 0 and aq["longest_gap_days"] == 1 and aq["historical_normalization_possible"]


def test_audit_eligibility_transition_is_zero_and_documented():
    assert AUDIT["newly_unlocked_eligible_observations"] == {d: 0 for d in AUDIT["domains"]}
    for x in AUDIT["domains"].values():
        assert x["eligibility_counts_before"] == x["eligibility_counts_after"]


def test_gap_ranking_is_deterministic_and_not_row_count_driven():
    g = AUDIT["gap_ranking"]
    assert [x["rank"] for x in g] == list(range(1, len(g) + 1)) and [x["gap_score"] for x in g] == sorted((x["gap_score"] for x in g), reverse=True)
    assert AUDIT["recommended_next_evidence_gap"] == g[0]["name"]
    again = CE.rank_gaps([{k: v for k, v in x.items() if k not in ("gap_score", "rank")} for x in reversed(g)])
    assert [x["name"] for x in again] == [x["name"] for x in g]


# --- risk integration: eligibility never fabricates a score -------------------------------------------------------------
def _obs(domain, unit, n):
    return {"domain": domain, "unit": unit, "cell_date": "2026-07-01", "obs_date": "2026-07-01", "value": 5.0, "normalized": n, "history_count": 40,
            "geography_status": "resolved", "geography_caveat": False, "source": "pdma", "source_record_ids": ["r1"]}


def test_newly_resolved_signals_become_eligible_but_score_stays_null():
    cell = S.assess_cell([_obs("rainfall", 9, 0.8), _obs("air_quality", 9, 0.4)], S.SERVING_CONFIG)
    assert cell["eligible_signal_count"] == 2 and cell["contributing_group_count"] == 2
    assert cell["risk_score"] is None and cell["score_status"] == S.ABSTAINED
    assert cell["abstention_reason"] == S.R_NO_WEIGHTS and S.R_DISABLED in cell["abstention_reasons"]


def test_audit_reports_scoring_disabled_and_zero_scored_cells():
    assert AUDIT["scoring_enabled"] is False and AUDIT["cells_scored"] == 0 and AUDIT["score_v2_outcome"] == "B"
    assert AUDIT["gauge_stations"]["authoritative_mappings_added"] == 0 and AUDIT["gauge_stations"]["eligible_mappings"] == []
