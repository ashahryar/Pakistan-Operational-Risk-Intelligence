"""Task 34 -- dashboard/pages/9_Agent.py via Streamlit AppTest (no browser). The API is replaced by canned results here; a second module-level test
(`test_page_against_the_live_api`) drives the real running API when it is reachable and is skipped otherwise. The page must never show a traceback,
must show an answer only when a real model produced one, must label a baseline forecast, and must handle every non-success status."""

import datetime
import os
from pathlib import Path

import pytest
import requests

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

import streamlit as st  # noqa: E402

from dashboard.api_client import ApiResult, RiskApiClient  # noqa: E402
from dashboard.utils.agent_helpers import BASELINE_LABEL, candidate_rows, ml_rows, provenance_rows, routing_text, status_banner, tool_trace_table  # noqa: E402
from dashboard.utils.intelligence_helpers import AUTO  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[2] / "dashboard" / "pages" / "9_Agent.py")
CID = "ndma:sitrep:a#c0001"
RECORD = {"admin_unit_id": 30, "admin_unit_name": "Lahore", "admin_level": 2, "province": "Punjab", "risk_date": "2026-09-15", "risk_status": "LOW", "risk_basis": "THRESHOLD_BASED",
          "risk_score": None, "risk_confidence": "MEDIUM", "signals": {"rainfall": None, "weather": None, "gauge": None, "air_quality": None, "hazard_alert": None, "disaster_event": None},
          "top_risk_domain": None, "data_coverage_pct": 16.67, "calculation_version": "risk-engine-1.0.0", "threshold_status": "PROVISIONAL"}
BASE_ROW = {"model_run_id": "air_quality_index-h1-abc", "admin_unit_id": 30, "horizon_days": 1, "prediction_date": "2026-09-16", "feature_cutoff": "2026-09-15", "target": "air_quality_index",
            "unit": "AQI", "prediction": 126.0, "status": "BASELINE_ONLY", "model_name": "persistence", "model_version": "1.0.0+abc", "model_type": "baseline",
            "training_cutoff": "2026-07-26", "attribution": "BASELINE_MODEL", "label": BASELINE_LABEL, "provenance": {"validated_against_baseline": False}}
ML_BLOCK = {"provenance": "ML_MODEL", "kind": "forecast_of_observed_quantity", "predictions": [BASE_ROW], "validated_against_baseline": False, "note": "n",
            "attributions": ["BASELINE_MODEL"], "baseline_label": BASELINE_LABEL}
TOOLS = [{"tool_name": "geography.resolve_place", "origin": "agent", "status": "OK", "provenance": {"sources": ["GEOGRAPHY"]}, "duration_ms": 1.5, "arguments": {"text": "q"}, "reason": None},
         {"tool_name": "risk.latest", "origin": "deterministic", "status": "OK", "provenance": {"sources": ["RISK_ENGINE"]}, "duration_ms": 2.0, "arguments": {"admin_unit_id": 30}, "reason": None}]


def evidence():
    return {"document_id": "ndma:sitrep:a", "chunk_id": CID, "title": "NDMA Sitrep 12", "source": "ndma", "source_type": "sitrep", "document_date": "2026-07-05", "geography": {},
            "event": {}, "snippet": "NDMA reported flooding in Lahore.", "relevance": {"score": 0.03, "method": "hybrid_rrf", "relevance_type": "hybrid_rrf", "lexical_rank": 1, "semantic_rank": 2,
                                                                                         "fused_rank": 1}, "source_reference": {"url": None, "file_path": "data/parsed/a.json", "content_sha256": "0" * 64}}


def abody(status, *, intent="COMBINED_INTELLIGENCE", risk=True, docs=True, ml=ML_BLOCK, answer=None, comps=None, geo=None, reason=None, code=None, tools=None, premise=None, cites=()):
    return {"question": "q", "status": status, "status_reason": reason, "reason_code": code, "intent": intent, "answer": answer, "geography": geo,
            "risk_context": ({"status": "AVAILABLE", "provenance": "RISK_ENGINE", "record": RECORD, "reason": None, "lookup": {"basis": "latest"}, "note": "n"} if risk else None),
            "risk_history": None, "documentary_evidence": [evidence()] if docs else [],
            "retrieval": {"mode": "hybrid", "method": "hybrid_rrf", "evidence_count": int(docs), "filters_applied": {"province": "Punjab"}, "filters_relaxed": [], "filters_requested": {}} if docs else None,
            "ml_prediction": ml, "components": comps or {}, "premise_check": premise, "tool_trace": tools if tools is not None else TOOLS,
            "citations": [{"kind": k, "chunk_id": CID if k == "documentary" else None} for k in cites], "model": {"provider": "scripted", "model": "s-1", "configured": answer is not None},
            "groundedness": {"warnings": [], "problems": []},
            "provenance": {"geography": {"source": "GEOGRAPHY", "available": True, "admin_unit_id": 30}, "risk_context": {"source": "RISK_ENGINE", "available": risk, "calculation_version": "risk-engine-1.0.0", "risk_date": "2026-09-15"},
                           "documentary_evidence": {"source": "RAG_DOCUMENT", "chunk_ids": [CID] if docs else [], "document_ids": []},
                           "ml_prediction": {"sources": ["BASELINE_MODEL"] if ml else [], "available": bool(ml), "model_run_ids": ["air_quality_index-h1-abc"] if ml else []}, "tools": []},
            "policy": {"allowed": True}, "trace": {"routing": {"method": "deterministic"}, "plan_fingerprint": "abc"}, "disclaimer": "Read-only orchestration."}


