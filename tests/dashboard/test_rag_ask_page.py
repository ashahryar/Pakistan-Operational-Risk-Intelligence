"""Task 31 -- dashboard/pages/7_RAG_Ask.py via Streamlit AppTest (no browser, no network). The API is replaced by canned results; the
page must never show a Python traceback, and must show the evidence separately from the answer."""

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

import streamlit as st  # noqa: E402

from dashboard.api_client import ApiResult, RiskApiClient  # noqa: E402
from dashboard.utils.rag_helpers import citation_rows, evidence_caption, status_banner  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[2] / "dashboard" / "pages" / "7_RAG_Ask.py")
CID = "ndma:sitrep:a#c0001"


def evidence(cid=CID, title="NDMA Sitrep 12"):
    return {"document_id": cid.split("#")[0], "chunk_id": cid, "title": title, "source": "ndma", "source_type": "sitrep", "document_date": "2026-07-05",
            "geography": {}, "event": {}, "snippet": "NDMA reported 45 deaths in Swat.", "snippet_document_char_start": 0, "snippet_document_char_end": 10,
            "relevance": {"score": 0.03, "method": "hybrid_rrf", "relevance_type": "hybrid_rrf", "lexical_rank": 1, "semantic_rank": 2, "fused_rank": 1},
            "source_reference": {"url": None, "file_path": "data/parsed/a.json", "content_sha256": "0" * 64}}


def body(status, answer=None, cited=True, warnings=(), problems=()):
    e = evidence()
    return {"query": "q", "answer": answer, "answer_status": status,
            "citations": [{"chunk_id": CID, "document_id": e["document_id"], "title": e["title"], "source": "ndma", "document_date": "2026-07-05",
                           "source_reference": e["source_reference"]}] if cited else [],
            "evidence": [e] if status != "RETRIEVAL_EMPTY" else [], "retrieval": {"mode": "hybrid", "method": "hybrid_rrf", "evidence_count": 1, "top_k": 5,
                                                                                  "filters": {}, "note": ""},
            "model": {"provider": "scripted", "model": "s-1", "configured": True}, "groundedness": {"warnings": list(warnings), "problems": list(problems)},
            "disclaimer": "Generated from retrieved source reports only; not an official warning."}


@pytest.fixture(autouse=True)
def fresh_caches():
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def patch_api(monkeypatch, ask_result):
    calls = []

    def fake_get(self, path, params=None, timeout=None):
        if path == "/api/v1/geography/admin-units":
            return ApiResult(True, data=[{"id": 2, "name": "Punjab", "level": 1}])
        if path == "/api/v1/rag/ask":
            calls.append(params)
            return ask_result
        return ApiResult(False, error_kind="server_error", message="unexpected path")
    monkeypatch.setattr(RiskApiClient, "_get", fake_get)
    return calls


def ask(at, question="How many people died in Swat?"):
    at.text_input[0].set_value(question)
    at.button[0].click()
    return at.run()


def test_page_renders_the_form_without_calling_the_api():
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception and at.title[0].value.endswith("Ask the Reports")
    assert [s.label for s in at.selectbox] == ["Retrieval", "Province", "Source"]


def test_successful_answer_shows_answer_citations_and_evidence_separately(monkeypatch):
    calls = patch_api(monkeypatch, ApiResult(True, data=body("ANSWERED", f"NDMA reported 45 deaths in Swat [chunk:{CID}].")))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    at.selectbox[1].select("Punjab")
    at.selectbox[2].select("ndma")
    at = ask(at)
    assert not at.exception and not at.error
    assert calls == [{"q": "How many people died in Swat?", "mode": "hybrid", "source": "ndma", "province": "Punjab", "top_k": 5}]
    assert any("ANSWERED" in s.value for s in at.success)
    assert any(f"[chunk:{CID}]" in m.value for m in at.markdown)
    assert [s.value for s in at.subheader] == ["Answer", "Citations", "Retrieved evidence"]
    df = at.dataframe[0].value
    assert list(df["Chunk"]) == [CID] and list(df["Source"]) == ["NDMA"] and list(df["Title"]) == ["NDMA Sitrep 12"] and list(df["Date"]) == ["2026-07-05"]
    assert any("✅" in x.label and CID in x.label for x in at.expander)                         # the cited evidence is marked
    assert any("keyword rank 1" in c.value and "meaning rank 2" in c.value for c in at.caption)


def test_insufficient_evidence_is_shown_as_a_warning_with_no_answer_section(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE", cited=False)))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("INSUFFICIENT_EVIDENCE" in w.value for w in at.warning)
    assert "No cited passages" in " ".join(c.value for c in at.caption) and at.expander                  # evidence still listed


def test_retrieval_empty_message(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("RETRIEVAL_EMPTY", cited=False)))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("RETRIEVAL_EMPTY" in w.value for w in at.warning) and any("Nothing was retrieved" in c.value for c in at.caption)


def test_llm_unavailable_503_still_shows_the_evidence(monkeypatch):
    patch_api(monkeypatch, ApiResult(False, data=body("LLM_UNAVAILABLE", cited=False), error_kind="unavailable", message="x", status_code=503))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("LLM_UNAVAILABLE" in i.value for i in at.info) and at.expander


