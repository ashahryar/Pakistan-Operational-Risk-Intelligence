"""Task 34 -- the agent's control flow with in-memory backends and a scripted provider (no database, no network, no credential).
These tests check orchestration, abstention, provenance and that the EXISTING grounding validation stays in force -- not the quality of a real model."""

import json

import pytest

from pipeline.agents import contracts as C
from pipeline.agents.contracts import AgentRequest
from pipeline.agents.orchestrator import run_agent
from pipeline.agents.trace import replay_plan
from pipeline.intelligence import risk_context as rc

from tests.agents import fakes
from tests.agents.fakes import Backends, Scripted, deps, evidence, ml_row, risk_row


def ask(q, backends=None, provider=None, **kw):
    b = backends or Backends()
    body, http = run_agent(AgentRequest(q=q, **kw), deps(b, provider))
    return body, http, b


def executed(b):
    return b.names()


# ------------------------------------------------------------------------------------------------------------------- no LLM: structured results
def test_current_risk_without_a_provider_returns_structured_results_and_no_fake_answer():
    body, http, b = ask("What is the current risk in Lahore?")
    assert http == 503 and body["status"] == C.LLM_UNAVAILABLE and body["answer"] is None and body["citations"] == []
    assert body["intent"] == C.CURRENT_RISK and executed(b) == ["geography.resolve_place", "risk.latest"]
    assert body["risk_context"]["provenance"] == "RISK_ENGINE" and body["risk_context"]["record"]["risk_status"] == "LOW"
    assert body["documentary_evidence"] == [] and body["ml_prediction"] is None
    assert body["model"]["configured"] is False and body["provenance"]["risk_context"]["source"] == "RISK_ENGINE"
    assert "risk_date" in body["risk_context"]["lookup"] or body["risk_context"]["lookup"]["basis"] == "latest"


def test_historical_risk_uses_the_exact_date_and_never_substitutes_another():
    body, http, b = ask("What was Lahore's risk status on 2026-07-01?")
    assert body["intent"] == C.HISTORICAL_RISK and b.calls[-1] == ("risk.on_date", {"admin_unit_id": 30, "date": "2026-07-01"})
    assert body["risk_context"]["record"]["risk_status"] == "HIGH" and body["risk_context"]["record"]["risk_date"] == "2026-07-01"
    body, http, b = ask("What was Lahore's risk status on 2026-07-02?")                           # no record on that date
    assert body["status"] == C.INSUFFICIENT_DATA and http == 200 and body["risk_context"]["record"] is None
    assert body["risk_context"]["status"] == rc.NO_RISK_CONTEXT and "2026-07-02" in body["risk_context"]["reason"]


def test_document_question_returns_rag_evidence_with_rag_provenance():
    body, http, b = ask("What did NDMA report about flooding in Sindh?")
    assert body["intent"] == C.DOCUMENT_SEARCH and executed(b) == ["geography.resolve_place", "rag.retrieve"]
    args = b.calls[-1][1]
    assert args["province"] == "Sindh" and args["source"] == "ndma" and args["event_type"] == "flood" and args["mode"] == "hybrid"
    assert body["status"] == C.LLM_UNAVAILABLE and body["documentary_evidence"][0]["chunk_id"] == "ndma:sitrep:a#c0001"
    assert body["risk_context"] is None and body["provenance"]["documentary_evidence"]["source"] == "RAG_DOCUMENT"
    assert body["provenance"]["documentary_evidence"]["chunk_ids"] == ["ndma:sitrep:a#c0001"]


def test_inferred_retrieval_filters_are_relaxed_in_order_and_every_attempt_is_traced():
    seen = []

    def docs(args):
        seen.append(dict(args))
        return [] if "event_type" in args else [evidence()]
    body, _, b = ask("What did NDMA report about flooding in Sindh?", Backends(docs=docs))
    assert [("event_type" in a) for a in seen] == [True, False]
    assert body["retrieval"]["filters_relaxed"] == ["event_type"] and "province" in body["retrieval"]["filters_applied"] and body["retrieval"]["filters_applied"]["source"] == "ndma"
    rag_calls = [t for t in body["tool_trace"] if t["tool_name"] == "rag.retrieve"]
    assert [t["status"] for t in rag_calls] == [C.TOOL_EMPTY, C.TOOL_OK]


