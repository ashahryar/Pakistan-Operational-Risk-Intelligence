"""Task 30 -- UNIT tests for the embedding contract and the semantic retriever.

These use `ConceptStandIn`, a tiny test-only stand-in that maps a few words onto a handful of axes so similarity is predictable.
It is NOT an embedding model and proves nothing about production semantic quality; that is covered by the separate real-model
tests (tests/rag/test_embeddings_real.py, marker `real_model`). The stand-in lives only in test code; production modules contain
no placeholder-vector generator (checked below).
"""

import math
import re
from pathlib import Path

import pytest

from pipeline.rag.chunking import chunk_document
from pipeline.rag.embeddings import MODEL_NAME, MODEL_VERSION, ModelInfo, build_embedding_records, validate_vector
from pipeline.rag.evidence import build_evidence
from pipeline.rag.normalize import normalize_document
from pipeline.rag.retrieval import LexicalRetriever, SearchFilters
from pipeline.rag.semantic import IncompatibleEmbeddings, SemanticRetriever

REPO = Path(__file__).resolve().parents[2]
AXES = {"flood": ["flood", "inundation", "overflow", "river"], "heat": ["heatwave", "hot", "temperature", "scorching"],
        "slide": ["landslide", "slope", "collapse", "debris"], "money": ["stock", "market", "earnings"], "other": []}
DIM = len(AXES)


class ConceptStandIn:
    """TEST-ONLY. Unit-length vectors from word-to-axis membership; deterministic and meaningful to the tests."""

    def __init__(self, name="stand-in", version="v1"):
        self.info = ModelInfo(name, version, DIM, True, {"test_only": True})
        self.calls = []

    def _vec(self, text):
        words = re.findall(r"\w+", text.lower())
        v = [float(sum(w in ws for w in words)) for ws in AXES.values()]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v] if any(v) else [0.0] * (DIM - 1) + [1.0]      # unknown words -> the "other" axis

    def embed_documents(self, texts):
        self.calls.append(list(texts))
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def make_doc(native, text, **over):
    src = {"source": "ndma", "source_type": "sitrep", "native_id": native, "title": f"t-{native}", "text": text, "text_fields": None,
           "date_text": "1 July 2026", "url": None, "file_path": f"data/parsed/{native}.json", "provinces_raw": ["Punjab"], "districts_raw": [],
           "jurisdiction": None, "geography_basis": "mentioned_in_text", "event_raw": [], "ingestion_timestamp": "2026-09-01T00:00:00",
           "parser_version": None, "published_at": None, "metadata": {}}
    src.update(over)
    return normalize_document(src, {"Punjab": 2, "Sindh": 3})


def build(embedder=None):
    docs = [make_doc("f1", "River overflow caused inundation in low lying areas.", event_raw=["Flood"], date_text="1 July 2026"),
            make_doc("f2", "Flood waters entered the town after the river rose.", source="pdma", source_type="daily_report",
                     date_text="20 July 2026", provinces_raw=["Sindh"], event_raw=["Flood"]),
            make_doc("h1", "Scorching temperature and a heatwave across the plains.", event_raw=["Heatwave"], date_text="5 July 2026"),
            make_doc("s1", "A landslide sent debris onto the slope road.", event_raw=["Landslide"], date_text=None),
            make_doc("m1", "Stock market earnings rose.", date_text="9 July 2026", provinces_raw=[])]
    chunks = [c for d in docs for c in chunk_document(d)]
    emb = embedder or ConceptStandIn()
    records, failures = build_embedding_records(chunks, emb)
    assert failures == []
    return docs, chunks, records, emb


def retr(embedder=None, **kw):
    docs, chunks, records, emb = build(embedder)
    return docs, chunks, records, SemanticRetriever(docs, chunks, records, emb, **kw)


def ids(hits):
    return [h.document_id.split(":")[-1] for h in hits]


# ------------------------------------------------------------------ embedding contract
def test_record_names_its_chunk_model_version_and_dimension():
    docs, chunks, records, emb = build()
    assert [r["chunk_id"] for r in records] == [c["chunk_id"] for c in chunks]                 # stable chunk association, same order
    for r, c in zip(records, chunks):
        assert (r["model_name"], r["model_version"], r["embedding_dimension"], r["normalized"]) == ("stand-in", "v1", DIM, True)
        assert len(r["embedding"]) == DIM and r["chunk_sha256"] == c["chunk_sha256"] and r["metadata"] == {"test_only": True}


def test_vector_validation_rejects_wrong_dimension_nan_zero_and_unnormalized():
    validate_vector([1.0, 0.0, 0.0], 3)
    for bad, msg in (([1.0, 0.0], "dimensions"), ([float("nan"), 0, 0], "non-finite"), ([0.0, 0.0, 0.0], "zero vector"),
                     ([2.0, 0.0, 0.0], "norm"), (["a", 0, 0], "non-finite or non-numeric")):
        with pytest.raises(ValueError, match=msg):
            validate_vector(bad, 3)
    validate_vector([2.0, 0.0, 0.0], 3, normalized=False)


