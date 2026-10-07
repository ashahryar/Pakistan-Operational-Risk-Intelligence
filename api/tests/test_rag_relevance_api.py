"""Task 35 -- the relevance / abstention gate through the HTTP API (/rag/search, /rag/ask, /intelligence/ask, /agent/ask) with the REAL policy
(`strict_relevance`) over a tiny fake corpus: a supported question finds its evidence; a question that only shares words with the corpus is NO_EVIDENCE -- decided by
the relevance signals -- without calling the language model, without losing provenance and without touching filters. Scripted provider, no network, no credential."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.app.routers.agent as agent_router  # noqa: E402
import api.app.services.agent as agent_service  # noqa: E402
import api.app.services.geography as geo_service  # noqa: E402
import api.app.services.intelligence as intel  # noqa: E402
import api.app.services.ml as ml_service  # noqa: E402
import api.app.services.rag as rag_service  # noqa: E402
from api.app.main import app  # noqa: E402
from api.tests.test_agent_api import AgentDb  # noqa: E402
from api.tests.test_intelligence_api import Provider  # noqa: E402
from tests.rag.test_embeddings_unit import ConceptStandIn  # noqa: E402

pytestmark = pytest.mark.strict_relevance
client = TestClient(app)

SUPPORTED = "river overflow inundation"
OVERLAP_ONLY = "river bitcoin cryptocurrency"                  # shares the word 'river' with the corpus, but its other concepts occur nowhere in it
D4_LIKE = "What did NDMA report about volcanic eruptions in Punjab?"


@pytest.fixture
def env(monkeypatch):
    emb = ConceptStandIn()
    db = AgentDb(emb)
    for mod in (rag_service, intel, ml_service, agent_service, geo_service):
        monkeypatch.setattr(mod, "fetch_all", db)
    monkeypatch.setattr(agent_router, "admin_unit_exists", lambda i: True)
    rag_service._cache.update(token=None, retriever=None)
    rag_service._sem_cache.update(token=None, retriever=None)
    rag_service._hyb_cache.update(key=None, retriever=None)
    rag_service.set_embedder(emb)
    rag_service.set_llm_provider(None)
    for k in ("PORI_LLM_PROVIDER", "PORI_LLM_MODEL", "PORI_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield db
    rag_service.set_embedder(None)
    rag_service.set_llm_provider(None)
    for c in (rag_service._cache, rag_service._sem_cache):
        c.update(token=None, retriever=None)
    rag_service._hyb_cache.update(key=None, retriever=None)


def cite_first(evidence):
    return f"River overflow was reported in the area [chunk:{evidence[0]['chunk_id']}]."


# ------------------------------------------------------------------------------------------------------------------------------ /rag/search
@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_search_supported_query_is_relevant_and_every_result_is_labelled(env, mode):
    r = client.get("/api/v1/rag/search", params={"q": SUPPORTED, "mode": mode, "min_score": 0.5} if mode != "lexical" else {"q": SUPPORTED})
    b = r.json()
    assert r.status_code == 200 and b["relevance_status"] == "RELEVANT" and b["abstained"] is False and b["abstention_reason"] is None and b["count"] >= 1
    assert all(e["relevance"]["assessment"]["label"] == "RELEVANT" for e in b["results"][:1]) and b["relevance_policy"]["mode"] == mode
    assert set(b["results"][0]["relevance"]["assessment"]) == {"label", "coverage", "absent_share", "cosine"}


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_search_keeps_low_relevance_results_for_compatibility_but_labels_them_and_can_drop_them(env, mode):
    params = {"q": OVERLAP_ONLY, "mode": mode, **({"min_score": 0.0} if mode != "lexical" else {})}
    b = client.get("/api/v1/rag/search", params=params).json()
    assert b["count"] >= 1 and b["relevance_status"] == "NO_EVIDENCE" and b["abstained"] is True and "none passed the relevance check" in b["abstention_reason"]
    assert all(e["relevance"]["assessment"]["label"] == "LOW_RELEVANCE" for e in b["results"])          # existing clients still get the rows; none is called evidence
    strict = client.get("/api/v1/rag/search", params={**params, "only_relevant": "true"}).json()
    assert strict["count"] == 0 and strict["results"] == [] and strict["relevance_status"] == "NO_EVIDENCE"


def test_search_with_no_matching_word_is_no_evidence_with_its_own_reason(env):
    b = client.get("/api/v1/rag/search", params={"q": "bitcoin price"}).json()
    assert b["count"] == 0 and b["relevance_status"] == "NO_EVIDENCE" and b["abstention_reason"] == "no chunk matched the question and filters"


def test_the_gate_never_widens_filters(env):
    wide = client.get("/api/v1/rag/search", params={"q": SUPPORTED}).json()
    narrow = client.get("/api/v1/rag/search", params={"q": SUPPORTED, "province": "Sindh"}).json()
    assert wide["relevance_status"] == "RELEVANT" and narrow["count"] == 0 and narrow["filters"] == {"province": "Sindh"}     # a relevant answer elsewhere does not leak in
    assert narrow["relevance_status"] == "NO_EVIDENCE" and narrow["abstention_reason"] == "no chunk matched the question and filters"


# --------------------------------------------------------------------------------------------------------------------------------- /rag/ask
def test_ask_without_relevant_evidence_does_not_call_the_model(env):
    p = Provider(cite_first)
    rag_service.set_llm_provider(p)
    r = client.get("/api/v1/rag/ask", params={"q": OVERLAP_ONLY, "mode": "lexical"})
    b = r.json()
    assert r.status_code == 200 and b["answer_status"] == "RETRIEVAL_EMPTY" and b["answer"] is None and b["evidence"] == [] and b["citations"] == []
    assert p.calls == [] and b["model"]["called"] is False                                              # not LLM_UNAVAILABLE: the model was simply never needed
    rel = b["retrieval"]["relevance"]
    assert rel["relevance_status"] == "NO_EVIDENCE" and rel["abstained"] is True and rel["low_relevance_count"] >= 1 and rel["withheld_chunks"]
    assert {"chunk_id", "coverage", "cosine"} == set(rel["withheld_chunks"][0]) and "text" not in rel["withheld_chunks"][0]     # withheld chunks are never shown as evidence


def test_ask_with_relevant_evidence_still_goes_through_the_existing_grounding(env):
    p = Provider(cite_first)
    rag_service.set_llm_provider(p)
    b = client.get("/api/v1/rag/ask", params={"q": SUPPORTED, "mode": "lexical"}).json()
    assert b["answer_status"] == "ANSWERED" and len(p.calls) == 1 and b["model"]["called"] is True and b["groundedness"]["citations_valid"] is True
    assert b["retrieval"]["relevance"]["relevance_status"] == "RELEVANT" and b["evidence"] and b["retrieval"]["relevance"]["policy"]["mode"] == "lexical"
    rag_service.set_llm_provider(Provider(lambda ev: "River overflow was reported [chunk:not-supplied#c9]."))
    bad = client.get("/api/v1/rag/ask", params={"q": SUPPORTED, "mode": "lexical"}).json()
    assert bad["answer_status"] == "INVALID_ANSWER" and bad["answer"] is None                           # the gate did not bypass the citation validator


# ------------------------------------------------------------------------------------------------------------------------- /intelligence/ask
def test_intelligence_exposes_no_evidence_and_does_not_report_llm_unavailable(env):
    p = Provider(lambda ev: "unused")
    rag_service.set_llm_provider(p)
    r = client.get("/api/v1/intelligence/ask", params={"q": OVERLAP_ONLY, "mode": "lexical"})
    b = r.json()
    assert r.status_code == 200 and b["status"] == "RETRIEVAL_EMPTY" and b["status"] != "LLM_UNAVAILABLE" and b["answer"] is None
    assert b["documentary_evidence"] == [] and p.calls == [] and b["model"]["called"] is False
    assert b["retrieval"]["relevance"]["relevance_status"] == "NO_EVIDENCE" and b["retrieval"]["relevance"]["abstained"] is True and b["retrieval"]["evidence_count"] == 0
    assert b["provenance"]["documentary_evidence"]["chunk_ids"] == [] and b["risk_context"]["provenance"] == "RISK_ENGINE"


def test_intelligence_keeps_the_risk_context_when_documents_are_withheld(env):
    p = Provider(lambda ev: "The risk engine classifies Sialkot as MODERATE [risk_engine].")
    rag_service.set_llm_provider(p)
    b = client.get("/api/v1/intelligence/ask", params={"q": "Why is Sialkot classified as MODERATE? bitcoin cryptocurrency", "mode": "lexical"}).json()
    assert b["risk_context"]["status"] == "AVAILABLE" and b["risk_context"]["record"]["risk_status"] == "MODERATE"
    assert b["documentary_evidence"] == [] and b["retrieval"]["relevance"]["abstained"] is True and b["status"] == "ANSWERED"      # risk-only answer, still validated
    assert [c["kind"] for c in b["citations"]] == ["risk_engine"] and len(p.calls) == 1 and "chunk" not in str(p.calls[0][2][0].get("kind"))


def test_relaxation_still_runs_in_the_documented_order_and_never_drops_geography(env):
    b = client.get("/api/v1/intelligence/ask", params={"q": "What flooding was reported in Sialkot? river overflow", "mode": "lexical"}).json()
    r = b["retrieval"]
    order = ["event_type", "district_to_province", "date"]
    assert r["filters_relaxed"] == [x for x in order if x in r["filters_relaxed"]]                       # a prefix of the existing order, never reordered
    assert "province" in r["filters_applied"] or "admin_unit_id" in r["filters_applied"]                  # geography is never dropped


# ---------------------------------------------------------------------------------------------------------------------------------- /agent/ask
def test_agent_reports_no_evidence_for_the_d4_style_question_without_a_special_rule(env):
    for q in (D4_LIKE, "What did PDMA advise about nuclear safety in Punjab?", "What did the reports say about the election in Punjab?"):
        r = client.get("/api/v1/agent/ask", params={"q": q, "mode": "lexical"})
        b = r.json()
        assert r.status_code == 200 and b["status"] == "NO_EVIDENCE" and b["intent"] == "DOCUMENT_SEARCH" and b["answer"] is None, (q, b["status"])
        assert b["documentary_evidence"] == [] and b["components"]["evidence"]["status"] == "NO_EVIDENCE" and b["model"]["called"] is False
        assert b["retrieval"]["relevance"]["abstained"] is True and b["components"]["evidence"]["relevance_status"] == "NO_EVIDENCE"
        assert [t["tool_name"] for t in b["tool_trace"]][:2] == ["geography.resolve_place", "rag.retrieve"]


def test_agent_still_returns_supported_evidence_and_all_endpoints_stay_read_only(env):
    b = client.get("/api/v1/agent/ask", params={"q": "What was reported about river overflow inundation in Punjab?", "mode": "lexical"}).json()
    assert b["intent"] == "DOCUMENT_SEARCH" and b["status"] == "LLM_UNAVAILABLE" and b["documentary_evidence"] and b["retrieval"]["relevance"]["relevance_status"] == "RELEVANT"
    for path in ("/api/v1/rag/search?q=flood", "/api/v1/rag/ask?q=flood", "/api/v1/intelligence/ask?q=flood", "/api/v1/agent/ask?q=flood"):
        for verb in ("post", "put", "patch", "delete"):
            assert getattr(client, verb)(path).status_code == 405, (verb, path)