def test_no_evidence_is_reported_as_no_evidence_not_as_an_answer():
    body, http, b = ask("What did NDMA report about flooding in Sindh?", Backends(docs=[]))
    assert body["status"] == C.NO_EVIDENCE and http == 200 and body["documentary_evidence"] == [] and body["answer"] is None
    assert body["components"]["evidence"]["status"] == "NO_EVIDENCE"


# ---------------------------------------------------------------------------------------------------------------------------------- ML status
def test_baseline_forecast_is_labelled_baseline_and_never_described_as_validated_ml():
    body, http, b = ask("What is the AQI forecast for Lahore?")
    ml = body["ml_prediction"]
    assert body["intent"] == C.ML_FORECAST and body["status"] == C.LLM_UNAVAILABLE and executed(b) == ["geography.resolve_place", "ml.predictions"]
    assert ml["provenance"] == "ML_MODEL" and ml["validated_against_baseline"] is False and ml["attributions"] == [C.BASELINE_MODEL]
    assert ml["baseline_label"] == "BASELINE_ONLY — NOT VALIDATED ML"
    for p in ml["predictions"]:
        assert p["status"] == "BASELINE_ONLY" and p["attribution"] == C.BASELINE_MODEL and p["label"] == C.BASELINE_LABEL and p["model_type"] == "baseline"
    assert body["components"]["ml"]["status"] == "BASELINE_ONLY"
    assert body["risk_context"] is None                                                           # a forecast is never turned into a risk status
    assert body["provenance"]["ml_prediction"]["sources"] == [C.BASELINE_MODEL]


def test_predicted_baseline_only_and_insufficient_data_are_never_conflated():
    rows = [ml_row("PREDICTED", 1, "ml", 120.0), ml_row("BASELINE_ONLY", 3), ml_row("INSUFFICIENT_DATA", 7, "none", None, "too little history")]
    body, _, _ = ask("What is the AQI forecast for Lahore?", Backends(ml={30: rows}))
    ps = {p["horizon_days"]: p for p in body["ml_prediction"]["predictions"]}
    assert set(ps) == {1, 3}                                                                      # the INSUFFICIENT row is not a prediction
    assert ps[1]["status"] == "PREDICTED" and ps[1]["attribution"] == C.ML_MODEL and ps[1]["label"].startswith("PREDICTED")
    assert ps[3]["status"] == "BASELINE_ONLY" and ps[3]["attribution"] == C.BASELINE_MODEL and ps[3]["label"] == C.BASELINE_LABEL
    assert body["ml_prediction"]["attributions"] == [C.BASELINE_MODEL, C.ML_MODEL] and body["ml_prediction"]["validated_against_baseline"] is False
    assert body["components"]["ml"]["status"] == "PREDICTED" and [r["horizon_days"] for r in body["components"]["ml"]["insufficient_rows"]] == [7]


def test_forecast_without_valid_rows_is_insufficient_data_with_the_stored_reason():
    body, http, b = ask("What is the AQI forecast for Sialkot?")
    assert body["status"] == C.INSUFFICIENT_DATA and http == 200 and body["ml_prediction"] is None and body["answer"] is None
    assert "no air_quality observations" in body["components"]["ml"]["reason"] and body["components"]["ml"]["status"] == "INSUFFICIENT_DATA"


