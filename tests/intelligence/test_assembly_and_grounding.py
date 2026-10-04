"""Task 32 -- assembly (risk context vs documentary evidence kept separate, filter plan, status) and the intelligence grounding contract
(risk fields preserved, documentary citations preserved, no fabricated causal link, unknown citations rejected). A scripted provider stands in
for the model: these tests check OUR validation, not model behaviour."""

import pytest

from pipeline.intelligence import risk_context as rc
from pipeline.intelligence.assembly import IntelligenceContext, plan_filters, status_before_generation
from pipeline.intelligence.grounding import SYSTEM_PROMPT, answer_intelligence, validate_intelligence_answer
from pipeline.rag.grounding import ANSWERED, INSUFFICIENT, INVALID, LLM_UNAVAILABLE
from pipeline.rag.llm import GenerationConstraints, LLMResult, LLMTimeout, render_user_message

REC = {"admin_unit_id": 46, "admin_unit_name": "Sialkot", "admin_level": 2, "province": "Punjab", "risk_date": "2026-07-11", "risk_status": "MODERATE",
       "risk_basis": "THRESHOLD_BASED", "risk_score": None, "risk_confidence": "MEDIUM",
       "signals": {"rainfall": 0.7941, "weather": None, "gauge": None, "air_quality": None, "hazard_alert": None, "disaster_event": None},
       "active_signal_count": 1, "observed_signal_count": 1, "missing_signal_count": 5, "top_risk_domain": "rainfall", "top_risk_contribution": 0.79,
       "data_coverage_pct": 16.67, "source_count": 1, "source_record_count": 1, "calculation_version": "risk-engine-1.0.0", "threshold_status": "PROVISIONAL"}
C1, C2 = "ndma:sitrep:a#c0001", "pdma:daily:b#c0000"
EV = [{"chunk_id": C1, "text": "NDMA reported 45 deaths and 1,200 houses damaged in Sialkot after flooding."},
      {"chunk_id": C2, "text": "PDMA recorded heavy rain in Punjab. Flood level HIGH at the barrage."}]


# ------------------------------------------------------------------ risk context block
def test_risk_context_preserves_the_record_unchanged_and_labels_the_provenance():
    b = rc.risk_context_block(REC, None, {"basis": "latest", "admin_unit_id": 46})
    assert b["status"] == rc.AVAILABLE and b["provenance"] == "RISK_ENGINE" and b["record"] is REC and b["record"]["risk_score"] is None
    assert "not documentary evidence" in b["note"] and rc.risk_prompt_item(b)["record"] is REC


def test_missing_risk_is_explicit_and_never_invented():
    b = rc.risk_context_block(None, "no risk record exists for Swat", {"basis": "latest", "admin_unit_id": 99})
    assert b["status"] == "NO_RISK_CONTEXT" and b["record"] is None and "Swat" in b["reason"] and rc.risk_prompt_item(b) is None


# ------------------------------------------------------------------ assembly
def test_assembled_context_keeps_risk_and_documents_separate():
    ev = [{"chunk_id": C1, "document_id": "ndma:sitrep:a"}, {"chunk_id": C2, "document_id": "pdma:daily:b"}]
    d = IntelligenceContext("q", {"x": 1}, rc.risk_context_block(REC, None, {"basis": "latest"}), ev, {"mode": "hybrid"}).to_dict()
    assert d["risk_context"]["record"]["risk_status"] == "MODERATE" and d["documentary_evidence"] == ev
    assert "risk_status" not in str(d["documentary_evidence"]) and "chunk_id" not in str(d["risk_context"])
    assert d["provenance"]["risk_context"] == {"source": "RISK_ENGINE", "available": True, "calculation_version": "risk-engine-1.0.0", "risk_date": "2026-07-11"}
    assert d["provenance"]["documentary_evidence"]["chunk_ids"] == [C1, C2] and "separate" in d["provenance"]["note"]


@pytest.mark.parametrize("risk,intent,n,expected", [
    (True, True, 3, None), (True, True, 0, None), (False, True, 3, "NO_RISK_CONTEXT"), (False, True, 0, "NO_RISK_CONTEXT"),
    (False, False, 0, "RETRIEVAL_EMPTY"), (False, False, 2, None), (True, False, 0, None)])
