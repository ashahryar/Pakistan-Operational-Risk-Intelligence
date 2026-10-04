"""Task 30 -- REAL-MODEL integration tests (marker `real_model`).

These run the actual pinned embedding model (ONNX Runtime, BAAI/bge-small-en-v1.5) and, where noted, the stored embeddings of the
real local corpus. They are skipped automatically when the runtime/weights or the stored embeddings are unavailable (for example in
CI, which deliberately installs no model). Unit tests with a stand-in embedder are in test_embeddings_unit.py and prove only logic,
not semantic quality; this file is what exercises the real model.
"""

import glob
import hashlib
from pathlib import Path

import numpy as np
import pytest

from pipeline.rag.embeddings import DIMENSION, HF_REPO, HF_REVISION, MODEL_NAME, MODEL_VERSION, FastEmbedEmbedder, cache_dir, runtime_available

REPO = Path(__file__).resolve().parents[2]
WEIGHTS_SHA256 = "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431"


def _weights_cached() -> bool:
    return bool(glob.glob(str(Path(cache_dir()) / f"models--{HF_REPO.replace('/', '--')}" / "snapshots" / HF_REVISION / "model_optimized.onnx")))


def _live_embeddings() -> bool:
    try:
        from sqlalchemy import text

        from scripts.database.apply_serving_migration import engine_for
        with engine_for().connect() as c:
            return bool(c.execute(text("SELECT to_regclass('rag.chunk_embeddings') IS NOT NULL AND (SELECT count(*) FROM rag.chunk_embeddings) > 0")).scalar_one())
    except Exception:
        return False


real = pytest.mark.skipif(not (runtime_available() and _weights_cached()), reason="embedding runtime / model weights not available")
live = pytest.mark.skipif(not (runtime_available() and _weights_cached() and _live_embeddings()), reason="stored embeddings or model not available")
pytestmark = [pytest.mark.real_model]


@pytest.fixture(scope="module")
def embedder():
    return FastEmbedEmbedder()


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ------------------------------------------------------------------ the model itself
@real
def test_model_identity_dimension_normalization_and_determinism(embedder):
    texts = ["Heavy rain and flood warning issued for Lahore district.", "Heatwave conditions with temperatures above 45 degrees."]
    a, b = np.array(embedder.embed_documents(texts)), np.array(embedder.embed_documents(texts))
    assert a.shape == (2, DIMENSION) == (2, 384)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-3) and np.isfinite(a).all()
    assert np.allclose(a, b, atol=1e-6)                                  # same model + input -> same vector (tolerance for float math)
    info = embedder.info
    assert (info.name, info.version, info.dimension) == (MODEL_NAME, MODEL_VERSION, 384)
    assert info.metadata["weights_sha256"] == WEIGHTS_SHA256 and info.metadata["hf_revision"] == HF_REVISION and info.metadata["library"] == "fastembed"


@real
def test_model_captures_meaning_not_just_shared_words(embedder):
    q = np.array(embedder.embed_query("flooding near the river"))
    flood_paraphrase = np.array(embedder.embed_documents(["Inundation expected along the river banks."])[0])      # no shared content word with the query
    unrelated = np.array(embedder.embed_documents(["Stock market closed higher on Tuesday."])[0])
    heat = np.array(embedder.embed_documents(["Heatwave conditions with temperatures above 45 degrees."])[0])
    assert cos(q, flood_paraphrase) > cos(q, heat) > cos(q, unrelated)
    assert cos(q, flood_paraphrase) - cos(q, unrelated) > 0.2
    d1, d2 = embedder.embed_documents(["intense rainfall", "heavy downpour"])
    assert cos(d1, d2) > 0.8                                              # synonyms with no shared word


# ------------------------------------------------------------------ stored vectors are the model's output
@live
def test_stored_embeddings_equal_a_fresh_embedding_of_the_chunk_text(embedder):
    from sqlalchemy import text

    from scripts.database.apply_serving_migration import engine_for
    with engine_for().connect() as c:
        rows = c.execute(text("SELECT c.chunk_id, c.chunk_text, e.embedding FROM rag.document_chunks c JOIN rag.chunk_embeddings e USING (chunk_id) "
                              "WHERE e.model_version = :v ORDER BY md5(c.chunk_id) LIMIT 8"), {"v": MODEL_VERSION}).fetchall()
    assert len(rows) == 8
    fresh = embedder.embed_documents([r[1] for r in rows])
    for (cid, _, stored), f in zip(rows, fresh):
        assert cos(stored, f) > 0.9999 and np.allclose(stored, f, atol=1e-4), cid


# ------------------------------------------------------------------ evaluation on the real corpus
@pytest.fixture(scope="module")
def evaluation(embedder):
    from scripts.rag.evaluate_semantic import run
    return run(embedder=embedder)


def case(report, cid):
    return next(c for c in report["cases"] if c["id"] == cid)


@live
def test_semantic_retrieves_relevant_evidence_where_keywords_find_nothing(evaluation):
    for cid in ("lives_lost", "destroyed_dwellings"):
        c = case(evaluation, cid)
        assert c["lexical"]["relevant"] == 0                              # BM25 returns no relevant chunk: none of the query words occur in the text
        assert c["semantic"]["precision_at_k"] >= 0.8, c["semantic"]["top"]
        assert set(c["query_words_absent_from_corpus"]) >= {"lives"} or set(c["query_words_absent_from_corpus"]) >= {"destroyed"}


