"""Task 32 -- dashboard/pages/8_Intelligence.py via Streamlit AppTest (no browser, no network). The API is replaced by canned results; the page
must never show a traceback, must show computed risk context and documentary evidence separately, and must show an AI explanation only when a
real model produced one."""

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

import streamlit as st  # noqa: E402

from dashboard.api_client import ApiResult, RiskApiClient  # noqa: E402
from dashboard.utils.intelligence_helpers import AUTO, area_options, risk_metrics, status_banner  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[2] / "dashboard" / "pages" / "8_Intelligence.py")
CID = "ndma:sitrep:a#c0001"
RECORD = {"admin_unit_id": 46, "admin_unit_name": "Sialkot", "admin_level": 2, "province": "Punjab", "risk_date": "2026-07-11", "risk_status": "MODERATE",
          "risk_basis": "THRESHOLD_BASED", "risk_score": None, "risk_confidence": "MEDIUM",
          "signals": {"rainfall": 0.79, "weather": None, "gauge": None, "air_quality": None, "hazard_alert": None, "disaster_event": None},
          "top_risk_domain": "rainfall", "data_coverage_pct": 16.67, "calculation_version": "risk-engine-1.0.0", "threshold_status": "PROVISIONAL"}


def evidence():
    return {"document_id": "ndma:sitrep:a", "chunk_id": CID, "title": "NDMA Sitrep 12", "source": "ndma", "source_type": "sitrep", "document_date": "2026-07-05",
            "geography": {}, "event": {}, "snippet": "NDMA reported 45 deaths in Sialkot.",
            "relevance": {"score": 0.03, "method": "hybrid_rrf", "relevance_type": "hybrid_rrf", "lexical_rank": 1, "semantic_rank": 2, "fused_rank": 1},
            "source_reference": {"url": None, "file_path": "data/parsed/a.json", "content_sha256": "0" * 64}}


def body(status, *, risk=True, docs=True, answer=None, cites=(), warnings=(), problems=()):
    return {"question": "q", "status": status, "answer": answer,
            "question_context": {"geography_status": "resolved", "admin_unit": {"id": 46, "name": "Sialkot"}, "target_basis": "question_text"},
            "risk_context": {"status": "AVAILABLE" if risk else "NO_RISK_CONTEXT", "provenance": "RISK_ENGINE", "record": RECORD if risk else None,
                             "reason": None if risk else "no risk record exists for Sialkot", "lookup": {"basis": "latest"}, "note": "n"},
            "documentary_evidence": [evidence()] if docs else [],
            "retrieval": {"mode": "hybrid", "method": "hybrid_rrf", "evidence_count": int(docs), "top_k": 5, "filters_applied": {"admin_unit_id": 46},
                          "filters_relaxed": ["event_type"], "filters_requested": {}, "note": ""},
            "citations": [{"kind": k, "chunk_id": CID if k == "documentary" else None} for k in cites],
            "model": {"provider": "scripted", "model": "s-1", "configured": True},
            "groundedness": {"warnings": list(warnings), "problems": list(problems)}, "provenance": {}, "disclaimer": "Decision support only."}


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
            return ApiResult(True, data=[{"id": 46, "name": "Sialkot", "level": 2, "province": "Punjab"}])
        if path == "/api/v1/intelligence/ask":
            calls.append(params)
            return result
        return ApiResult(False, error_kind="server_error", message="unexpected path")
    monkeypatch.setattr(RiskApiClient, "_get", fake_get)
    return calls


def ask(at, question="Why is Sialkot classified as MODERATE?"):
    at.text_input[0].set_value(question)
    at.button[0].click()
    return at.run()


def subheaders(at):
    return [s.value for s in at.subheader]


def test_page_renders_the_form_and_area_selector_without_calling_ask(monkeypatch):
    calls = patch_api(monkeypatch, ApiResult(True, data=body("ANSWERED")))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception and calls == [] and at.title[0].value.endswith("Operational Intelligence")
    assert [s.label for s in at.selectbox] == ["Area", "Evidence retrieval"]
    assert at.selectbox[0].options == [AUTO, "Punjab", "Sialkot (Punjab)"]


def test_successful_response_shows_risk_context_evidence_and_the_explanation_separately(monkeypatch):
    calls = patch_api(monkeypatch, ApiResult(True, data=body("ANSWERED", answer=f"Sialkot is MODERATE [risk_engine]. NDMA reported 45 deaths [chunk:{CID}].",
                                                              cites=("documentary", "risk_engine"))))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    at.selectbox[0].select("Sialkot (Punjab)")
    at = ask(at)
    assert not at.exception and not at.error
    assert calls == [{"q": "Why is Sialkot classified as MODERATE?", "mode": "hybrid", "admin_unit_id": 46, "province": None, "date": None, "top_k": 5}]
    assert subheaders(at) == ["Operational Risk Context", "Documentary Evidence", "AI Explanation"]
    m = {x.label: x.value for x in at.metric}
    assert m == {"Status": "MODERATE", "Confidence": "MEDIUM", "Coverage": "16.67%", "Top domain": "rainfall", "Risk score": "Unavailable"}
    df = at.dataframe[0].value
    assert dict(zip(df["signal"], df["value"]))["rainfall"] == "0.79" and dict(zip(df["signal"], df["value"]))["gauge"] == "not observed"
    assert any("RISK_ENGINE" in c.value for c in at.caption)
    assert any("✅" in x.label and CID in x.label and "NDMA Sitrep 12" in x.label for x in at.expander)               # chunk id + title shown, cited marked
    assert any("keyword rank 1" in c.value and "NDMA" in c.value and "2026-07-05" in c.value for c in at.caption)
    assert any("[risk_engine]" in md.value and f"[chunk:{CID}]" in md.value for md in at.markdown)


