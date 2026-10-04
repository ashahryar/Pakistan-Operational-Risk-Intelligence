"""Task 29 -- RAG evidence endpoints. Router behaviour is tested with the service layer patched (no database); live checks
run against the loaded rag.* tables and skip when they are absent."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.app.db as api_db  # noqa: E402
import api.app.routers.rag as rag_router  # noqa: E402
from api.app.main import app  # noqa: E402

client = TestClient(app)


def evidence(**over):
    e = {"document_id": "ndma:sitrep:abc", "chunk_id": "ndma:sitrep:abc#c0001", "title": "NDMA Sitrep", "source": "ndma", "source_type": "sitrep",
         "document_date": "2026-07-01", "geography": {"province": None, "admin_unit_id": None, "admin_unit_name": None, "provinces": ["Punjab"],
                                                       "status": "resolved", "basis": "mentioned_in_text"},
         "event": {"event_type": "flood", "event_types": ["flood"]},
         "relevance": {"score": 1.5, "method": "lexical_bm25_baseline", "matched_terms": ["flood"]}, "snippet": "flood in Lahore",
         "snippet_document_char_start": 10, "snippet_document_char_end": 25,
         "source_reference": {"url": None, "file_path": "data/parsed/ndma/sitreps/abc.json", "content_sha256": "x" * 64}}
    e.update(over)
    return e


def response(results, **filters):
    return {"query": "flood", "retrieval_method": "lexical_bm25_baseline", "retrieval_note": "baseline", "filters": filters,
            "count": len(results), "results": results}


def doc_summary(**over):
    d = {"document_id": "ndma:sitrep:abc", "source": "ndma", "source_type": "sitrep", "title": None, "document_date": None, "document_date_text": None,
         "document_date_basis": "not_stated", "published_at": None, "url": None, "file_path": None, "province": None, "admin_unit_id": None,
         "admin_unit_name": None, "provinces": [], "districts": [], "admin_unit_ids": [], "geography_status": "not_stated", "geography_basis": None,
         "event_type": None, "event_types": [], "language_script": "latin", "content_sha256": "x" * 64, "ingestion_timestamp": None,
         "parser_version": None, "normalization_version": "rag-normalize-1.0.0", "chunk_count": 2, "text_chars": 100}
    d.update(over)
    return d


# -------------------------------------------------------------------- no database
def test_valid_search_passes_filters_and_returns_evidence(monkeypatch):
    seen = {}

    def fake(q, filters, limit):
        seen.update(q=q, f=filters, limit=limit)
        return response([evidence()])
    monkeypatch.setattr(rag_router, "search_evidence", fake)
    monkeypatch.setattr(rag_router, "admin_unit_exists", lambda i: True)
    r = client.get("/api/v1/rag/search?q=flood Lahore&source=ndma&source_type=sitrep&province=Punjab&admin_unit_id=2&event_type=flood"
                   "&date_from=2026-07-01&date_to=2026-07-31&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["retrieval_method"] == "lexical_bm25_baseline" and body["count"] == 1 and "answer" not in body
    ev = body["results"][0]
    assert {"document_id", "chunk_id", "title", "source", "document_date", "geography", "event", "relevance", "snippet", "source_reference"} <= set(ev)
    f = seen["f"]
    assert (seen["q"], seen["limit"]) == ("flood Lahore", 5)
    assert (f.source, f.source_type, f.province, f.admin_unit_id, f.event_type, f.date_from, f.date_to) == (
        "ndma", "sitrep", "Punjab", 2, "flood", "2026-07-01", "2026-07-31")


@pytest.mark.parametrize("qs", ["q=flood&date_from=2026-13-45", "q=flood&date_to=notadate", "q=flood&limit=0", "q=flood&limit=51",
                                "q=a", "q=", "", "q=flood&admin_unit_id=0", "q=flood&admin_unit_id=abc", "q=flood&date_from=2026-08-01&date_to=2026-07-01"])
def test_invalid_search_parameters_are_422(qs):
    assert client.get(f"/api/v1/rag/search?{qs}").status_code == 422


def test_empty_search_result_is_200_with_zero_results(monkeypatch):
    monkeypatch.setattr(rag_router, "search_evidence", lambda q, f, limit: response([]))
    r = client.get("/api/v1/rag/search?q=zzzzqqqq")
    assert r.status_code == 200 and r.json()["count"] == 0 and r.json()["results"] == []


def test_unknown_admin_unit_is_404(monkeypatch):
    monkeypatch.setattr(rag_router, "admin_unit_exists", lambda i: False)
    assert client.get("/api/v1/rag/search?q=flood&admin_unit_id=999999").status_code == 404
    assert client.get("/api/v1/rag/documents?admin_unit_id=999999").status_code == 404


def test_document_list_and_null_metadata_are_preserved(monkeypatch):
    monkeypatch.setattr(rag_router, "list_documents", lambda *a: [doc_summary()])
    r = client.get("/api/v1/rag/documents?source=ndma&limit=1")
    assert r.status_code == 200 and r.json()[0]["document_date"] is None and r.json()[0]["title"] is None and r.json()[0]["url"] is None


def test_document_not_found_is_404_and_found_returns_text_and_chunks(monkeypatch):
    monkeypatch.setattr(rag_router, "get_document", lambda i: None)
    assert client.get("/api/v1/rag/documents/nope:nope:nope").status_code == 404
    detail = {**doc_summary(), "geography_text": [], "event_type_raw": [], "metadata": {}, "raw_text": "verbatim  text\n",
              "chunks": [{"chunk_id": "ndma:sitrep:abc#c0000", "chunk_index": 0, "char_start": 0, "char_end": 14, "chunk_sha256": "y" * 64}]}
    monkeypatch.setattr(rag_router, "get_document", lambda i: detail if i == "ndma:sitrep:abc" else None)
    r = client.get("/api/v1/rag/documents/ndma:sitrep:abc")
    assert r.status_code == 200 and r.json()["raw_text"] == "verbatim  text\n" and r.json()["chunks"][0]["chunk_id"].endswith("#c0000")


def test_documents_endpoint_validates_parameters():
    assert client.get("/api/v1/rag/documents?limit=0").status_code == 422
    assert client.get("/api/v1/rag/documents?limit=501").status_code == 422
    assert client.get("/api/v1/rag/documents?offset=-1").status_code == 422
    assert client.get("/api/v1/rag/documents?date_from=2026-08-01&date_to=2026-07-01").status_code == 422


def test_database_failure_is_503_not_an_empty_result(monkeypatch):
    class Boom:
        def connect(self):
            raise ConnectionError("down")
    monkeypatch.setattr(api_db, "engine", Boom())
    assert client.get("/api/v1/rag/documents").status_code == 503
    assert client.get("/api/v1/rag/search?q=flood").status_code == 503


def test_rag_api_is_read_only():
    # app.routes wraps included routers in this FastAPI version, so the OpenAPI document is the reliable source of truth
    paths = {p: set(m) for p, m in client.get("/openapi.json").json()["paths"].items() if p.startswith("/api/v1/rag")}
    assert set(paths) == {"/api/v1/rag/documents", "/api/v1/rag/documents/{document_id}", "/api/v1/rag/search"}
    assert all(m == {"get"} for m in paths.values())
    for verb in (client.post, client.put, client.patch, client.delete):
        assert verb("/api/v1/rag/search").status_code == 405 and verb("/api/v1/rag/documents").status_code == 405


def test_existing_endpoints_are_still_registered():
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/health", "/api/v1/geography/admin-units", "/api/v1/geography/boundaries", "/api/v1/risk", "/api/v1/risk/latest", "/api/v1/risk/map",
              "/api/v1/rag/search", "/api/v1/rag/documents"):
        assert p in paths


# -------------------------------------------------------------------- live database
def _live() -> bool:
    try:
        from sqlalchemy import text

        from config.database import engine
        with engine.connect() as c:
            return bool(c.execute(text("SELECT to_regclass('rag.documents') IS NOT NULL AND (SELECT count(*) FROM rag.documents) > 0")).scalar_one())
    except Exception:
        return False


live = pytest.mark.skipif(not _live(), reason="rag tables not loaded")


@live
def test_live_search_returns_traceable_evidence():
    r = client.get("/api/v1/rag/search?q=landslide&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 0 and body["retrieval_method"] == "lexical_bm25_baseline" and "not semantic" in body["retrieval_note"].lower()
    for e in body["results"]:
        assert e["chunk_id"].startswith(e["document_id"] + "#c") and "landslide" in e["snippet"].lower() and e["source_reference"]["file_path"]
        doc = client.get("/api/v1/rag/documents/" + e["document_id"]).json()
        assert doc["raw_text"][e["snippet_document_char_start"]:e["snippet_document_char_end"]] == e["snippet"]       # verbatim, traceable


@live
def test_live_filters_work_and_missing_dates_never_match_date_filters():
    allr = client.get("/api/v1/rag/search?q=flood&limit=50").json()["results"]
    assert {e["source"] for e in allr} > {"ndma"} or allr
    ndma = client.get("/api/v1/rag/search?q=flood&source=ndma&limit=50").json()["results"]
    assert ndma and all(e["source"] == "ndma" for e in ndma)
    dated = client.get("/api/v1/rag/search?q=flood&date_from=2026-07-01&date_to=2026-07-31&limit=50").json()["results"]
    assert dated and all("2026-07-01" <= e["document_date"] <= "2026-07-31" for e in dated)
    assert client.get("/api/v1/rag/search?q=flood&event_type=earthquake").json()["count"] == 0
    docs = client.get("/api/v1/rag/documents?limit=500").json()
    assert len(docs) == 253 and any(d["document_date"] is None for d in docs)
    assert not any(d["document_id"] in {e["document_id"] for e in dated} for d in docs if d["document_date"] is None)
    pun = client.get("/api/v1/rag/documents?province=Punjab&source=pdma&limit=500").json()
    assert pun and all("Punjab" in d["provinces"] for d in pun)


@live
def test_live_document_detail_hashes_and_chunks_are_consistent():
    import hashlib
    d = client.get("/api/v1/rag/documents?source=ffc&limit=1").json()[0]
    full = client.get("/api/v1/rag/documents/" + d["document_id"]).json()
    assert hashlib.sha256(full["raw_text"].encode("utf-8")).hexdigest() == full["content_sha256"]
    assert [c["chunk_index"] for c in full["chunks"]] == list(range(len(full["chunks"]))) and full["chunks"][-1]["char_end"] == len(full["raw_text"])
    assert full["url"].startswith("https://ffc.gov.pk/") and full["geography_status"] == "not_stated"