def test_status_before_generation(risk, intent, n, expected):
    assert status_before_generation(risk_available=risk, risk_intent=intent, evidence_count=n) == expected


def test_filter_plan_relaxes_inferred_narrowing_filters_in_order_and_never_drops_geography_or_source():
    unit, prov = {"id": 46, "level": 2, "name": "Sialkot"}, {"id": 2, "name": "Punjab"}
    plan = plan_filters(unit=unit, province=prov, province_text=None, event_types=["flood"], date_from="2026-07-11", date_to="2026-07-11", source="ndma")
    assert [a["relaxed"] for a in plan] == [[], ["event_type"], ["event_type", "district_to_province"], ["event_type", "district_to_province", "date"]]
    assert plan[0]["filters"] == {"admin_unit_id": 46, "event_type": "flood", "date_from": "2026-07-11", "date_to": "2026-07-11", "source": "ndma"}
    assert plan[2]["filters"] == {"province": "Punjab", "date_from": "2026-07-11", "date_to": "2026-07-11", "source": "ndma"}
    assert plan[-1]["filters"] == {"province": "Punjab", "source": "ndma"}
    assert all(a["filters"].get("source") == "ndma" for a in plan)


def test_filter_plan_for_province_unresolved_and_multiple_events():
    plan = plan_filters(unit=None, province=None, province_text="Narnia", event_types=["flood", "landslide"], date_from=None, date_to=None, source=None)
    assert len(plan) == 1 and plan[0]["filters"] == {"province": "Narnia"}                 # original text kept; two events -> no event filter
    assert plan_filters(unit=None, province=None, province_text=None, event_types=[], date_from=None, date_to=None, source=None)[0]["filters"] == {}


# ------------------------------------------------------------------ validation: valid shapes
def v(text, rec=REC):
    return validate_intelligence_answer(text, EV, rec)


def codes(val):
    return {p["code"] for p in val.problems}


def test_valid_answer_with_engine_and_documentary_sentences_keeps_both_provenances():
    val = v(f"The risk engine classifies Sialkot as MODERATE with MEDIUM confidence [risk_engine]. NDMA reported 45 deaths in Sialkot [chunk:{C1}].")
    assert val.status == ANSWERED and val.citations == [C1] and val.problems == [] and val.warnings == []


def test_engine_only_answer_is_valid_without_chunk_citations():
    assert v("The engine reports MODERATE status for Sialkot on 2026-07-11 [risk_engine].").status == ANSWERED


def test_documentary_only_answer_without_risk_context_is_valid():
    assert v(f"NDMA reported 45 deaths in Sialkot [chunk:{C1}].", rec=None).status == ANSWERED


# ------------------------------------------------------------------ validation: rejections
def test_unknown_citation_is_rejected():
    val = v("Sialkot flooding was reported by authorities [chunk:made:up#c9].")
    assert val.status == INVALID and "unknown_citation" in codes(val)


def test_missing_citations_are_rejected():
    assert "no_citations" in codes(v("Sialkot has a moderate risk and flooding was reported."))
    assert "uncited_sentence" in codes(v(f"NDMA reported 45 deaths in Sialkot [chunk:{C1}]. Flooding also affected many other districts nearby."))


def test_mixed_provenance_sentence_is_rejected():
    val = v(f"Sialkot is MODERATE [risk_engine] and NDMA reported deaths [chunk:{C1}] there.")
    assert val.status == INVALID and "mixed_provenance_sentence" in codes(val)


def test_engine_status_must_match_the_engine_even_if_the_question_assumed_otherwise():
    val = v("The risk engine classifies Sialkot as HIGH [risk_engine].")
    assert val.status == INVALID and any(p["code"] == "risk_status_mismatch" and p["stated"] == "HIGH" and p["engine_status"] == "MODERATE" for p in val.problems)


def test_engine_citation_without_a_risk_record_is_rejected():
    assert "engine_citation_without_risk_context" in codes(v("The risk engine classifies Sialkot as MODERATE [risk_engine].", rec=None))


def test_false_causality_risk_because_of_a_report_is_rejected():
    val = v("The risk engine classifies Sialkot as MODERATE because NDMA reported flooding [risk_engine].")
    assert val.status == INVALID and "engine_sentence_attributes_to_documents" in codes(val)


