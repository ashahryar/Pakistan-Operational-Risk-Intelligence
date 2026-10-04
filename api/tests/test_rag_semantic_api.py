"""Task 30 -- semantic mode of GET /api/v1/rag/search. UNIT/INTEGRATION level with a patched database and the TEST-ONLY stand-in
embedder (tests/rag/test_embeddings_unit.py::ConceptStandIn); real-model behaviour is covered by tests/rag/test_embeddings_real.py."""

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
from pipeline.rag.chunking import chunk_document  # noqa: E402
from pipeline.rag.embeddings import build_embedding_records  # noqa: E402
from tests.rag.test_embeddings_unit import ConceptStandIn, make_doc  # noqa: E402

client = TestClient(app)


def semantic_response():
    return {"query": "flood", "mode": "semantic", "retrieval_method": "semantic_vector", "retrieval_note": "n",
            "embedding_model": {"name": "m", "version": "v", "dimension": 4}, "min_score": 0.5, "filters": {}, "count": 1,
            "results": [{"document_id": "d", "chunk_id": "d#c0000", "title": None, "source": "ndma", "source_type": "sitrep", "document_date": None,
                         "geography": {"province": None, "admin_unit_id": None, "admin_unit_name": None, "provinces": [], "status": "not_stated", "basis": None},
                         "event": {"event_type": None, "event_types": []},
                         "relevance": {"score": 0.8, "method": "semantic_vector", "matched_terms": [], "relevance_type": "semantic_vector", "model_version": "v"},
                         "snippet": "text", "snippet_document_char_start": 0, "snippet_document_char_end": 4,
                         "source_reference": {"url": None, "file_path": "f", "content_sha256": "x" * 64}}]}


# ------------------------------------------------------------------ routing and validation (service patched)
def test_default_mode_is_lexical_and_never_calls_the_semantic_service(monkeypatch):
    calls = []
    monkeypatch.setattr(rag_router, "search_evidence", lambda q, f, limit: calls.append("lexical") or {
        "query": q, "retrieval_method": "lexical_bm25_baseline", "retrieval_note": "n", "filters": {}, "count": 0, "results": []})
    monkeypatch.setattr(rag_router, "search_semantic_evidence", lambda *a, **k: calls.append("semantic"))
    r = client.get("/api/v1/rag/search?q=flood")
    assert r.status_code == 200 and calls == ["lexical"] and r.json()["retrieval_method"] == "lexical_bm25_baseline" and r.json()["mode"] == "lexical"
    assert client.get("/api/v1/rag/search?q=flood&mode=lexical").status_code == 200 and calls == ["lexical", "lexical"]


def test_semantic_mode_passes_filters_and_min_score(monkeypatch):
    seen = {}
    monkeypatch.setattr(rag_router, "search_semantic_evidence", lambda q, f, limit, min_score: seen.update(q=q, f=f, limit=limit, ms=min_score) or semantic_response())
    monkeypatch.setattr(rag_router, "admin_unit_exists", lambda i: True)
    r = client.get("/api/v1/rag/search?q=river overflow&mode=semantic&min_score=0.6&source=ndma&province=Punjab&admin_unit_id=2&event_type=flood"
                   "&date_from=2026-07-01&date_to=2026-07-31&limit=3")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "semantic" and body["retrieval_method"] == "semantic_vector" and body["embedding_model"]["dimension"] == 4 and "answer" not in body
    ev = body["results"][0]
    assert ev["relevance"]["relevance_type"] == "semantic_vector" and ev["relevance"]["model_version"] == "v" and ev["relevance"]["matched_terms"] == []
    assert (seen["q"], seen["limit"], seen["ms"]) == ("river overflow", 3, 0.6)
    f = seen["f"]
    assert (f.source, f.province, f.admin_unit_id, f.event_type, f.date_from, f.date_to) == ("ndma", "Punjab", 2, "flood", "2026-07-01", "2026-07-31")


@pytest.mark.parametrize("qs", ["q=flood&mode=bogus", "q=flood&mode=SEMANTIC", "q=flood&mode=", "q=flood&mode=semantic&min_score=1.5",
                                "q=flood&mode=semantic&min_score=-0.1", "q=flood&mode=semantic&min_score=abc", "q=flood&min_score=0.5",
                                "q=flood&mode=lexical&min_score=0.5", "q=flood&mode=semantic&date_from=2026-08-01&date_to=2026-07-01"])
def test_invalid_mode_and_score_parameters_are_rejected(qs):
    assert client.get(f"/api/v1/rag/search?{qs}").status_code == 422


def test_semantic_unavailable_is_a_graceful_503_not_a_500(monkeypatch):
    import pipeline.rag.embeddings as emb
    monkeypatch.setattr(emb, "runtime_available", lambda: False)
    rag_service.set_embedder(None)
    r = client.get("/api/v1/rag/search?q=flood&mode=semantic")
    assert r.status_code == 503 and "Semantic retrieval is unavailable" in r.json()["detail"] and "embedding runtime" in r.json()["detail"]
    assert client.get("/api/v1/rag/documents?limit=1").status_code in (200, 503)                          # other endpoints unaffected by the failure mode