def test_empty_chunk_text_and_bad_vectors_are_failures_not_placeholders():
    chunks = [{"chunk_id": "d#c0000", "chunk_text": "river flood", "chunk_sha256": "a"}, {"chunk_id": "d#c0001", "chunk_text": "   ", "chunk_sha256": "b"}]
    records, failures = build_embedding_records(chunks, ConceptStandIn())
    assert [r["chunk_id"] for r in records] == ["d#c0000"] and failures == [{"chunk_id": "d#c0001", "error": "empty chunk text"}]

    class Bad(ConceptStandIn):
        def embed_documents(self, texts):
            return [[0.0] * DIM for _ in texts]                                                 # a model returning zero vectors
    records, failures = build_embedding_records(chunks[:1], Bad())
    assert records == [] and "zero vector" in failures[0]["error"]


def test_a_failing_chunk_does_not_hide_the_others():
    class Flaky(ConceptStandIn):
        def embed_documents(self, texts):
            if any("poison" in t for t in texts):
                if len(texts) > 1:
                    raise RuntimeError("batch failed")
                raise RuntimeError("poisoned chunk")
            return super().embed_documents(texts)
    chunks = [{"chunk_id": f"d#c{i:04d}", "chunk_text": t, "chunk_sha256": str(i)} for i, t in enumerate(["flood river", "poison text", "heat hot"])]
    records, failures = build_embedding_records(chunks, Flaky(), batch_size=8)
    assert [r["chunk_id"] for r in records] == ["d#c0000", "d#c0002"] and failures[0]["chunk_id"] == "d#c0001"
    assert "poisoned chunk" in failures[0]["error"]


def test_count_mismatch_from_the_model_is_detected():
    class Short(ConceptStandIn):
        def embed_documents(self, texts):
            return super().embed_documents(texts)[:-1]
    chunks = [{"chunk_id": f"d#c{i:04d}", "chunk_text": "flood", "chunk_sha256": "x"} for i in range(2)]
    records, failures = build_embedding_records(chunks, Short())
    assert len(records) + len(failures) == 2                      # nothing is silently dropped


def test_embedding_generation_is_deterministic_for_a_fixed_model():
    _, _, a, _ = build()
    _, _, b, _ = build()
    assert a == b


def test_production_modules_contain_no_placeholder_vector_generators():
    for name in ("embeddings.py", "semantic.py"):
        code = re.sub(r"#[^\n]*|\"\"\"[\s\S]*?\"\"\"", "", (REPO / "pipeline" / "rag" / name).read_text(encoding="utf-8"))
        for forbidden in ("import random", "np.random", "numpy.random", "np.zeros", "np.ones", "[0.0] *", "TfidfVectorizer", "hash(", "sha256(text"):
            assert forbidden not in code, (name, forbidden)
    assert MODEL_NAME == "BAAI/bge-small-en-v1.5" and "@" in MODEL_VERSION and len(MODEL_VERSION.split("@")[1]) == 40   # pinned immutable revision


# ------------------------------------------------------------------ semantic retrieval
def test_semantic_ranking_by_similarity_and_meaning_without_shared_words():
    _, _, _, r = retr()
    hits = r.search("inundation", SearchFilters(), 5, min_score=0.5)
    assert ids(hits) == ["f1", "f2"] or set(ids(hits)) == {"f1", "f2"}           # flood-axis chunks, incl. one that never says "inundation"
    assert all(h.method == "semantic_vector" and h.matched_terms == () and h.model_version == "v1" for h in hits)
    assert hits[0].score >= hits[1].score
    assert ids(r.search("scorching", SearchFilters(), 3, min_score=0.5)) == ["h1"]


def test_semantic_retrieval_differs_from_the_lexical_baseline():
    docs, chunks, _, r = retr()
    lex = LexicalRetriever(docs, chunks)
    assert lex.search("inundation", SearchFilters(), 5)[0].document_id.endswith(":f1")           # only the literal match
    assert not any(h.document_id.endswith(":f2") for h in lex.search("inundation", SearchFilters(), 5))
    assert any(h.document_id.endswith(":f2") for h in r.search("inundation", SearchFilters(), 5, min_score=0.5))
    assert lex.search("inundation", SearchFilters(), 5)[0].method == "lexical_bm25_baseline"      # BM25 is never mislabelled semantic


def test_source_province_event_admin_and_date_filters_work_with_semantic_search():
    _, _, _, r = retr()
    q = "river flood"
    assert set(ids(r.search(q, SearchFilters(source="pdma"), 5, 0.5))) == {"f2"}
    assert set(ids(r.search(q, SearchFilters(province="sindh"), 5, 0.5))) == {"f2"}
    assert set(ids(r.search(q, SearchFilters(event_type="flood"), 5, 0.5))) == {"f1", "f2"}
    assert r.search(q, SearchFilters(event_type="earthquake"), 5, 0.0) == []
    assert set(ids(r.search(q, SearchFilters(admin_unit_id=3), 5, 0.5))) == {"f2"}
    assert set(ids(r.search(q, SearchFilters(date_from="2026-07-10"), 5, 0.5))) == {"f2"}
    assert set(ids(r.search(q, SearchFilters(date_to="2026-07-10"), 5, 0.5))) == {"f1"}
    assert "s1" not in ids(r.search("landslide debris", SearchFilters(date_from="2000-01-01"), 5, 0.0))      # undated never matches a date filter
    assert ids(r.search("landslide debris", SearchFilters(date_from="2000-01-01"), 5, 0.5)) == []
    assert ids(r.search("landslide debris", SearchFilters(), 5, 0.5)) == ["s1"]