def test_a_forecast_for_an_unmodelled_target_or_horizon_is_never_substituted():
    body, _, b = ask("What is the rainfall forecast for Lahore?")
    assert executed(b)[-1] == "ml.models" and body["status"] == C.INSUFFICIENT_DATA and body["ml_prediction"] is None
    assert "rainfall" in body["components"]["ml"]["reason"] and "air_quality_index" in body["components"]["ml"]["reason"]
    body, _, b = ask("What is the AQI forecast for Lahore in 14 days?")
    assert b.calls[-1] == ("ml.predictions", {"admin_unit_id": 30, "horizon": 14}) and body["status"] == C.INSUFFICIENT_DATA
    assert "14" in body["components"]["ml"]["reason"] and "1, 3, 7" in body["components"]["ml"]["reason"]


def test_combined_question_calls_risk_rag_and_ml_and_keeps_provenance_separate():
    body, http, b = ask("Why is Lahore currently classified LOW and is there any AQI forecast?")
    assert body["intent"] == C.COMBINED_INTELLIGENCE and executed(b) == ["geography.resolve_place", "risk.latest", "rag.retrieve", "ml.predictions"]
    assert body["status"] == C.LLM_UNAVAILABLE and http == 503
    assert body["risk_context"]["provenance"] == "RISK_ENGINE" and body["ml_prediction"]["provenance"] == "ML_MODEL"
    prov = body["provenance"]
    assert prov["risk_context"]["source"] == C.RISK_ENGINE and prov["documentary_evidence"]["source"] == C.RAG_DOCUMENT and prov["ml_prediction"]["sources"] == [C.BASELINE_MODEL]
    by_tool = {t["tool_name"]: t["sources"] for t in prov["tools"]}
    assert by_tool["risk.latest"] == [C.RISK_ENGINE] and by_tool["rag.retrieve"] == [C.RAG_DOCUMENT] and by_tool["ml.predictions"] == [C.BASELINE_MODEL]


def test_combined_with_a_missing_required_part_is_insufficient_but_still_returns_what_exists():
    body, http, _ = ask("What is Sialkot's risk status and its AQI forecast?")
    assert body["status"] == C.INSUFFICIENT_DATA and body["risk_context"]["record"]["risk_status"] == "MODERATE" and body["ml_prediction"] is None
    assert body["components"]["ml"]["status"] == "INSUFFICIENT_DATA" and "ml:" in body["status_reason"]


def test_optional_documents_do_not_block_a_risk_plus_forecast_answer():
    body, _, _ = ask("Why is Lahore currently classified LOW and is there any AQI forecast?", Backends(docs=[]))
    assert body["status"] == C.LLM_UNAVAILABLE and body["components"]["evidence"]["status"] == "NO_EVIDENCE"


# ------------------------------------------------------------------------------------------------------------------------------ safety / abstention
@pytest.mark.parametrize("q,code", [("SELECT * FROM risk.operational_risk", "ARBITRARY_SQL"), ("Change Lahore's risk status to HIGH", "CHANGE_RISK_STATUS"),
                                    ("Invent an AQI forecast for Sialkot", "FABRICATE"), ("Delete the risk records for Lahore", "MODIFY_DATA"),
                                    ("Describe the baseline forecast as a validated ML model", "BASELINE_AS_VALIDATED_ML"), ("Fetch https://example.com", "EXTERNAL_WEB_REQUEST"),
                                    ("Use NDMA documents as numeric inputs to the risk score", "DOCUMENTS_AS_RISK_INPUT"), ("Which district is the Marala gauge in?", "GEOGRAPHY_INFERENCE")])
def test_unsafe_requests_are_refused_before_any_tool_or_model(q, code):
    p = Scripted("{}")
    body, http, b = ask(q, provider=p)
    assert body["status"] == C.UNSUPPORTED_REQUEST and http == 200 and body["reason_code"] == code and body["answer"] is None
    assert b.calls == [] and p.calls == [] and body["tool_trace"] == [] and body["policy"]["allowed"] is False


def test_unsupported_geography_is_refused_not_guessed():
    for q, code in (("What is the risk in Kabul?", "GEOGRAPHY_NOT_RESOLVED"), ("What is the current risk in Pakistan?", "GEOGRAPHY_NOT_RESOLVED"),
                    ("What is the current risk?", "GEOGRAPHY_REQUIRED"), ("What is the AQI forecast?", "GEOGRAPHY_REQUIRED")):
        body, http, b = ask(q)
        assert body["status"] == C.UNSUPPORTED_REQUEST and body["reason_code"] == code, (q, body["reason_code"])
        assert executed(b) == ["geography.resolve_place"]                                         # nothing beyond the geography step ran