def test_read_only_contract_is_unchanged_with_the_semantic_mode():
    assert_read_only(app, client, ("/api/v1/rag",), {"/api/v1/rag/documents", "/api/v1/rag/documents/{document_id}", "/api/v1/rag/search"})
    assert client.post("/api/v1/rag/search?q=flood&mode=semantic").status_code == 405


# ------------------------------------------------------------------ service end-to-end (patched DB + stand-in embedder)
class FakeDb:
    def __init__(self, embedder, version=None):
        self.docs = [make_doc("f1", "River overflow caused inundation.", event_raw=["Flood"], date_text=None),
                     make_doc("h1", "Scorching temperature and a heatwave.", source="pdma", source_type="daily_report", event_raw=["Heatwave"],
                              date_text="9 July 2026")]
        self.chunks = [c for d in self.docs for c in chunk_document(d)]
        recs, _ = build_embedding_records(self.chunks, embedder)
        self.records = [dict(r, model_version=version or r["model_version"]) for r in recs]

    def __call__(self, sql, params=None):
        s = " ".join(sql.split())
        if "count(*) AS n, max(loaded_at) AS t FROM rag.documents" in s:
            return [{"n": len(self.docs), "t": "t0"}]
        if "count(*) AS n, max(created_at) AS t FROM rag.chunk_embeddings" in s:
            return [{"n": sum((r["model_name"], r["model_version"]) == (params["m"], params["v"]) for r in self.records), "t": "t0"}]
        if s.startswith("SELECT document_id, source") and "FROM rag.documents WHERE is_current" in s:
            return [{k: v for k, v in d.items() if k not in ("raw_text",)} for d in self.docs]
        if "FROM rag.document_chunks c JOIN rag.documents d" in s and "e.chunk_id" not in s:
            return [{k: c[k] for k in ("chunk_id", "document_id", "chunk_index", "char_start", "char_end", "chunk_text")} for c in self.chunks]
        if "FROM rag.chunk_embeddings e JOIN" in s:
            return [dict(r) for r in self.records if (r["model_name"], r["model_version"]) == (params["m"], params["v"])]
        raise AssertionError(f"unexpected SQL: {s[:120]}")


@pytest.fixture
def semantic_env(monkeypatch):
    emb = ConceptStandIn()
    monkeypatch.setattr(rag_service, "fetch_all", FakeDb(emb))
    rag_service._cache.update(token=None, retriever=None)
    rag_service.set_embedder(emb)
    monkeypatch.setattr(rag_router, "admin_unit_exists", lambda i: True)
    yield emb
    rag_service.set_embedder(None)
    rag_service._cache.update(token=None, retriever=None)


def test_semantic_search_returns_evidence_with_full_provenance(semantic_env):
    r = client.get("/api/v1/rag/search?q=inundation&mode=semantic&min_score=0.5")
    assert r.status_code == 200
    b = r.json()
    assert b["mode"] == "semantic" and b["embedding_model"] == {"name": "stand-in", "version": "v1", "dimension": 5} and b["min_score"] == 0.5
    assert b["count"] == 1
    e = b["results"][0]
    assert e["document_id"].endswith(":f1") and e["chunk_id"].startswith(e["document_id"] + "#c")
    assert e["relevance"]["relevance_type"] == "semantic_vector" and e["snippet"] == "River overflow caused inundation."
    assert e["source_reference"]["file_path"] == "data/parsed/f1.json" and e["event"]["event_types"] == ["flood"] and e["geography"]["provinces"] == ["Punjab"]


def test_semantic_filters_empty_results_and_missing_dates(semantic_env):
    ok = client.get("/api/v1/rag/search?q=scorching&mode=semantic&min_score=0.5&source=pdma").json()
    assert [x["document_id"].split(":")[-1] for x in ok["results"]] == ["h1"]
    assert client.get("/api/v1/rag/search?q=scorching&mode=semantic&min_score=0.5&source=ndma").json()["results"] == []
    assert client.get("/api/v1/rag/search?q=inundation&mode=semantic&min_score=0.5&date_from=2000-01-01").json()["results"] == []   # f1 is undated
    assert client.get("/api/v1/rag/search?q=unrelated words&mode=semantic&min_score=0.9").json() == {
        **client.get("/api/v1/rag/search?q=unrelated words&mode=semantic&min_score=0.9").json(), "count": 0, "results": []}


def test_lexical_mode_still_works_in_the_same_environment(semantic_env):
    b = client.get("/api/v1/rag/search?q=inundation").json()
    assert b["mode"] == "lexical" and b["retrieval_method"] == "lexical_bm25_baseline" and b["count"] == 1
    assert b["results"][0]["relevance"]["relevance_type"] == "lexical_bm25_baseline" and b["results"][0]["relevance"]["matched_terms"] == ["inundation"]
    assert b["embedding_model"] is None


def test_embeddings_from_a_different_model_version_are_refused_with_503(monkeypatch):
    emb = ConceptStandIn()
    monkeypatch.setattr(rag_service, "fetch_all", FakeDb(emb, version="v-other"))        # stored vectors are from another version
    rag_service.set_embedder(emb)
    rag_service._cache.update(token=None, retriever=None)
    r = client.get("/api/v1/rag/search?q=flood&mode=semantic")
    assert r.status_code == 503 and "no embeddings are stored" in r.json()["detail"]
    rag_service.set_embedder(None)
