"""Task 36 -- the operational risk score v2 foundation: evidence contract, eligibility, contributions, aggregation and abstention. Expected values are computed BY HAND in
the tests (not by calling the implementation): e.g. 100 * (2*0.8 + 1*0.4) / (2+1) = 66.6667. The shipped config has no weights, so the shipped behaviour is: always abstain."""

import copy
import math
import random
import re
from pathlib import Path

import pytest
import yaml

from pipeline.risk import scoring_v2 as S

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = yaml.safe_load((ROOT / "config" / "risk_score_v2.yaml").read_text(encoding="utf-8"))
WEIGHTED = {**copy.deepcopy(SHIPPED), "enabled": True, "weights": {"hydromet_event": {"weight": 2, "evidence_reference": "test fixture only"},
                                                                   "air_quality": {"weight": 1, "evidence_reference": "test fixture only"},
                                                                   "temperature": {"weight": 1, "evidence_reference": "test fixture only"}}}


def obs(domain="rainfall", normalized=0.8, history=40, value=12.0, unit=9, date="2026-07-17", obs_date=None, geo="resolved", caveat=False, ids=("rec-1",), source="pdma"):
    return {"domain": domain, "unit": unit, "cell_date": date, "obs_date": obs_date or date, "value": value, "normalized": normalized, "history_count": history,
            "geography_status": geo, "geography_caveat": caveat, "source": source, "source_record_ids": list(ids)}


# --------------------------------------------------------------------------------------------------------------------------- the shipped contract
def test_shipped_config_is_honest_and_the_api_constant_mirrors_it():
    assert SHIPPED["enabled"] is False and SHIPPED["weights"] == {} and SHIPPED["min_history_for_score"] == 30 and SHIPPED["required_independent_groups"] == 2
    assert S.SERVING_CONFIG == SHIPPED, "config/risk_score_v2.yaml and scoring_v2.SERVING_CONFIG diverged"
    assert set(S.SERVING_CONFIG) == set(SHIPPED)


def test_shipped_behaviour_never_produces_a_score_even_with_perfect_evidence():
    cell = [obs("rainfall", 0.9), obs("air_quality", 0.7, ids=("aqi-1",), source="epa_punjab")]
    r = S.assess_cell(cell, SHIPPED)
    assert r["risk_score"] is None and r["score_status"] == S.ABSTAINED and r["eligible_signal_count"] == 2 and r["contributing_group_count"] == 2
    assert r["abstention_reasons"] == [S.R_NO_WEIGHTS, S.R_DISABLED] and r["abstention_reason"] == S.R_NO_WEIGHTS and r["abstention_text"]


# ---------------------------------------------------------------------------------------------------------------------------------- eligibility
def test_raw_observation_becomes_a_normalized_contribution():
    a = S.assess_signal(obs("rainfall", normalized=0.8, history=40), SHIPPED)
    assert a["eligibility"] == S.ELIGIBLE and a["contribution"] == 0.8 and a["normalization"]["method"] == "percentile_rank_strict_prior"
    assert a["normalization"]["history_count"] == 40 and a["normalization"]["min_history"] == 30 and a["independence_group"] == "hydromet_event"


@pytest.mark.parametrize("kw,code", [
    ({"history": 29}, S.INSUFFICIENT_DATA), ({"normalized": None}, S.INSUFFICIENT_DATA), ({"value": None}, S.INSUFFICIENT_DATA),
    ({"obs_date": "2026-07-16"}, S.INSUFFICIENT_DATA),                                    # exact date: no carry-forward of yesterday's observation
    ({"geo": "unresolved"}, S.UNRESOLVED_GEOGRAPHY), ({"geo": "ambiguous"}, S.UNRESOLVED_GEOGRAPHY), ({"unit": None}, S.UNRESOLVED_GEOGRAPHY),
    ({"caveat": True}, S.UNRESOLVED_GEOGRAPHY),
    ({"value": float("nan")}, S.INVALID), ({"value": float("inf")}, S.INVALID), ({"value": -3.0}, S.INVALID), ({"normalized": 1.2}, S.INVALID), ({"normalized": -0.1}, S.INVALID),
    ({"value": "12"}, S.INVALID), ({"value": True}, S.INVALID),
])
def test_ineligible_observations_make_no_contribution(kw, code):
    a = S.assess_signal(obs(**kw), SHIPPED)
    assert a["eligibility"] == code and a["contribution"] is None and a["reason"]


def test_missing_history_means_no_normalization_not_a_zero():
    a = S.assess_signal(obs(history=0, normalized=None), SHIPPED)
    assert a["eligibility"] == S.INSUFFICIENT_DATA and a["contribution"] is None and "no defensible normalization" in a["reason"]