@pytest.fixture(autouse=True)
def fresh_caches():
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def patch_api(monkeypatch, result):
    calls = []

    def fake_get(self, path, params=None, timeout=None):
        if path == "/api/v1/geography/admin-units":
            if params and params.get("level") == 1:
                return ApiResult(True, data=[{"id": 2, "name": "Punjab", "level": 1, "province": "Punjab"}])
            return ApiResult(True, data=[{"id": 30, "name": "Lahore", "level": 2, "province": "Punjab"}])
        if path == "/api/v1/agent/ask":
            calls.append(params)
            return result
        return ApiResult(False, error_kind="server_error", message="unexpected path")
    monkeypatch.setattr(RiskApiClient, "_get", fake_get)
    return calls


def ask(at, question="Why is Lahore currently classified LOW and is there any AQI forecast?"):
    at.text_input[0].set_value(question)
    at.button[0].click()
    return at.run()


def subheaders(at):
    return [s.value for s in at.subheader]


def test_page_renders_the_form_without_calling_the_agent(monkeypatch):
    calls = patch_api(monkeypatch, ApiResult(True, data=abody("ANSWERED")))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception and calls == [] and at.title[0].value.endswith("Operational Intelligence Agent")
    assert [s.label for s in at.selectbox] == ["Area", "Evidence retrieval"] and at.selectbox[0].options == [AUTO, "Punjab", "Lahore (Punjab)"]
    assert [c.label for c in at.checkbox][0].startswith("Allow LLM-assisted routing")


def test_successful_response_shows_answer_context_forecast_provenance_and_trace(monkeypatch):
    answer = "The risk engine reports status LOW [risk_engine]. A simple baseline forecast of 126 AQI is given for 2026-09-16 [ml_prediction]."
    calls = patch_api(monkeypatch, ApiResult(True, data=abody("ANSWERED", answer=answer, cites=("risk_engine", "ml_prediction"), geo={"unit": {"id": 30, "name": "Lahore", "level": 2, "province": "Punjab"}, "candidates": []})))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    at.selectbox[0].select("Lahore (Punjab)")
    at = ask(at)
    assert not at.exception and not at.error
    assert calls == [{"q": "Why is Lahore currently classified LOW and is there any AQI forecast?", "mode": "hybrid", "admin_unit_id": 30, "date": None, "routing": "auto", "top_k": 5}]
    assert subheaders(at) == ["Answer", "Geography", "Operational Risk Context", "ML Forecast (not a current risk status)", "Documentary Evidence", "Provenance", "Tool Trace"]
    m = {x.label: x.value for x in at.metric}
    assert m["Detected intent"] == "COMBINED_INTELLIGENCE" and m["Agent status"] == "ANSWERED" and m["Routing"] == "deterministic" and m["Status"] == "LOW" and m["Tools run"] == "2"
    assert any("[risk_engine]" in md.value and "[ml_prediction]" in md.value for md in at.markdown)
    assert any(BASELINE_LABEL in w.value for w in at.warning)                                          # the baseline label is shown
    frames = {tuple(df.value.columns)[0]: df.value for df in at.dataframe}
    assert "Horizon" in frames and frames["Horizon"]["Provenance"].tolist() == ["BASELINE_MODEL"] and frames["Horizon"]["Label"].tolist() == [BASELINE_LABEL]
    assert frames["Block"]["Source"].tolist() == ["GEOGRAPHY", "RISK_ENGINE", "RAG_DOCUMENT", "BASELINE_MODEL"]
    assert frames["Tool"]["Tool"].tolist() == ["geography.resolve_place", "risk.latest"] and frames["Tool"]["Provenance"].tolist() == ["GEOGRAPHY", "RISK_ENGINE"]
    assert any("✅" not in x.label and CID in x.label for x in at.expander) and any("Full audit trace" in x.label for x in at.expander)