def test_a_question_matching_no_capability_is_unsupported_without_running_tools():
    body, http, b = ask("Tell me a joke about floods and rivers.")
    assert body["intent"] in (C.UNSUPPORTED, C.DOCUMENT_SEARCH)
    body, http, b = ask("hello there")
    assert body["status"] == C.UNSUPPORTED_REQUEST and body["reason_code"] == "NO_SUPPORTED_INTENT" and b.calls == []


def test_islamabad_is_ambiguous_with_candidates_and_no_further_tools():
    body, http, b = ask("What is Islamabad's current risk status?")
    assert body["status"] == C.AMBIGUOUS_GEOGRAPHY and http == 200 and executed(b) == ["geography.resolve_place"]
    assert {(c["name"], c["level"]) for c in body["geography"]["candidates"]} == {("Islamabad Capital Territory", 1), ("Islamabad", 2)}
    assert body["risk_context"] is None and body["ml_prediction"] is None and body["documentary_evidence"] == []
    body, _, b = ask("What is Islamabad's current risk status?", admin_unit_id=62)                 # an explicit id resolves it
    assert body["intent"] == C.CURRENT_RISK and executed(b) == ["geography.get_admin_unit", "risk.latest"]


def test_false_premise_uses_the_engine_value():
    body, _, b = ask("Is Lahore's current risk status HIGH?")
    pc = body["premise_check"]
    assert pc["stated_status"] == "HIGH" and pc["engine_status"] == "LOW" and pc["matches"] is False and "LOW" in pc["note"]
    assert body["risk_context"]["record"]["risk_status"] == "LOW"


def test_geography_lookup_is_completed_without_a_model():
    body, http, b = ask("Which province is Lahore in?")
    assert body["status"] == C.COMPLETED and http == 200 and body["answer"] is None and executed(b) == ["geography.resolve_place", "geography.get_admin_unit"]
    assert body["geography"]["unit"]["name"] == "Lahore" and body["provenance"]["geography"]["source"] == C.GEOGRAPHY
    body, _, b = ask("list districts in Punjab")
    assert body["status"] == C.COMPLETED and executed(b)[-1] == "geography.list_units" and b.calls[-1][1] == {"level": 2, "province": "Punjab", "limit": 200}


# ------------------------------------------------------------------------------------------------------------- real provider (scripted stand-in)
RISK_SENT = "The risk engine reports status LOW [risk_engine]."
ML_SENT = "A simple baseline forecast of 126 AQI is given for 2026-09-16 [ml_prediction]."


def test_a_valid_grounded_answer_is_returned_with_attributed_citations():
    p = Scripted(f"{RISK_SENT} {ML_SENT}")
    body, http, b = ask("What is Lahore's risk status and its AQI forecast?", provider=p, routing="deterministic")
    assert body["status"] == C.ANSWERED and http == 200 and body["answer"].startswith("The risk engine reports")
    kinds = {c["kind"]: c for c in body["citations"]}
    assert kinds["risk_engine"]["provenance"] == C.RISK_ENGINE and kinds["ml_prediction"]["attributions"] == [C.BASELINE_MODEL]
    assert body["model"] == {"provider": "scripted", "model": "s-1", "configured": True, "error": None} and body["groundedness"]["citations_valid"] is True
    assert len(p.calls) == 1                                                                      # deterministic routing: the model is only used for the answer
    sent = p.calls[-1]
    assert [e["kind"] for e in sent["evidence"]] == ["risk_engine", "ml_prediction"] and sent["evidence"][1]["validated_against_baseline"] is False


