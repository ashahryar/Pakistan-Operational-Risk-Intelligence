"""Task 31 -- UNIT tests for hybrid retrieval (reciprocal rank fusion of BM25 and semantic results).

Uses the TEST-ONLY `ConceptStandIn` embedder from test_embeddings_unit, so these tests prove the fusion LOGIC (ranks, ties, provenance
fields, determinism, the exact-name / paraphrase behaviour the fusion is meant to give) and nothing about real model quality. Real
behaviour is measured by scripts/rag/evaluate_semantic.py on the actual corpus.
"""

import pytest

from pipeline.rag.chunking import chunk_document
from pipeline.rag.embeddings import build_embedding_records
from pipeline.rag.hybrid import CANDIDATE_POOL, HYBRID_METHOD, RRF_K, HybridRetriever, query_terms, rrf_fuse
from pipeline.rag.retrieval import Hit, LexicalRetriever, SearchFilters
from pipeline.rag.semantic import SemanticRetriever
from tests.rag.test_embeddings_unit import ConceptStandIn, make_doc


def H(cid, score=1.0, method="x", terms=()):
    return Hit(cid, "doc:" + cid, score, method, terms)


# ------------------------------------------------------------------ rank fusion (pure)
def test_rrf_scores_are_sums_of_reciprocal_ranks_and_fields_are_exposed():
    out = rrf_fuse([H("A", 9.0, terms=("a",)), H("B", 5.0, terms=("b",))], [H("B", 0.9), H("C", 0.7)])
    assert [h.chunk_id for h in out] == ["B", "A", "C"]
    b, a, c = out
    assert b.score == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert a.score == pytest.approx(1 / (RRF_K + 1)) and c.score == pytest.approx(1 / (RRF_K + 2))
    assert (b.lexical_rank, b.semantic_rank, b.fused_rank) == (2, 1, 1)
    assert (a.lexical_rank, a.semantic_rank, a.fused_rank) == (1, None, 2)          # lexical-only result
    assert (c.lexical_rank, c.semantic_rank, c.fused_rank) == (None, 2, 3)          # semantic-only result
    assert (b.lexical_score, b.semantic_score) == (5.0, 0.9) and a.semantic_score is None and c.lexical_score is None
    assert all(h.method == HYBRID_METHOD for h in out) and a.matched_terms == ("a",) and c.matched_terms == ()


def test_a_chunk_found_by_both_lists_outranks_single_list_chunks_at_equal_rank():
    out = rrf_fuse([H("A"), H("B")], [H("C"), H("B")])
    assert out[0].chunk_id == "B"                                                  # rank 2 in both beats rank 1 in one only


def test_ties_break_by_chunk_id_and_output_is_deterministic():
    a, b = [H("Z"), H("Y")], [H("X")]
    first = rrf_fuse(a, b)
    assert [h.chunk_id for h in first] == ["X", "Z", "Y"]                          # X and Z tie at 1/61 -> chunk_id order
    assert [h.chunk_id for h in rrf_fuse([H("B")], [H("A")])] == ["A", "B"]         # equal scores -> chunk_id order
    assert rrf_fuse(a, b) == first and rrf_fuse(list(a), list(b)) == first


def test_empty_inputs():
    assert rrf_fuse([], []) == []
    assert [h.chunk_id for h in rrf_fuse([H("A")], [])] == ["A"] and [h.chunk_id for h in rrf_fuse([], [H("A")])] == ["A"]


def test_k_is_configurable():
    out = rrf_fuse([H("A")], [], k=10)
    assert out[0].score == pytest.approx(1 / 11)


def test_stopwords_are_removed_for_the_lexical_side_only():
    assert query_terms("How to bake a chocolate cake") == ["bake", "chocolate", "cake"]
    assert query_terms("what happened in Swat") == ["happened", "swat"]
    assert query_terms("the of and") == []


# ------------------------------------------------------------------ the retriever over a small corpus
def corpus():
    emb = ConceptStandIn()
    docs = [make_doc("d1", "River overflow caused inundation in the Swat valley."),
            make_doc("d2", "Flood waters entered the town after the river rose."),
            make_doc("d3", "Scorching temperature and heatwave across the plains.", source="pdma", source_type="daily_report"),
            make_doc("d4", "Officials visited Swat and reported a road closure.")]
    chunks = [c for d in docs for c in chunk_document(d)]
    recs, failed = build_embedding_records(chunks, emb)
    assert not failed
    ids = {d["document_id"].split(":")[-1]: c["chunk_id"] for d in docs for c in chunks if c["document_id"] == d["document_id"]}
    lex = LexicalRetriever(docs, chunks)
    sem = SemanticRetriever(docs, chunks, recs, emb, 0.5)
    return HybridRetriever(lex, sem), lex, sem, ids


def test_exact_entity_query_is_found_lexically_even_where_semantic_misses_it():
    hyb, lex, sem, ids = corpus()
    got = {h.chunk_id: h for h in hyb.search("Swat", limit=10)}
    assert set(got) == {ids["d1"], ids["d4"]}
    assert got[ids["d4"]].lexical_rank and got[ids["d4"]].semantic_rank                # found by both
    assert got[ids["d1"]].lexical_rank and got[ids["d1"]].semantic_rank is None        # lexical-only: semantic (stand-in) does not know "swat"
    assert [h.chunk_id for h in sem.search("Swat", limit=10)] == [ids["d4"]]            # semantic alone misses d1
    assert next(iter(got)) == ids["d4"]                                                 # the shared result ranks first


def test_paraphrase_query_is_found_semantically_where_lexical_has_no_match():
    hyb, lex, sem, ids = corpus()
    assert lex.search("inundation", limit=10)[0].chunk_id == ids["d1"] and len(lex.search("inundation", limit=10)) == 1
    got = {h.chunk_id: h for h in hyb.search("inundation", limit=10)}
    assert set(got) == {ids["d1"], ids["d2"]}
    assert got[ids["d2"]].lexical_rank is None and got[ids["d2"]].semantic_rank is not None       # semantic-only result
    assert got[ids["d1"]].lexical_rank == 1                                                       # shared result


def test_filters_apply_to_both_sides():
    hyb, _, _, ids = corpus()
    assert {h.chunk_id for h in hyb.search("Swat", SearchFilters(source="pdma"), 10)} == set()
    assert [h.chunk_id for h in hyb.search("scorching", SearchFilters(source="pdma"), 10)] == [ids["d3"]]


def test_unrelated_query_returns_nothing_and_limit_is_respected():
    hyb, _, _, ids = corpus()
    assert hyb.search("zebra giraffe", limit=5, min_score=1.01) == []                # no keyword match and nothing above the cosine floor
    assert len(hyb.search("river", limit=1)) == 1
    assert hyb.search("", limit=5) == [] and hyb.search("   ", limit=5) == [] and hyb.search("river", limit=0) == []


def test_search_is_deterministic_and_min_score_reaches_the_semantic_side():
    hyb, _, _, ids = corpus()
    a = hyb.search("inundation", limit=10)
    assert a == hyb.search("inundation", limit=10)
    assert {h.chunk_id for h in hyb.search("inundation", limit=10, min_score=0.999)} == {ids["d1"], ids["d2"]}      # stand-in cosine is 1.0
    strict = hyb.search("inundation", limit=10, min_score=1.01)
    assert all(h.semantic_rank is None for h in strict) and {h.chunk_id for h in strict} == {ids["d1"]}              # only the lexical match remains


def test_pool_constant_and_candidate_limit():
    hyb, *_ = corpus()
    assert CANDIDATE_POOL == 50 and hyb.pool == 50 and hyb.k == 60