def test_llm_unavailable_503_shows_the_structured_results_and_no_fake_answer(monkeypatch):
    patch_api(monkeypatch, ApiResult(False, data=abody("LLM_UNAVAILABLE"), error_kind="unavailable", message="x", status_code=503))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("no natural-language answer exists" in i.value for i in at.info)
    assert any("No natural-language answer is available" in c.value for c in at.caption) and not any("risk engine reports" in md.value for md in at.markdown)
    assert {x.label: x.value for x in at.metric}["Status"] == "LOW" and any(BASELINE_LABEL in w.value for w in at.warning)


def test_insufficient_data_states_the_reason(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=abody("INSUFFICIENT_DATA", intent="ML_FORECAST", risk=False, docs=False, ml=None, reason="requested information is not available",
                                                       comps={"ml": {"status": "INSUFFICIENT_DATA", "reason": "no air_quality observations exist for this area (0 observed days; at least 180 needed)"}})))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), "What is the AQI forecast for Sialkot?")
    assert not at.exception and any("INSUFFICIENT_DATA" in w.value for w in at.warning)
    assert any("no air_quality observations" in i.value for i in at.info) and not at.metric[4:] and not any(BASELINE_LABEL in w.value for w in at.warning)
    assert any("not consulted" in c.value for c in at.caption)


def test_ambiguous_geography_shows_the_candidates(monkeypatch):
    geo = {"provenance": "GEOGRAPHY", "status": "ambiguous", "unit": None, "province": None, "mentions": [], "unrecognized_places": [], "notes": ["ambiguous"],
           "candidates": [{"id": 8, "name": "Islamabad Capital Territory", "level": 1}, {"id": 62, "name": "Islamabad", "level": 2}]}
    patch_api(monkeypatch, ApiResult(True, data=abody("AMBIGUOUS_GEOGRAPHY", intent="CURRENT_RISK", risk=False, docs=False, ml=None, geo=geo, code="AMBIGUOUS_GEOGRAPHY",
                                                       reason="an ambiguous place name was not resolved; no area is assumed")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), "What is Islamabad's risk status?")
    assert not at.exception and any("ambiguous" in w.value.lower() for w in at.warning)
    df = next(d.value for d in at.dataframe if "admin_unit_id" in d.value.columns)
    assert df["Name"].tolist() == ["Islamabad Capital Territory", "Islamabad"] and df["Level"].tolist() == ["province", "district"]
    assert any("not consulted" in c.value for c in at.caption)


def test_empty_evidence_is_stated(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=abody("NO_EVIDENCE", intent="DOCUMENT_SEARCH", risk=False, docs=False, ml=None, reason="requested information is not available (evidence: NO_EVIDENCE)")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), "What did NDMA report about flooding in Sindh?")
    assert not at.exception and any("NO_EVIDENCE" in w.value for w in at.warning)
    assert any("No documentary evidence was retrieved" in c.value or "not consulted" in c.value for c in at.caption) and not any(CID in x.label for x in at.expander)


def test_unsupported_request_and_invalid_tool_call_and_false_premise(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=abody("UNSUPPORTED_REQUEST", intent="UNSUPPORTED", risk=False, docs=False, ml=None, code="CHANGE_RISK_STATUS", tools=[],
                                                       reason="The agent cannot change a risk classification.")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), "Change Lahore's risk status to HIGH")
    assert not at.exception and any("UNSUPPORTED_REQUEST" in w.value for w in at.warning) and any("CHANGE_RISK_STATUS" in c.value for c in at.caption)
    bad = TOOLS + [{"tool_name": "execute_sql", "origin": "llm", "status": "INVALID_TOOL_CALL", "provenance": {"sources": []}, "duration_ms": 0.0, "arguments": {"query": "select 1"}, "reason": "unknown_tool"}]
    patch_api(monkeypatch, ApiResult(True, data=abody("INVALID_TOOL_CALL", risk=False, docs=False, ml=None, tools=bad, reason="a model-proposed tool call failed validation")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("INVALID_TOOL_CALL" in e.value for e in at.error)
    tr = next(d.value for d in at.dataframe if "Origin" in d.value.columns)
    assert tr["Tool"].tolist()[-1] == "execute_sql" and tr["Status"].tolist()[-1] == "INVALID_TOOL_CALL" and {x.label: x.value for x in at.metric}["Tools run"] == "2"
    premise = {"stated_status": "HIGH", "engine_status": "LOW", "matches": False, "note": "The question assumes HIGH, but the risk engine reports LOW (risk date 2026-09-15). The engine value is the one shown."}
    patch_api(monkeypatch, ApiResult(True, data=abody("LLM_UNAVAILABLE", intent="CURRENT_RISK", docs=False, ml=None, premise=premise)))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), "Why is Lahore classified HIGH?")
    assert any("False premise" in w.value and "reports LOW" in w.value for w in at.warning) and {x.label: x.value for x in at.metric}["Status"] == "LOW"