@pytest.mark.parametrize("domain,why", [("hazard_alert", "contextual"), ("disaster_event", "contextual"), ("documents", "not part"), ("rag_relevance", "not part"),
                                        ("ml_prediction", "not part"), ("baseline_forecast", "not part"), ("reservoir", "not part")])
def test_contextual_documentary_and_ml_domains_are_out_of_scope(domain, why):
    a = S.assess_signal(obs(domain, normalized=0.99, history=99), SHIPPED)
    assert a["eligibility"] == S.OUT_OF_SCOPE and a["contribution"] is None and why in a["reason"]


def test_gauge_without_an_authoritative_geography_never_contributes():
    for geo in ("unresolved", "ambiguous", "resolved_inferred", "caveated"):
        assert S.assess_signal(obs("gauge", geo=geo), SHIPPED)["eligibility"] == S.UNRESOLVED_GEOGRAPHY
    assert S.assess_signal(obs("gauge", unit=None, geo="unresolved"), SHIPPED)["contribution"] is None


# ------------------------------------------------------------------------------------------------------------------------------- aggregation
def test_weighted_score_matches_a_hand_computed_value():
    cell = [obs("rainfall", 0.8), obs("air_quality", 0.4, ids=("aqi-1",), source="epa_punjab")]
    r = S.assess_cell(cell, WEIGHTED)
    assert r["score_status"] == S.SCORED and r["risk_score"] == pytest.approx(66.6667, abs=1e-4)          # 100*(2*0.8 + 1*0.4)/3
    assert r["abstention_reason"] is None and r["abstention_reasons"] == [] and set(r["score_provenance"]["weights"]) == {"hydromet_event", "air_quality"}
    assert r["score_provenance"]["weights"]["hydromet_event"]["evidence_reference"] == "test fixture only"
    three = S.assess_cell(cell + [obs("weather", 0.6, source="pmd", ids=("w-1",))], WEIGHTED)
    assert three["risk_score"] == pytest.approx(100 * (2 * 0.8 + 1 * 0.4 + 1 * 0.6) / 4, abs=1e-4)          # 70.0


def test_one_signal_per_independence_group_no_double_counting():
    cell = [obs("rainfall", 0.9, ids=("r-1",)), obs("gauge", 0.5, ids=("g-1",), source="pdma"), obs("air_quality", 0.1, ids=("a-1",), source="epa_punjab")]
    r = S.assess_cell(cell, WEIGHTED)
    assert [c["domain"] for c in r["contributing_signals"]] == ["air_quality", "rainfall"]                  # sorted by group; rainfall represents hydromet_event
    assert r["risk_score"] == pytest.approx(100 * (2 * 0.9 + 1 * 0.1) / 3, abs=1e-4)                       # gauge (0.5) is NOT summed with rainfall
    gauge = next(e for e in r["excluded_signals"] if e["domain"] == "gauge")
    assert gauge["eligibility"] == S.OUT_OF_SCOPE and "overlaps" in gauge["reason"] and gauge["contribution"] is None and r["eligible_signal_count"] == 3


def test_hazard_alerts_and_disaster_events_never_enter_the_score():
    cell = [obs("rainfall", 0.8), obs("air_quality", 0.4), obs("hazard_alert", None, history=0, value=1.0), obs("disaster_event", None, history=0, value=5.0)]
    r = S.assess_cell(cell, WEIGHTED)
    assert r["risk_score"] == pytest.approx(66.6667, abs=1e-4)
    assert {e["domain"] for e in r["excluded_signals"]} == {"hazard_alert", "disaster_event"} and all(e["eligibility"] == S.OUT_OF_SCOPE for e in r["excluded_signals"])


@pytest.mark.parametrize("cell,reason", [
    ([], S.R_NO_ELIGIBLE), ([obs("rainfall", history=3)], S.R_NO_ELIGIBLE), ([obs("gauge", geo="unresolved")], S.R_NO_ELIGIBLE),
    ([obs("rainfall", 0.8)], S.R_TOO_FEW_GROUPS), ([obs("rainfall", 0.8), obs("gauge", 0.9)], S.R_TOO_FEW_GROUPS),                    # one group, even with two domains
])
def test_abstention_reasons_are_exact_when_the_data_contract_fails(cell, reason):
    r = S.assess_cell(cell, WEIGHTED)
    assert r["risk_score"] is None and r["abstention_reason"] == reason and r["score_status"] == S.ABSTAINED


@pytest.mark.parametrize("weights", [{}, {"hydromet_event": {"weight": 2}}, {"hydromet_event": {"weight": 2, "evidence_reference": "  "}},
                                     {"hydromet_event": {"weight": 0, "evidence_reference": "x"}}, {"hydromet_event": {"weight": -1, "evidence_reference": "x"}},
                                     {"hydromet_event": {"weight": float("nan"), "evidence_reference": "x"}},
                                     {"hydromet_event": {"weight": 2, "evidence_reference": "x"}}])                                  # air_quality group has no weight