def test_limit_threshold_and_degenerate_queries():
    _, _, _, r = retr()
    assert len(r.search("flood", SearchFilters(), 1, 0.0)) == 1 and r.search("flood", SearchFilters(), 0) == []
    assert r.search("", SearchFilters(), 5) == [] and r.search("   ", SearchFilters(), 5) == []
    assert r.search("market earnings", SearchFilters(), 5, min_score=0.999) != [] and r.search("flood", SearchFilters(), 5, min_score=0.999) != []
    assert r.search("totally unrelated words", SearchFilters(), 5, min_score=0.9) == []         # a threshold can produce "no useful result"


def test_results_are_deterministic_with_ties_broken_by_chunk_id():
    _, _, _, r = retr()
    a = r.search("flood", SearchFilters(), 10, 0.0)
    assert a == r.search("flood", SearchFilters(), 10, 0.0)
    tied = [h for h in a if h.score == a[0].score]
    assert [h.chunk_id for h in tied] == sorted(h.chunk_id for h in tied)


def test_vectors_from_another_model_or_version_are_never_compared():
    docs, chunks, records, emb = build()
    with pytest.raises(IncompatibleEmbeddings, match="version|stand-in"):
        SemanticRetriever(docs, chunks, records, ConceptStandIn("stand-in", "v2"))
    with pytest.raises(IncompatibleEmbeddings):
        SemanticRetriever(docs, chunks, records, ConceptStandIn("other-model", "v1"))
    bad = [dict(records[0], embedding_dimension=DIM + 1)] + records[1:]
    with pytest.raises(IncompatibleEmbeddings, match="dimension"):
        SemanticRetriever(docs, chunks, bad, emb)


def test_semantic_evidence_keeps_full_provenance_and_verbatim_text():
    docs, chunks, _, r = retr()
    hit = r.search("landslide", SearchFilters(), 1, 0.5)[0]
    chunk = next(c for c in chunks if c["chunk_id"] == hit.chunk_id)
    doc = next(d for d in docs if d["document_id"] == hit.document_id)
    e = build_evidence(hit, doc, chunk)
    assert e["document_id"] == doc["document_id"] and e["chunk_id"] == chunk["chunk_id"] and e["source"] == "ndma"
    assert e["relevance"]["relevance_type"] == "semantic_vector" and e["relevance"]["method"] == "semantic_vector"
    assert e["relevance"]["model_version"] == "v1" and e["relevance"]["matched_terms"] == []
    assert doc["raw_text"][e["snippet_document_char_start"]:e["snippet_document_char_end"]] == e["snippet"] == chunk["chunk_text"]
    assert e["document_date"] is None and e["event"]["event_types"] == ["landslide"]            # missing date stays missing
    assert e["source_reference"]["file_path"] == doc["file_path"] and e["source_reference"]["content_sha256"] == doc["content_sha256"]


def test_lexical_baseline_is_unchanged_by_the_semantic_layer():
    docs, chunks, _, _ = retr()
    lex = LexicalRetriever(docs, chunks)
    h = lex.search("river flood", SearchFilters(), 10)
    assert {x.document_id.split(":")[-1] for x in h} == {"f1", "f2"} and all(x.method == "lexical_bm25_baseline" and x.model_version is None for x in h)
    e = build_evidence(h[0], next(d for d in docs if d["document_id"] == h[0].document_id), next(c for c in chunks if c["chunk_id"] == h[0].chunk_id))
    assert e["relevance"]["relevance_type"] == "lexical_bm25_baseline" and e["relevance"]["matched_terms"]
    assert len(e["snippet"]) <= 300 or e["snippet"] == next(c for c in chunks if c["chunk_id"] == h[0].chunk_id)["chunk_text"]


def test_run_metadata_of_a_lazily_loaded_model_is_recorded_on_every_record():
    """Regression: metadata that a model only fills in when it first loads (as the real embedder does) must reach the stored records."""
    class Lazy(ConceptStandIn):
        def __init__(self):
            super().__init__()
            self.info = ModelInfo("lazy", "v1", DIM, True, {})                     # empty until first use, like FastEmbedEmbedder

        def embed_documents(self, texts):
            self.info = ModelInfo("lazy", "v1", DIM, True, {"library": "x", "weights_sha256": "abc"})
            return super().embed_documents(texts)
    chunks = [{"chunk_id": f"d#c{i:04d}", "chunk_text": "river flood", "chunk_sha256": str(i)} for i in range(3)]
    records, failures = build_embedding_records(chunks, Lazy())
    assert failures == [] and all(r["metadata"] == {"library": "x", "weights_sha256": "abc"} for r in records)