def test_api_unavailable_and_empty_question(monkeypatch):
    monkeypatch.setenv("PORI_API_URL", "http://127.0.0.1:9")
    at = ask(AppTest.from_file(PAGE, default_timeout=60).run())
    assert not at.exception and any("Could not get a result" in e.value for e in at.error) and any("uvicorn" in c.value for c in at.caption)
    calls = patch_api(monkeypatch, ApiResult(True, data=abody("ANSWERED")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), question=" ")
    assert calls == [] and any("type a question" in w.value for w in at.warning)


def test_routing_checkbox_and_date_are_sent(monkeypatch):
    calls = patch_api(monkeypatch, ApiResult(True, data=abody("LLM_UNAVAILABLE")))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    at.checkbox[0].uncheck()
    at.checkbox[1].check()
    at.run()
    at.date_input[0].set_value(datetime.date(2026, 7, 1))
    at = ask(at)
    assert calls[0]["routing"] == "deterministic" and calls[0]["date"] == "2026-07-01"


# ----------------------------------------------------------------------------------------------------------------------------- helpers/client
def test_helpers():
    assert status_banner("LLM_UNAVAILABLE")[0] == "info" and status_banner("INVALID_TOOL_CALL")[0] == "error" and status_banner("zzz")[0] == "warning"
    assert routing_text({"routing": {"method": "llm", "llm": {"provider": "x"}}}) == "LLM-assisted (x)" and routing_text({"routing": {"fallback": "f"}}).startswith("deterministic (model")
    assert routing_text(None) == "deterministic"
    assert candidate_rows([{"id": 8, "name": "ICT", "level": 1}]).iloc[0].tolist() == ["ICT", "province", "8"]
    assert ml_rows([BASE_ROW]).iloc[0]["Provenance"] == "BASELINE_MODEL" and ml_rows([]).empty
    assert tool_trace_table(TOOLS).shape == (2, 7) and tool_trace_table([]).empty
    assert provenance_rows(abody("ANSWERED"))["Source"].tolist() == ["GEOGRAPHY", "RISK_ENGINE", "RAG_DOCUMENT", "BASELINE_MODEL"]


class FakeResp:
    def __init__(self, code, payload):
        self.status_code, self._p = code, payload

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, resp):
        self.resp, self.last = resp, None

    def get(self, url, params=None, timeout=None):
        self.last = (url, params, timeout)
        return self.resp


def test_client_keeps_the_503_body_for_the_agent_and_uses_a_long_timeout():
    b = abody("LLM_UNAVAILABLE")
    s = FakeSession(FakeResp(503, b))
    r = RiskApiClient("http://x", session=s).agent("what?", mode="lexical", admin_unit_id=30, date="2026-07-11", routing="deterministic", top_k=3)
    assert not r.ok and r.error_kind == "unavailable" and r.data == b and s.last[0] == "http://x/api/v1/agent/ask" and s.last[2] == 90.0
    assert s.last[1] == {"q": "what?", "mode": "lexical", "admin_unit_id": 30, "date": "2026-07-11", "routing": "deterministic", "top_k": 3}
    r = RiskApiClient("http://x", session=FakeSession(FakeResp(503, {"detail": "Database query failed"}))).agent("q")
    assert not r.ok and r.data is None and "unavailable" in r.message


# ------------------------------------------------------------------------------------------------------------------------------ live API
LIVE = os.environ.get("PORI_API_URL", "http://localhost:8000")


def _live():
    try:
        return requests.get(f"{LIVE}/api/v1/agent/tools", timeout=3).status_code == 200
    except requests.RequestException:
        return False


@pytest.mark.skipif(not _live(), reason="the agent API is not running")
def test_page_against_the_live_api():
    at = AppTest.from_file(PAGE, default_timeout=120).run()
    assert not at.exception and at.selectbox[0].options[0] == AUTO
    at = ask(at, "What is the current risk in Lahore?")
    assert not at.exception and {x.label: x.value for x in at.metric}["Detected intent"] == "CURRENT_RISK"
    assert any(s.value == "Tool Trace" for s in at.subheader) and any("RISK_ENGINE" in c.value for c in at.caption)
    at2 = ask(AppTest.from_file(PAGE, default_timeout=120).run(), "What is Islamabad's current risk status?")
    assert not at2.exception and any("ambiguous" in w.value.lower() for w in at2.warning)