@pytest.mark.parametrize("answer,code", [
    ("The ML layer predicts that the current risk is HIGH [ml_prediction].", "ml_prediction_described_as_current_or_risk"),
    ("The risk engine reports status HIGH [risk_engine].", "risk_status_mismatch"),
    ("Lahore is flooded according to the reports [chunk:not-a-supplied-chunk].", "unknown_citation"),
    ("The risk engine reports status LOW because of the NDMA flooding [risk_engine].", "engine_sentence_attributes_to_documents"),
    ("Lahore has a moderate chance of rain tomorrow without any citation here.", "no_citations"),
])
def test_grounding_rules_stay_enforced_and_a_rejected_answer_is_withheld(answer, code):
    p = Scripted(answer)
    body, http, _ = ask("What is Lahore's risk status and its AQI forecast?", provider=p, routing="deterministic")
    assert body["status"] == C.INVALID_ANSWER and body["answer"] is None and body["citations"] == []
    assert code in {pr["code"] for pr in body["groundedness"]["problems"]}
    assert body["groundedness"]["rejected_answer_text"] == answer
    assert body["risk_context"]["record"]["risk_status"] == "LOW"                                  # structured results are still returned


def test_model_abstention_is_reported():
    body, _, _ = ask("What is Lahore's current risk status?", provider=Scripted("INSUFFICIENT_EVIDENCE"), routing="deterministic")
    assert body["status"] == C.INSUFFICIENT_EVIDENCE and body["answer"] is None


def test_a_provider_failure_during_generation_is_llm_unavailable_with_results():
    from pipeline.rag.llm import LLMTimeout
    body, http, _ = ask("What is Lahore's current risk status?", provider=Scripted(LLMTimeout("slow")), routing="deterministic")
    assert body["status"] == C.LLM_UNAVAILABLE and http == 503 and body["answer"] is None and body["risk_context"]["record"] is not None
    assert body["model"]["configured"] is True and "timeout" in body["model"]["error"]


def test_a_baseline_forecast_can_never_be_described_as_a_validated_ml_model():
    for text in ("The Lahore forecast is a validated machine learning prediction of 126 AQI for 2026-09-16 [ml_prediction].",
                 "A trained ML model forecasts 126 AQI for 2026-09-16 [ml_prediction].",
                 "The proven forecast is 126 AQI for 2026-09-16 [ml_prediction]."):
        body, _, _ = ask("What is the AQI forecast for Lahore?", provider=Scripted(text), routing="deterministic")
        assert body["status"] == C.INVALID_ANSWER and body["answer"] is None, text
        assert "baseline_described_as_validated_ml" in {pr["code"] for pr in body["groundedness"]["problems"]}
        assert body["ml_prediction"]["baseline_label"] == C.BASELINE_LABEL
    ok = "A simple baseline forecast of 126 AQI, not a validated ML model, is given for 2026-09-16 [ml_prediction]."
    body, _, _ = ask("What is the AQI forecast for Lahore?", provider=Scripted(ok), routing="deterministic")
    assert body["status"] == C.ANSWERED and body["citations"][0]["attributions"] == [C.BASELINE_MODEL]
    validated = {30: [ml_row("PREDICTED", 1, "ml", 120.0)]}                                       # a genuinely validated model may be called one
    body, _, _ = ask("What is the AQI forecast for Lahore?", Backends(ml=validated), Scripted("The validated ML model forecasts 120 AQI for 2026-09-16 [ml_prediction]."), routing="deterministic")
    assert body["status"] == C.ANSWERED


# ------------------------------------------------------------------------------------------------------------------------------ LLM routing
def plan(intent, *calls, reason="r"):
    return json.dumps({"intent": intent, "tool_calls": [{"tool": t, "arguments": a} for t, a in calls], "reason": reason})