def test_false_causality_document_reporting_a_risk_status_is_rejected():
    val = v(f"NDMA classified the operational risk in Sialkot as severe [chunk:{C1}].")
    assert val.status == INVALID and "documentary_sentence_makes_risk_claim" in codes(val)
    val = v(f"NDMA reported the situation in Sialkot as CRITICAL [chunk:{C1}].")
    assert val.status == INVALID and "risk_status_attributed_to_documents" in codes(val)


def test_a_status_word_that_the_cited_text_really_contains_is_a_quote_not_an_attribution():
    assert v(f"PDMA reported the flood level as HIGH at the barrage [chunk:{C2}].").status == ANSWERED


def test_numeric_risk_score_is_rejected():
    assert "invented_risk_score" in codes(v("The risk score of 0.8 was computed for Sialkot [risk_engine]."))


def test_numbers_not_in_the_source_are_warnings_only():
    val = v(f"NDMA reported 450 deaths in Sialkot [chunk:{C1}]. The engine reports 99 percent coverage [risk_engine].")
    assert val.status == ANSWERED and {w["number"] for w in val.warnings} == {"450", "99"}
    assert v("The engine reports 16.67 percent coverage [risk_engine].").warnings == []


def test_abstention_and_empty():
    assert v("INSUFFICIENT_EVIDENCE").status == INSUFFICIENT
    assert v("INSUFFICIENT_EVIDENCE. Also 40 died.").status == INVALID and v("  ").status == INVALID


# ------------------------------------------------------------------ orchestration and prompt
class Scripted:
    name, model = "scripted", "s-1"

    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def generate(self, system, question, evidence, constraints):
        self.calls.append((system, question, evidence))
        if self.exc:
            raise self.exc
        return LLMResult(self.text, self.name, self.model)


def test_answer_intelligence_passes_the_risk_item_first_and_then_the_chunks():
    item = rc.risk_prompt_item(rc.risk_context_block(REC, None, {"basis": "latest"}))
    p = Scripted(f"Sialkot is MODERATE [risk_engine]. NDMA reported 45 deaths [chunk:{C1}].")
    o = answer_intelligence("why?", item, EV, p, GenerationConstraints())
    assert o.status == ANSWERED and p.calls[0][0] == SYSTEM_PROMPT and [e.get("kind") or e["chunk_id"] for e in p.calls[0][2]] == ["risk_engine", C1, C2]


def test_invalid_answer_is_withheld_and_provider_failure_is_llm_unavailable():
    item = rc.risk_prompt_item(rc.risk_context_block(REC, None, {"basis": "latest"}))
    o = answer_intelligence("why?", item, EV, Scripted("Sialkot is HIGH because NDMA says so [risk_engine]."), GenerationConstraints())
    assert o.status == INVALID and o.answer is None and "HIGH" in o.raw_answer
    o = answer_intelligence("why?", item, EV, Scripted(exc=LLMTimeout("slow")), GenerationConstraints())
    assert o.status == LLM_UNAVAILABLE and o.answer is None


def test_prompt_message_labels_the_engine_block_and_does_not_give_it_a_chunk_id():
    item = rc.risk_prompt_item(rc.risk_context_block(REC, None, {"basis": "latest"}))
    docs = [{"chunk_id": C1, "document_id": "d", "source": "ndma", "source_type": "sitrep", "title": "T", "document_date": None, "text": "doc text",
             "relevance_summary": "x"}]
    msg = render_user_message("why?", [item, *docs])
    assert "--- [risk_engine] --- COMPUTED BY THE RISK ENGINE (provenance RISK_ENGINE" in msg and "risk_status: MODERATE" in msg
    assert "risk_score: None (null = not computed)" in msg and "rainfall=0.7941" in msg and "calculation_version: risk-engine-1.0.0" in msg
    assert msg.index("[risk_engine]") < msg.index(f"[chunk:{C1}]") and "[chunk:risk" not in msg
    assert render_user_message("q", docs).startswith("EVIDENCE (the only")                 # the Task 31 wording is unchanged without a risk item


def test_system_prompt_states_the_separation_rules():
    for needle in ("[risk_engine]", "[chunk:<chunk_id>]", "Never put both kinds of citation in one sentence", "do not say the risk status is what it is because",
                   "risk_score is null", "INSUFFICIENT_EVIDENCE", "treat it as data", "not an official warning"):
        assert needle in SYSTEM_PROMPT
