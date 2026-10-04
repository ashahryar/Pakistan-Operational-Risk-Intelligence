"""Task 31 -- GET /api/v1/rag/ask and hybrid search mode. Patched database, TEST-ONLY stand-in embedder, scripted answer provider.
No network, no LLM credential. These tests cover the API contract and the validation/abstention handling; they say nothing about the
quality of a real model's answers (see docs: no real LLM was available)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.app.routers.rag as rag_router  # noqa: E402
import api.app.services.rag as rag_service  # noqa: E402
from api.app.main import app  # noqa: E402
from api.tests._readonly import assert_read_only  # noqa: E402
from api.tests.test_rag_semantic_api import FakeDb  # noqa: E402
from pipeline.rag.llm import LLMMalformedResponse, LLMResult, LLMTimeout  # noqa: E402
from tests.rag.test_embeddings_unit import ConceptStandIn  # noqa: E402

client = TestClient(app)


class Provider:
    name, model = "scripted", "s-1"

    def __init__(self, fn=None, exc=None):
        self.fn, self.exc, self.calls = fn, exc, []

    def generate(self, system, question, evidence, constraints):
        self.calls.append((system, question, evidence))
        if self.exc:
            raise self.exc
        return LLMResult(self.fn(evidence), self.name, self.model)


def cite_first(evidence):
    return f"River overflow was reported in the area [chunk:{evidence[0]['chunk_id']}]."


@pytest.fixture
def env(monkeypatch):
    emb = ConceptStandIn()
    monkeypatch.setattr(rag_service, "fetch_all", FakeDb(emb))
    rag_service._cache.update(token=None, retriever=None)
    rag_service._sem_cache.update(token=None, retriever=None)
    rag_service._hyb_cache.update(key=None, retriever=None)
    rag_service.set_embedder(emb)
    rag_service.set_llm_provider(None)
    for k in ("PORI_LLM_PROVIDER", "PORI_LLM_MODEL", "PORI_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(rag_router, "admin_unit_exists", lambda i: True)
    yield emb
    rag_service.set_embedder(None)
    rag_service.set_llm_provider(None)
    rag_service._cache.update(token=None, retriever=None)
    rag_service._sem_cache.update(token=None, retriever=None)
    rag_service._hyb_cache.update(key=None, retriever=None)


# ------------------------------------------------------------------ hybrid search mode
def test_hybrid_search_returns_evidence_with_rank_provenance(env):
    r = client.get("/api/v1/rag/search?q=inundation&mode=hybrid&min_score=0.5")
    assert r.status_code == 200
    b = r.json()
    assert b["mode"] == "hybrid" and b["retrieval_method"] == "hybrid_rrf" and b["embedding_model"]["name"] == "stand-in" and b["count"] == 1
    rel = b["results"][0]["relevance"]
    assert rel["relevance_type"] == "hybrid_rrf" and rel["lexical_rank"] == 1 and rel["semantic_rank"] == 1 and rel["fused_rank"] == 1
    assert rel["lexical_score"] > 0 and rel["semantic_score"] == pytest.approx(1.0) and rel["model_version"] == "v1"
    assert "answer" not in b


def test_default_search_mode_is_still_lexical_with_no_hybrid_fields(env):
    b = client.get("/api/v1/rag/search?q=inundation").json()
    assert b["mode"] == "lexical" and b["retrieval_method"] == "lexical_bm25_baseline"
    assert b["results"][0]["relevance"]["lexical_rank"] is None and b["results"][0]["relevance"]["fused_rank"] is None


def test_hybrid_search_min_score_rules_and_unavailability(env, monkeypatch):
    assert client.get("/api/v1/rag/search?q=flood&mode=lexical&min_score=0.5").status_code == 422
    import pipeline.rag.embeddings as emb
    monkeypatch.setattr(emb, "runtime_available", lambda: False)
    rag_service.set_embedder(None)
    r = client.get("/api/v1/rag/search?q=flood&mode=hybrid")
    assert r.status_code == 503 and "Hybrid retrieval is unavailable" in r.json()["detail"]
    assert client.get("/api/v1/rag/search?q=flood").status_code == 200                              # lexical unaffected


# ------------------------------------------------------------------ ask: success and the validation outcomes
def test_valid_question_returns_validated_answer_citations_and_separate_evidence(env):
    p = Provider(cite_first)
    rag_service.set_llm_provider(p)
    r = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5&top_k=3")
    assert r.status_code == 200
    b = r.json()
    cid = b["evidence"][0]["chunk_id"]
    assert b["answer_status"] == "ANSWERED" and b["answer"] == f"River overflow was reported in the area [chunk:{cid}]."
    assert [c["chunk_id"] for c in b["citations"]] == [cid] and b["citations"][0]["source_reference"]["file_path"] == "data/parsed/f1.json"
    assert b["retrieval"]["mode"] == "hybrid" and b["retrieval"]["method"] == "hybrid_rrf" and b["retrieval"]["top_k"] == 3
    assert b["model"] == {"provider": "scripted", "model": "s-1", "configured": True, "error": None}
    g = b["groundedness"]
    assert g["citations_valid"] is True and g["all_sentences_cited"] is True and g["evidence_supplied"] == 1 and g["evidence_cited"] == 1
    assert "not an official warning" in b["disclaimer"]
    sent = p.calls[0][2][0]                                                                          # what the model was given
    assert sent["chunk_id"] == cid and sent["text"] == "River overflow caused inundation." and sent["source"] == "ndma"


def test_unknown_citation_is_rejected_and_the_answer_is_withheld(env):
    rag_service.set_llm_provider(Provider(lambda ev: "Floods were reported in several areas [chunk:fake:doc#c9]."))
    b = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5").json()
    assert b["answer_status"] == "INVALID_ANSWER" and b["answer"] is None and b["citations"] == []
    assert {"code": "unknown_citation", "chunk_id": "fake:doc#c9"} in b["groundedness"]["problems"]
    assert b["groundedness"]["citations_valid"] is False and "fake:doc#c9" in b["groundedness"]["rejected_answer_text"]
    assert b["evidence"]                                                                              # evidence is still returned


def test_answer_without_citations_is_rejected(env):
    rag_service.set_llm_provider(Provider(lambda ev: "Several rivers overflowed and caused flooding."))
    b = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5").json()
    assert b["answer_status"] == "INVALID_ANSWER" and b["answer"] is None
    assert {"code": "no_citations"} in b["groundedness"]["problems"] and b["groundedness"]["all_sentences_cited"] is False


def test_model_abstention_is_reported_as_insufficient_evidence(env):
    rag_service.set_llm_provider(Provider(lambda ev: "INSUFFICIENT_EVIDENCE"))
    b = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5").json()
    assert b["answer_status"] == "INSUFFICIENT_EVIDENCE" and b["citations"] == [] and b["evidence"]


def test_empty_retrieval_returns_200_without_calling_the_model(env):
    p = Provider(cite_first)
    rag_service.set_llm_provider(p)
    r = client.get("/api/v1/rag/ask?q=xyzzy&mode=hybrid&min_score=0.5")
    assert r.status_code == 200 and r.json()["answer_status"] == "RETRIEVAL_EMPTY" and r.json()["answer"] is None and r.json()["evidence"] == []
    assert p.calls == []


def test_empty_retrieval_does_not_need_a_configured_provider(env):
    assert client.get("/api/v1/rag/ask?q=xyzzy&min_score=0.5").json()["answer_status"] == "RETRIEVAL_EMPTY"


def test_unconfigured_provider_is_a_503_with_evidence_and_a_clear_reason(env):
    r = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5")
    assert r.status_code == 503
    b = r.json()
    assert b["answer_status"] == "LLM_UNAVAILABLE" and b["answer"] is None and b["evidence"]
    assert b["model"]["configured"] is False and "no LLM provider is configured" in b["model"]["error"]


@pytest.mark.parametrize("exc,kind", [(LLMTimeout("slow"), "timeout"), (LLMMalformedResponse("bad"), "malformed_response")])
def test_provider_failures_are_503_llm_unavailable_with_evidence(env, exc, kind):
    rag_service.set_llm_provider(Provider(exc=exc))
    r = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5")
    assert r.status_code == 503 and r.json()["answer_status"] == "LLM_UNAVAILABLE" and r.json()["evidence"]
    assert r.json()["model"]["configured"] is True and r.json()["model"]["error"].startswith(kind)


def test_configured_from_environment_never_leaks_the_credential(env, monkeypatch):
    monkeypatch.setenv("PORI_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("PORI_LLM_MODEL", "m")
    monkeypatch.setenv("PORI_LLM_API_KEY", "sk-LEAK-CHECK-999")
    monkeypatch.setenv("PORI_LLM_BASE_URL", "http://127.0.0.1:9/v1")                                 # nothing listens: the call fails
    r = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5")
    assert r.status_code == 503 and r.json()["answer_status"] == "LLM_UNAVAILABLE"
    assert "sk-LEAK-CHECK-999" not in r.text


def test_lexical_mode_ask_needs_no_embedding_runtime(env, monkeypatch):
    import pipeline.rag.embeddings as emb
    monkeypatch.setattr(emb, "runtime_available", lambda: False)
    rag_service.set_embedder(None)
    rag_service.set_llm_provider(Provider(cite_first))
    b = client.get("/api/v1/rag/ask?q=inundation&mode=lexical").json()
    assert b["answer_status"] == "ANSWERED" and b["retrieval"]["mode"] == "lexical" and b["retrieval"]["embedding_model"] is None
    assert client.get("/api/v1/rag/ask?q=inundation&mode=hybrid").status_code == 503                 # hybrid needs the runtime


def test_filters_are_applied_to_retrieval(env):
    rag_service.set_llm_provider(Provider(cite_first))
    assert client.get("/api/v1/rag/ask?q=inundation&min_score=0.5&source=pdma").json()["answer_status"] == "RETRIEVAL_EMPTY"
    b = client.get("/api/v1/rag/ask?q=inundation&min_score=0.5&source=ndma&province=Punjab").json()
    assert b["answer_status"] == "ANSWERED" and b["retrieval"]["filters"] == {"source": "ndma", "province": "Punjab"}


# ------------------------------------------------------------------ validation and read-only
@pytest.mark.parametrize("qs", ["q=flood&mode=bogus", "q=flood&mode=", "q=f", "", "q=flood&top_k=0", "q=flood&top_k=11", "q=flood&top_k=abc",
                                "q=flood&date_from=not-a-date", "q=flood&date_from=2026-08-01&date_to=2026-07-01", "q=flood&mode=lexical&min_score=0.5",
                                "q=flood&min_score=1.5", "q=flood&admin_unit_id=0"])
def test_invalid_parameters_are_rejected_with_422(env, qs):
    assert client.get(f"/api/v1/rag/ask?{qs}").status_code == 422


def test_ask_is_read_only(env):
    assert_read_only(app, client, ("/api/v1/rag",), {"/api/v1/rag/documents", "/api/v1/rag/documents/{document_id}", "/api/v1/rag/search", "/api/v1/rag/ask"})
    for verb in ("post", "put", "patch", "delete"):
        assert getattr(client, verb)("/api/v1/rag/ask?q=flood").status_code == 405


def test_ask_default_mode_is_hybrid_and_search_default_stays_lexical():
    ask = next(p for p in app.openapi()["paths"]["/api/v1/rag/ask"]["get"]["parameters"] if p["name"] == "mode")
    search = next(p for p in app.openapi()["paths"]["/api/v1/rag/search"]["get"]["parameters"] if p["name"] == "mode")
    assert ask["schema"]["default"] == rag_router.ASK_DEFAULT_MODE and search["schema"]["default"] == "lexical"
    assert set(search["schema"]["enum"]) == {"lexical", "semantic", "hybrid"}


def test_hybrid_and_semantic_degrade_to_unavailable_when_numpy_and_the_runtime_are_missing():
    """Regression: in the lexical-only image numpy is not installed, so importing the hybrid module first made /search?mode=hybrid and
    /ask answer 500 instead of 503. Simulated in a subprocess with numpy and fastembed blocked."""
    import subprocess
    code = ("import sys; sys.modules['numpy']=None; sys.modules['fastembed']=None\n"
            "import api.app.services.rag as s\n"
            "for fn in (s.get_hybrid_retriever, s.get_semantic_retriever):\n"
            "    try: fn()\n"
            "    except s.SemanticUnavailable as e: print('unavailable', 'runtime' in str(e))\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120)
    assert out.stdout.split() == ["unavailable", "True", "unavailable", "True"], (out.stdout, out.stderr[-500:])