@live
def test_semantic_beats_bm25_on_the_paraphrase_set_but_not_everywhere(evaluation):
    s = evaluation["summary"]
    assert s["paraphrase_mean_precision_at_k"]["semantic"] > s["paraphrase_mean_precision_at_k"]["lexical"]
    assert s["paraphrase_cases_semantic_better"] >= 4 and s["paraphrase_cases"] == 8
    # honest counter-evidence is part of the record: keyword search wins on a rare place name and on some advisory wording
    assert case(evaluation, "geo_swat")["lexical"]["precision_at_k"] == 1.0
    assert s["paraphrase_cases_lexical_better"] >= 1


@live
def test_semantic_geographic_and_source_and_date_cases(evaluation):
    assert case(evaluation, "geo_chitral")["semantic"]["precision_at_k"] >= 0.8
    for cid in ("source_ndma", "source_pdma", "date_july"):
        c = case(evaluation, cid)
        assert c["semantic"]["returned"] > 0 and c["semantic"]["filters_respected"] and c["semantic"]["precision_at_k"] >= 0.8, cid
    assert evaluation["summary"]["filters_respected_everywhere"] is True


@live
def test_unsupported_queries_return_no_semantic_results_at_the_default_threshold(evaluation):
    # Task 31 added a near-domain unsupported query ("hurricane damage in Florida") that DOES clear the 0.60 floor: a documented limitation.
    assert evaluation["summary"]["min_score"] == 0.60 and evaluation["summary"]["empty_cases_with_semantic_results"] == ["empty_hurricane"]
    for cid in ("empty_finance", "empty_sport", "empty_recipe"):
        assert case(evaluation, cid)["semantic"]["returned"] == 0


# ------------------------------------------------------------------ API with the real model and stored embeddings
@pytest.fixture(scope="module")
def client(embedder):
    from fastapi.testclient import TestClient

    import api.app.services.rag as svc
    from api.app.main import app
    svc.set_embedder(embedder)
    yield TestClient(app)
    svc.set_embedder(None)


@live
def test_api_semantic_mode_returns_traceable_evidence(client):
    r = client.get("/api/v1/rag/search?q=people who lost their lives&mode=semantic&limit=5")
    assert r.status_code == 200
    b = r.json()
    assert b["mode"] == "semantic" and b["retrieval_method"] == "semantic_vector" and b["embedding_model"]["dimension"] == 384
    assert b["embedding_model"]["version"] == MODEL_VERSION and b["count"] == 5 and "answer" not in b
    for e in b["results"]:
        assert e["relevance"]["relevance_type"] == "semantic_vector" and e["relevance"]["score"] >= 0.60 and e["chunk_id"].startswith(e["document_id"] + "#c")
        doc = client.get("/api/v1/rag/documents/" + e["document_id"]).json()
        assert doc["raw_text"][e["snippet_document_char_start"]:e["snippet_document_char_end"]] == e["snippet"]          # verbatim, traceable
        assert e["source_reference"]["content_sha256"] == hashlib.sha256(doc["raw_text"].encode("utf-8")).hexdigest()
    lex = client.get("/api/v1/rag/search?q=people who lost their lives").json()
    assert lex["mode"] == "lexical" and lex["retrieval_method"] == "lexical_bm25_baseline"                              # default unchanged


@live
def test_api_semantic_filters_empty_and_missing_dates(client):
    ndma = client.get("/api/v1/rag/search?q=flood damage&mode=semantic&source=ndma&limit=10").json()["results"]
    assert ndma and all(e["source"] == "ndma" for e in ndma)
    dated = client.get("/api/v1/rag/search?q=flood damage&mode=semantic&date_from=2026-07-01&date_to=2026-07-31&limit=20").json()["results"]
    assert dated and all("2026-07-01" <= e["document_date"] <= "2026-07-31" for e in dated)                          # undated documents never match
    prov = client.get("/api/v1/rag/search?q=flood damage&mode=semantic&province=Punjab&event_type=flood&limit=10").json()["results"]
    assert prov and all("Punjab" in e["geography"]["provinces"] and "flood" in e["event"]["event_types"] for e in prov)
    assert client.get("/api/v1/rag/search?q=how to bake a chocolate cake&mode=semantic").json()["count"] == 0
    assert client.get("/api/v1/rag/search?q=flood&mode=semantic&event_type=earthquake").json()["count"] == 0
    assert client.get("/api/v1/rag/search?q=flood damage&mode=semantic&limit=2").json()["count"] == 2


@live
def test_semantic_search_is_read_only_and_does_not_change_stored_data(client):
    from sqlalchemy import text

    from scripts.database.apply_serving_migration import engine_for

    def snapshot():
        with engine_for().connect() as c:
            return c.execute(text("SELECT (SELECT count(*) FROM rag.chunk_embeddings), (SELECT count(*) FROM rag.document_chunks), "
                                  "(SELECT count(*) FROM rag.documents), (SELECT max(created_at) FROM rag.chunk_embeddings)")).fetchone()
    before = snapshot()
    for _ in range(3):
        assert client.get("/api/v1/rag/search?q=landslide&mode=semantic").status_code == 200
    assert snapshot() == before
    assert client.post("/api/v1/rag/search?q=landslide&mode=semantic").status_code == 405