def test_no_risk_context_is_stated_and_no_explanation_is_shown(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("NO_RISK_CONTEXT", risk=False)))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("NO_RISK_CONTEXT" in w.value for w in at.warning) and any("no risk record exists" in i.value for i in at.info)
    assert "AI Explanation" not in subheaders(at) and not at.metric and at.expander                                    # documents still shown


def test_llm_unavailable_503_shows_context_and_evidence_but_no_fake_answer(monkeypatch):
    patch_api(monkeypatch, ApiResult(False, data=body("LLM_UNAVAILABLE"), error_kind="unavailable", message="x", status_code=503))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("AI generation is unavailable" in i.value for i in at.info)
    assert "AI Explanation" not in subheaders(at) and {x.label: x.value for x in at.metric}["Status"] == "MODERATE" and at.expander


def test_invalid_answer_is_withheld(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("INVALID_ANSWER", problems=[{"code": "unknown_citation"}])))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("withheld" in e.value for e in at.error) and "AI Explanation" not in subheaders(at)


def test_insufficient_evidence_is_a_warning_not_an_explanation(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("INSUFFICIENT_EVIDENCE", answer="INSUFFICIENT_EVIDENCE")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert any("INSUFFICIENT_EVIDENCE" in w.value for w in at.warning) and "AI Explanation" not in subheaders(at)


def test_retrieval_empty_and_no_documents(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("RETRIEVAL_EMPTY", risk=False, docs=False)))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("No documentary evidence was retrieved" in c.value for c in at.caption) and not at.expander


def test_api_unavailable_is_a_friendly_message(monkeypatch):
    monkeypatch.setenv("PORI_API_URL", "http://127.0.0.1:9")
    at = ask(AppTest.from_file(PAGE, default_timeout=60).run())
    assert not at.exception and any("Could not get an answer" in e.value for e in at.error) and any("uvicorn" in c.value for c in at.caption)


def test_api_validation_error_is_friendly_and_empty_question_is_not_sent(monkeypatch):
    patch_api(monkeypatch, ApiResult(False, error_kind="invalid_request", message="The API rejected the filter values (HTTP 422).", status_code=422))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("rejected the filter values" in e.value for e in at.error)
    calls = patch_api(monkeypatch, ApiResult(True, data=body("ANSWERED")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), question=" ")
    assert calls == [] and any("type a question" in w.value for w in at.warning)


def test_specific_risk_date_is_sent(monkeypatch):
    calls = patch_api(monkeypatch, ApiResult(True, data=body("ANSWERED", answer=f"x y z w [chunk:{CID}].")))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    at.checkbox[0].check()
    at.run()
    at.date_input[0].set_value(__import__("datetime").date(2026, 7, 11))
    at = ask(at)
    assert calls and calls[0]["date"] == "2026-07-11"


# ------------------------------------------------------------------ helpers and client
def test_helpers():
    assert status_banner("LLM_UNAVAILABLE")[0] == "info" and status_banner("zzz")[0] == "warning"
    assert risk_metrics({"risk_status": "LOW", "risk_score": None, "data_coverage_pct": None})["Coverage"] == "-"
    assert list(area_options([{"id": 1, "name": "B", "level": 2, "province": "P"}, {"id": 2, "name": "P", "level": 1}])) == [AUTO, "P", "B (P)"]


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


def test_client_keeps_the_503_body_for_intelligence_and_uses_a_long_timeout():
    b = body("LLM_UNAVAILABLE")
    s = FakeSession(FakeResp(503, b))
    r = RiskApiClient("http://x", session=s).intelligence("what?", mode="lexical", admin_unit_id=46, date="2026-07-11", top_k=3)
    assert not r.ok and r.error_kind == "unavailable" and r.data == b and s.last[0] == "http://x/api/v1/intelligence/ask" and s.last[2] == 90.0
    assert s.last[1] == {"q": "what?", "mode": "lexical", "admin_unit_id": 46, "date": "2026-07-11", "top_k": 3}
    r = RiskApiClient("http://x", session=FakeSession(FakeResp(503, {"detail": "Hybrid retrieval is unavailable: no runtime"}))).intelligence("q")
    assert not r.ok and r.data is None and "no runtime" in r.message