def test_invalid_answer_is_withheld_and_explained(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("INVALID_ANSWER", None, cited=False, problems=[{"code": "unknown_citation"}])))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("withheld" in e.value for e in at.error) and "Answer" not in [s.value for s in at.subheader]


def test_number_warning_is_surfaced(monkeypatch):
    patch_api(monkeypatch, ApiResult(True, data=body("ANSWERED", f"NDMA reported 450 deaths [chunk:{CID}].", warnings=[{"number": "450", "sentence": "NDMA reported 450 deaths"}])))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert any("450" in w.value and "does not appear" in w.value for w in at.warning)


def test_api_unreachable_shows_a_friendly_message_not_a_traceback(monkeypatch):
    monkeypatch.setenv("PORI_API_URL", "http://127.0.0.1:9")
    at = ask(AppTest.from_file(PAGE, default_timeout=60).run())
    assert not at.exception and any("Could not get an answer" in e.value for e in at.error) and any("uvicorn" in c.value for c in at.caption)


def test_validation_error_from_the_api_is_friendly(monkeypatch):
    patch_api(monkeypatch, ApiResult(False, error_kind="invalid_request", message="The API rejected the filter values (HTTP 422).", status_code=422))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run())
    assert not at.exception and any("rejected the filter values" in e.value for e in at.error)


def test_empty_question_is_not_sent(monkeypatch):
    calls = patch_api(monkeypatch, ApiResult(True, data=body("ANSWERED", "x")))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), question=" ")
    assert not at.exception and calls == [] and any("type a question" in w.value for w in at.warning)


# ------------------------------------------------------------------ helpers and client
def test_helpers():
    assert status_banner("ANSWERED")[0] == "success" and status_banner("nope")[0] == "warning"
    assert citation_rows([{"chunk_id": "c", "source": "pdma", "title": None, "document_date": None}]) == [
        {"Chunk": "c", "Source": "PDMA", "Title": "(untitled)", "Date": "undated"}]
    assert "keyword rank 1" in evidence_caption(evidence())


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


def test_client_ask_keeps_the_503_body_and_uses_a_long_timeout():
    b = body("LLM_UNAVAILABLE", cited=False)
    s = FakeSession(FakeResp(503, b))
    r = RiskApiClient("http://x", session=s).ask("what?", mode="semantic", top_k=3)
    assert not r.ok and r.error_kind == "unavailable" and r.data == b and s.last[0] == "http://x/api/v1/rag/ask" and s.last[2] == 90.0
    assert s.last[1] == {"q": "what?", "mode": "semantic", "top_k": 3}                                   # None filters are dropped


def test_client_other_503_without_answer_status_is_unchanged():
    r = RiskApiClient("http://x", session=FakeSession(FakeResp(503, {"detail": "db down"}))).admin_units()
    assert not r.ok and r.data is None and "database is unavailable" in r.message
    r = RiskApiClient("http://x", session=FakeSession(FakeResp(503, {"detail": "Hybrid retrieval is unavailable: no runtime"}))).ask("q")
    assert not r.ok and r.data is None and "no runtime" in r.message


# ------------------------------------------------------------------ Task 35: NO_EVIDENCE is stated plainly and withheld chunks are never shown as evidence
REL_NONE = {"relevance_status": "NO_EVIDENCE", "abstained": True, "abstention_reason": "5 retrieved chunk(s) shared words with the question but none passed the relevance check",
            "relevant_count": 0, "low_relevance_count": 5, "withheld_chunks": [{"chunk_id": CID, "coverage": 0.2, "cosine": 0.7}], "policy": {"mode": "hybrid"}}


def test_no_evidence_notice_is_shown_and_no_withheld_chunk_is_displayed(monkeypatch):
    b = body("RETRIEVAL_EMPTY", cited=False)
    b["retrieval"] = {**b["retrieval"], "evidence_count": 0, "relevance": REL_NONE}
    b["model"] = {"provider": None, "model": None, "configured": False, "called": False}
    patch_api(monkeypatch, ApiResult(True, data=b))
    at = ask(AppTest.from_file(PAGE, default_timeout=30).run(), "What did NDMA report about volcanic eruptions in Sindh?")
    assert not at.exception and any("NO_EVIDENCE" in i.value and "5 loosely matching passage(s) were withheld" in i.value and "NOT shown as evidence" in i.value for i in at.info)
    assert not at.expander and any("Nothing was retrieved" in c.value for c in at.caption)


def test_relevance_notice_helper():
    from dashboard.utils.rag_helpers import relevance_notice
    assert relevance_notice(None) is None and relevance_notice({}) is None and relevance_notice({"relevance": {"abstained": False}}) is None
    level, msg = relevance_notice({"relevance": REL_NONE})
    assert level == "info" and msg.startswith("NO_EVIDENCE") and "5 loosely matching" in msg
    assert "loosely" not in relevance_notice({"relevance": {**REL_NONE, "low_relevance_count": 0, "abstention_reason": "no chunk matched the question and filters"}})[1]