def test_weights_without_evidence_or_for_only_some_groups_are_rejected(weights):
    cfg = {**copy.deepcopy(WEIGHTED), "weights": weights}
    r = S.assess_cell([obs("rainfall", 0.8), obs("air_quality", 0.4)], cfg)
    assert r["risk_score"] is None and r["abstention_reason"] == S.R_NO_WEIGHTS


def test_disabled_scoring_abstains_even_with_valid_weights():
    r = S.assess_cell([obs("rainfall", 0.8), obs("air_quality", 0.4)], {**copy.deepcopy(WEIGHTED), "enabled": False})
    assert r["risk_score"] is None and r["abstention_reasons"] == [S.R_DISABLED]


def test_score_is_reproducible_order_independent_and_bounded():
    rng = random.Random(7)
    for _ in range(200):
        cell = [obs("rainfall", rng.random()), obs("gauge", rng.random()), obs("air_quality", rng.random(), ids=("a",)), obs("weather", rng.random(), ids=("w",)),
                obs("hazard_alert", None, history=0), obs("disaster_event", None, history=0)]
        a = S.assess_cell(cell, WEIGHTED)
        b = S.assess_cell(list(reversed(cell)), WEIGHTED)
        assert a == b and S.assess_cell(cell, WEIGHTED) == a                                  # same input -> identical result, any order
        assert a["risk_score"] is not None and 0.0 <= a["risk_score"] <= 100.0 and math.isfinite(a["risk_score"])
        picked = [max(o["normalized"] for o in cell if o["domain"] in ("rainfall", "gauge")), cell[2]["normalized"], cell[3]["normalized"]]
        assert a["risk_score"] == pytest.approx(100 * (2 * picked[0] + picked[1] + picked[2]) / 4, abs=1e-3)       # independent expectation


def test_extremes_map_to_the_scale_ends():
    lo = S.assess_cell([obs("rainfall", 0.0), obs("air_quality", 0.0)], WEIGHTED)["risk_score"]
    hi = S.assess_cell([obs("rainfall", 1.0), obs("air_quality", 1.0)], WEIGHTED)["risk_score"]
    assert lo == 0.0 and hi == 100.0


def test_provenance_is_complete_for_every_assessed_signal():
    r = S.assess_cell([obs("rainfall", 0.8, ids=("r-1", "r-2")), obs("air_quality", 0.4, ids=("a-1",), source="epa_punjab"), obs("hazard_alert", None, history=0, ids=("al-1",)),
                       obs("weather", 0.3, history=2, ids=("w-1",))], WEIGHTED)
    for a in r["contributing_signals"] + r["excluded_signals"]:
        assert {"domain", "source", "observation_date", "admin_unit_id", "value", "normalization", "contribution", "eligibility", "provenance", "reason"} <= set(a)
        assert a["provenance"]["source_record_ids"] and a["normalization"]["method"] and a["normalization"]["reference"] and a["eligibility"] in S.ELIGIBILITIES
    assert r["contributing_signals"][0]["provenance"]["source_record_ids"] in (["r-1", "r-2"], ["a-1"])


# ---------------------------------------------------------------------------------------------------------------------- stored-row / API form
def test_stored_row_representation_abstains_and_never_invents_a_score():
    row = {"risk_score": None, "signals": {"rainfall": 0.9, "weather": None, "gauge": None, "air_quality": 0.7, "hazard_alert": 1.0, "disaster_event": 3.0}}
    r = S.abstain_from_stored_row(row, S.SERVING_CONFIG)
    assert r["score_status"] == S.ABSTAINED and r["abstention_reason"] == S.R_NO_WEIGHTS and r["contributing_signals"] == [] and r["score_version"] == SHIPPED["score_version"]
    assert {e["domain"] for e in r["excluded_signals"]} == {"hazard_alert", "disaster_event"} and r["observed_domains"] == ["air_quality", "disaster_event", "hazard_alert", "rainfall"]
    assert S.abstain_from_stored_row({"risk_score": 41.5, "signals": {}}, S.SERVING_CONFIG)["score_status"] == S.SCORED      # a stored score is passed through, never recomputed


# -------------------------------------------------------------------------------------------------------------------------------- isolation
def test_the_scoring_module_cannot_see_documents_ml_or_geography_resolution():
    src = (ROOT / "pipeline" / "risk" / "scoring_v2.py").read_text(encoding="utf-8")
    imports = set(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M))
    assert imports <= {"__future__", "math", "typing"}, imports
    assert not re.search(r"pipeline\.(rag|ml|intelligence|agents|geo)|scripts\.geo|sqlalchemy|datetime|random", src)