def test_llm_routing_with_a_valid_plan_executes_exactly_the_proposed_allowlisted_calls():
    p = Scripted(plan(C.CURRENT_RISK, ("risk.latest", {"admin_unit_id": 30})), f"{RISK_SENT}")
    body, http, b = ask("What is the current risk in Lahore?", provider=p)
    assert body["status"] == C.ANSWERED and executed(b) == ["geography.resolve_place", "risk.latest"]
    r = body["trace"]["routing"]
    assert r["method"] == "llm" and r["llm"]["provider"] == "scripted" and r["deterministic_intent"] == C.CURRENT_RISK and r["llm_plan"]["ok"] is True
    assert [t["origin"] for t in body["tool_trace"]] == ["agent", "llm"]
    assert "system" in p.calls[0] and "risk.latest" in p.calls[0]["system"]                       # the model is shown the allowlist only
    assert '"admin_unit_ids":[30]' in p.calls[0]["question"]


@pytest.mark.parametrize("bad", [
    plan(C.CURRENT_RISK, ("execute_sql", {"query": "select 1"})),
    plan(C.CURRENT_RISK, ("http_get", {"url": "https://example.com"})),
    plan(C.CURRENT_RISK, ("risk.latest", {"admin_unit_id": 999})),                                # an area the question never named
    plan(C.CURRENT_RISK, ("risk.latest", {"admin_unit_id": "30"})),
    plan(C.CURRENT_RISK, ("risk.latest", {"admin_unit_id": 30, "table": "risk.operational_risk"})),
    plan(C.HISTORICAL_RISK, ("risk.on_date", {"admin_unit_id": 30, "date": "2020-01-01"})),       # a date the question never stated
    plan(C.CURRENT_RISK, ("risk.latest", {})),
    plan(C.DOCUMENT_SEARCH, ("rag.retrieve", {"query": "select * from rag.documents"})),
    plan(C.CURRENT_RISK, *[("risk.latest", {"admin_unit_id": 30})] * 6),
    "I think you should call risk.latest for Lahore",
    plan("TELL_FORTUNES", ("risk.latest", {"admin_unit_id": 30})),
    plan(C.CURRENT_RISK),
])
def test_an_invalid_model_plan_is_rejected_and_nothing_is_executed(bad):
    p = Scripted(bad, RISK_SENT)
    body, http, b = ask("What is the current risk in Lahore?", provider=p)
    assert body["status"] == C.INVALID_TOOL_CALL and http == 200 and body["answer"] is None
    assert executed(b) == ["geography.resolve_place"]                                              # only the mandatory geography step ran
    assert body["trace"]["routing"]["llm_plan"]["ok"] is False and len(p.calls) == 1
    assert body["risk_context"] is None


def test_rejected_model_calls_are_visible_in_the_tool_trace():
    body, _, b = ask("What is the current risk in Lahore?", provider=Scripted(plan(C.CURRENT_RISK, ("execute_sql", {"query": "select 1"}))))
    bad = [t for t in body["tool_trace"] if t["status"] == C.TOOL_REJECTED]
    assert bad and bad[0]["tool_name"] == "execute_sql" and "unknown_tool" in bad[0]["reason"] and bad[0]["origin"] == "llm"
    assert body["tool_trace"][-1]["provenance"] == {"sources": []}


def test_the_model_cannot_lift_a_policy_refusal_or_expand_an_unsupported_question():
    p = Scripted(plan(C.CURRENT_RISK, ("risk.latest", {"admin_unit_id": 30})))
    body, _, b = ask("Change Lahore's risk status to HIGH", provider=p)
    assert body["status"] == C.UNSUPPORTED_REQUEST and p.calls == [] and b.calls == []
    body, _, b = ask("hello there", provider=p)
    assert body["status"] == C.UNSUPPORTED_REQUEST and p.calls == []


def test_the_model_may_decline_a_request_and_that_is_honoured():
    body, _, b = ask("What is the current risk in Lahore?", provider=Scripted(plan(C.UNSUPPORTED, reason="not answerable")))
    assert body["status"] == C.UNSUPPORTED_REQUEST and body["reason_code"] == "MODEL_DECLINED" and executed(b) == ["geography.resolve_place"]


