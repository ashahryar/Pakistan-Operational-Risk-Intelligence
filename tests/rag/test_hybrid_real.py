"""Task 31 -- REAL-MODEL tests for hybrid retrieval and the grounded-answer API on the real local corpus (marker `real_model`).
Skipped without the embedding runtime/weights/stored embeddings (CI). No LLM is involved: a scripted provider stands in where the
endpoint needs one, so these check retrieval, evidence selection and citation validation on real chunks -- not model answer quality.
The assertions record honest findings, including where hybrid is NOT better (see docs)."""

import pytest

from pipeline.rag.embeddings import FastEmbedEmbedder
from tests.rag.test_embeddings_real import live

pytestmark = [pytest.mark.real_model]


@pytest.fixture(scope="module")
def embedder():
    return FastEmbedEmbedder()


@pytest.fixture(scope="module")
def evaluation(embedder):
    from scripts.rag.evaluate_semantic import run
    return run(embedder=embedder)


def case(report, cid):
    return next(c for c in report["cases"] if c["id"] == cid)


@live
def test_evaluation_set_keeps_the_16_original_cases_and_adds_the_task31_categories(evaluation):
    s = evaluation["summary"]
    assert s["cases_total"] == 46 and s["cases_task30_original"] == 16
    cats = {c["category"] for c in evaluation["cases"]}
    assert {"exact_place", "district", "province", "disaster_term", "paraphrase", "advisory_lang", "casualty", "infrastructure", "empty"} <= cats
    assert [c["id"] for c in evaluation["cases"][:3]] == ["slope_collapse", "rivers_bursting", "scorching_heat"]


@live
def test_hybrid_recovers_the_swat_exact_name_that_semantic_search_misses(evaluation):
    c = case(evaluation, "geo_swat")
    assert c["semantic"]["relevant"] == 0 and c["lexical"]["precision_at_k"] == 1.0
    assert c["hybrid"]["relevant"] >= 1                                                       # found through the BM25 side
    g = evaluation["summary"]["groups"]["exact_entity"]["mean_precision_at_k"]
    assert g["hybrid"] > g["semantic"]


@live
def test_hybrid_is_not_uniformly_better_and_the_report_says_where_it_loses(evaluation):
    s = evaluation["summary"]
    worse = set(s["cases_where_hybrid_is_worse_than_the_better_single_method"])
    assert {"geo_swat", "lives_lost", "scorching_heat"} <= worse                              # known losses are recorded, not hidden
    assert s["paraphrase_mean_precision_at_k"]["semantic"] > s["paraphrase_mean_precision_at_k"]["hybrid"]
    g = s["groups"]["exact_entity"]["mean_precision_at_k"]
    assert g["lexical"] >= g["hybrid"]


@live
def test_hybrid_inherits_keyword_junk_on_some_unsupported_queries_semantic_does_not(evaluation):
    u = evaluation["summary"]["unsupported_cases"]
    assert u["results_returned_total"]["semantic"] < u["results_returned_total"]["hybrid"] < u["results_returned_total"]["lexical"]
    assert evaluation["summary"]["filters_respected_everywhere"] is True


@live
def test_hybrid_results_expose_both_ranks_for_a_query_both_methods_find(embedder):
    from pipeline.rag.hybrid import HybridRetriever
    from pipeline.rag.retrieval import LexicalRetriever, SearchFilters
    from pipeline.rag.semantic import SemanticRetriever
    from scripts.rag.evaluate_semantic import load_corpus
    docs, chunks, emb, embedder = load_corpus(None, embedder)
    hyb = HybridRetriever(LexicalRetriever(docs, chunks), SemanticRetriever(docs, chunks, emb, embedder))
    hits = hyb.search("landslide blocked road", SearchFilters(), 10)
    assert hits and hits == hyb.search("landslide blocked road", SearchFilters(), 10)
    assert any(h.lexical_rank and h.semantic_rank for h in hits)
    assert [h.fused_rank for h in hits] == list(range(1, len(hits) + 1)) and all(h.score > 0 for h in hits)


@live
def test_ask_endpoint_end_to_end_with_real_retrieval_and_a_scripted_provider(embedder):
    from fastapi.testclient import TestClient

    import api.app.services.rag as svc
    from api.app.main import app
    from pipeline.rag.llm import LLMResult

    class Scripted:
        name, model = "scripted", "s-1"

        def generate(self, system, question, evidence, constraints):
            top = evidence[0]
            claim = " ".join(top["text"].split())[:120].rsplit(" ", 1)[0].rstrip(".")
            return LLMResult(f"The report states: {claim} [chunk:{top['chunk_id']}].", self.name, self.model)

    svc.set_embedder(embedder)
    svc.set_llm_provider(Scripted())
    try:
        c = TestClient(app)
        b = c.get("/api/v1/rag/ask", params={"q": "What was reported about Swat?", "top_k": 3}).json()
        assert b["retrieval"]["mode"] == "hybrid" and len(b["evidence"]) <= 3
        assert b["answer_status"] in ("ANSWERED", "INVALID_ANSWER")        # the scripted claim is a raw chunk excerpt; either is a valid pipeline outcome
        assert {x["chunk_id"] for x in b["citations"]} <= {e["chunk_id"] for e in b["evidence"]}
        assert any("swat" in e["snippet"].lower() for e in b["evidence"])
        assert all(e["source_reference"]["file_path"] or e["source_reference"]["url"] for e in b["evidence"])
        e = c.get("/api/v1/rag/ask", params={"q": "how to bake a chocolate cake", "mode": "semantic"}).json()
        assert e["answer_status"] == "RETRIEVAL_EMPTY" and e["evidence"] == []
        svc.set_llm_provider(None)
        assert c.get("/api/v1/rag/ask", params={"q": "What was reported about Swat?"}).status_code == 503
    finally:
        svc.set_embedder(None)
        svc.set_llm_provider(None)