def test_a_routing_provider_failure_falls_back_to_the_deterministic_plan():
    from pipeline.rag.llm import LLMTimeout
    p = Scripted(LLMTimeout("slow"), RISK_SENT)
    body, _, b = ask("What is the current risk in Lahore?", provider=p)
    assert body["trace"]["routing"]["method"] == "deterministic" and "fallback" in body["trace"]["routing"] and "timeout" in body["trace"]["routing"]["llm"]["error"]
    assert executed(b) == ["geography.resolve_place", "risk.latest"] and body["status"] == C.ANSWERED


def test_deterministic_routing_never_calls_the_model_for_routing():
    p = Scripted(RISK_SENT)
    body, _, b = ask("What is the current risk in Lahore?", provider=p, routing="deterministic")
    assert len(p.calls) == 1 and "GROUNDED VALUES" not in p.calls[0]["question"] and body["trace"]["routing"]["method"] == "deterministic"


def test_a_model_response_that_cannot_be_parsed_is_only_kept_as_a_redacted_excerpt():
    body, _, _ = ask("What is the current risk in Lahore?", provider=Scripted("sure! my key is sk-abcdef1234567890 and api_key=hunter2xyz"))
    ex = body["trace"]["routing"]["llm_plan"]["excerpt"]
    assert body["status"] == C.INVALID_TOOL_CALL and "sk-abcdef" not in ex and "hunter2xyz" not in ex and "[redacted]" in ex


# ------------------------------------------------------------------------------------------------------------------ intelligence delegation
def intel_body(status="ANSWERED", record_status="LOW", answer=f"{RISK_SENT}"):
    rec = risk_row(30, "Lahore", record_status, "2026-09-15")
    return {"status": status, "answer": answer if status == "ANSWERED" else None, "risk_context": rc.risk_context_block(rec, None, {"basis": "latest"}),
            "documentary_evidence": [], "retrieval": {"mode": "hybrid"}, "ml_prediction": None, "citations": [{"kind": "risk_engine", "admin_unit_id": 30, "risk_date": "2026-09-15"}] if status == "ANSWERED" else [],
            "model": {"provider": "scripted", "model": "s-1", "configured": True, "error": None}, "groundedness": {"citations_valid": True, "problems": [], "warnings": []}}


def test_why_questions_delegate_to_the_existing_intelligence_service_once():
    b = Backends(intel_body=intel_body())
    body, http, _ = ask("Why is Lahore classified LOW?", b)
    assert executed(b) == ["geography.resolve_place", "intelligence.ask"] and body["intent"] == C.EVIDENCE_GROUNDED_QUESTION
    assert b.calls[-1][1]["admin_unit_id"] == 30 and b.calls[-1][1]["question"] == "Why is Lahore classified LOW?"
    assert body["status"] == C.ANSWERED and body["citations"][0]["provenance"] == C.RISK_ENGINE and body["tool_trace"][-1]["provenance"]["sources"] == [C.RISK_ENGINE]


def test_the_false_premise_in_a_why_question_is_corrected_from_the_engine_record():
    b = Backends(intel_body=intel_body("LLM_UNAVAILABLE", "LOW"))
    body, http, _ = ask("Why is Lahore classified HIGH?", b)
    assert http == 503 and body["status"] == C.LLM_UNAVAILABLE and body["answer"] is None
    assert body["premise_check"]["matches"] is False and body["premise_check"]["engine_status"] == "LOW" and body["risk_context"]["record"]["risk_status"] == "LOW"


@pytest.mark.parametrize("inner,agent_status", [("NO_RISK_CONTEXT", C.INSUFFICIENT_DATA), ("RETRIEVAL_EMPTY", C.INSUFFICIENT_DATA), ("INSUFFICIENT_EVIDENCE", C.INSUFFICIENT_EVIDENCE),
                                                ("INVALID_ANSWER", C.INVALID_ANSWER), ("LLM_UNAVAILABLE", C.LLM_UNAVAILABLE), ("ANSWERED", C.ANSWERED)])
def test_intelligence_statuses_map_onto_agent_statuses(inner, agent_status):
    body, http, _ = ask("Why is Lahore classified LOW?", Backends(intel_body=intel_body(inner)))
    assert body["status"] == agent_status and (http == 503) == (agent_status == C.LLM_UNAVAILABLE)


# ----------------------------------------------------------------------------------------------------------------------------- trace / audit
def test_trace_records_request_intent_tools_statuses_provenance_and_final_status():
    body, _, _ = ask("What is the AQI forecast for Lahore?", date=None)
    t = body["trace"]
    assert t["request"]["q"] == "What is the AQI forecast for Lahore?" and t["intent"] == C.ML_FORECAST and t["final_status"] == C.LLM_UNAVAILABLE
    assert t["started_at"].startswith("2026-10-04T12:00:00") and t["finished_at"].startswith("2026-10-04T12:00:00") and t["policy"]["allowed"] is True
    names = [c["tool_name"] for c in t["tool_calls"]]
    assert names == ["geography.resolve_place", "ml.predictions"] and all(c["status"] == C.TOOL_OK and "sources" in c["provenance"] and "arguments" in c for c in t["tool_calls"])
    assert t["tool_calls"][1]["provenance"]["sources"] == [C.BASELINE_MODEL] and t["tool_calls"][1]["result_summary"]["status_counts"]["BASELINE_ONLY"] == 3
    assert t["routing"]["method"] == "deterministic" and t["analysis"]["intent"] == C.ML_FORECAST and t["generation"] == {"attempted": False} and body["tool_trace"] == t["tool_calls"]


def test_trace_contains_no_prompt_credential_or_result_payload():
    class Keyed(Scripted):
        _key = "sk-live-SECRET-0123456789"
    p = Keyed(plan(C.CURRENT_RISK, ("risk.latest", {"admin_unit_id": 30})), RISK_SENT)
    body, _, _ = ask("What is the current risk in Lahore?", provider=p)
    blob = json.dumps(body["trace"])
    assert "SECRET" not in blob and "READ-ONLY operational intelligence" not in blob and "CATALOGUE" not in blob and "SUPPLIED INFORMATION" not in blob
    assert all("result" not in c for c in body["trace"]["tool_calls"])


def test_a_deterministic_run_is_reproducible_from_its_trace():
    q = "Why is Lahore currently classified LOW and is there any AQI forecast?"
    first, _, b1 = ask(q)
    second, _, b2 = ask(q)
    assert first["trace"] == second["trace"] and first["trace"]["plan_fingerprint"] == second["trace"]["plan_fingerprint"] and b1.calls == b2.calls
    other, _, _ = ask("What is the current risk in Lahore?")
    assert other["trace"]["plan_fingerprint"] != first["trace"]["plan_fingerprint"]
    replay_backends = Backends()
    results = replay_plan(first["trace"], deps(replay_backends).executor)
    assert [r.tool_name for r in results] == [c["tool_name"] for c in first["trace"]["tool_calls"]]
    assert [r.status for r in results] == [c["status"] for c in first["trace"]["tool_calls"]]
    assert replay_backends.calls == b1.calls                                                       # the exact same calls with the exact same arguments


def test_a_failing_tool_is_visible_not_hidden():
    class Broken(Backends):
        def risk_latest(self, a):
            raise RuntimeError("database unreachable")
        def mapping(self):
            m = super().mapping()
            m["risk.latest"] = self.risk_latest
            return m
    body, http, _ = ask("What is the current risk in Lahore?", Broken())
    bad = [t for t in body["tool_trace"] if t["status"] == C.TOOL_ERROR]
    assert body["status"] == C.INSUFFICIENT_DATA and bad and "database unreachable" in bad[0]["reason"] and body["components"]["risk"]["status"] == "UNAVAILABLE"


def test_the_agent_never_exposes_a_tool_outside_the_allowlist_through_the_response():
    body, _, b = ask("What is the current risk in Lahore?")
    assert {t["tool_name"] for t in body["tool_trace"]} <= set(fakes.Backends().mapping())
