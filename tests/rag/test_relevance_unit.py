"""Task 35 -- the relevance / abstention policy as pure logic: signals (coverage, absent-word share, cosine), the per-mode chunk decision, the query-level gate,
and the safety properties (the gate only classifies: it never adds, reorders or fabricates a result, never touches filters, never needs geography)."""

import random
import re
from pathlib import Path

import pytest

from pipeline.rag import relevance as R
from pipeline.rag.retrieval import FRAMING_WORDS, STOPWORDS, Hit, LexicalRetriever, SearchFilters, content_terms, signal_terms
from tests.rag.test_embeddings_unit import build

POLICY = {"lexical": {"min_coverage": 0.25, "max_absent_share": 0.5}, "semantic": {"min_cosine": 0.63}, "hybrid": {"min_coverage": 0.0, "max_absent_share": 0.5, "rule": "or"}}


@pytest.fixture(scope="module")
def lex():
    docs, chunks, _, _ = build()
    return LexicalRetriever(docs, chunks)


def hit(chunk, doc="d", score=1.0, method="lexical_bm25_baseline"):
    return Hit(chunk, doc, score, method, ())


# ---------------------------------------------------------------------------------------------------------------------------------- signals
def test_content_and_signal_terms():
    assert content_terms("What did NDMA report about volcanic eruptions in Sindh?") == ["ndma", "report", "about", "volcanic", "eruptions", "sindh"]
    assert signal_terms("What did NDMA report about volcanic eruptions in Sindh?") == ["volcanic", "eruptions", "sindh"]        # framing words and agency names are not topics
    assert signal_terms("what reported about") == content_terms("what reported about") == ["reported", "about"]                 # a question made only of framing words keeps them: never an empty signal
    assert signal_terms("the of and") == []                                                                                      # only stop words: nothing to measure
    assert STOPWORDS < frozenset(STOPWORDS | FRAMING_WORDS) and not (STOPWORDS & {"flood", "rain", "landslide"}) and not (FRAMING_WORDS & {"flood", "rain", "landslide", "dengue"})


def test_coverage_is_the_idf_weighted_share_of_topic_words_in_the_chunk(lex):
    c = next(c["chunk_id"] for c in lex.chunks if "river overflow" in c["chunk_text"].lower())
    assert lex.coverage("river overflow", c) == 1.0
    assert 0.0 < lex.coverage("river heatwave", c) < 1.0                                  # one of two topic words
    assert lex.coverage("bitcoin price", c) == 0.0
    assert lex.coverage("river overflow", "no-such-chunk") == 0.0
    assert lex.coverage("", c) == 0.0
    assert lex.coverage("What did NDMA report about river overflow?", c) == 1.0           # framing words do not dilute the signal


def test_absent_share_is_the_idf_weighted_share_of_words_that_occur_nowhere(lex):
    assert lex.absent_share("river overflow") == 0.0
    assert lex.absent_share("volcanic eruptions") == 1.0
    assert 0.0 < lex.absent_share("river volcanic") < 1.0
    assert lex.absent_share("") == 0.0
    # a word absent from the corpus has the highest possible weight, so one absent concept word outweighs several present ones
    assert lex.absent_share("river overflow inundation volcanic") > lex.absent_share("river overflow inundation") == 0.0


# ----------------------------------------------------------------------------------------------------------------------------- chunk decision
@pytest.mark.parametrize("mode,cov,cos,absent,expected", [
    ("lexical", 0.30, None, 0.0, True), ("lexical", 0.24, None, 0.0, False), ("lexical", 0.90, None, 0.6, False), ("lexical", 0.90, None, 0.5, True),
    ("semantic", None, 0.63, None, True), ("semantic", None, 0.62, None, False), ("semantic", 0.99, None, 0.0, False),
    ("hybrid", 0.0, None, 0.5, True), ("hybrid", 0.9, None, 0.51, False), ("hybrid", 0.0, 0.99, 0.51, False),            # selected policy: the query-level absent share decides
])
def test_chunk_decision_per_mode(mode, cov, cos, absent, expected):
    assert R.chunk_passes(mode, cov, cos, POLICY, absent) is expected


def test_hybrid_or_and_rules_and_disabled_signals():
    both = {"hybrid": {"min_coverage": 0.3, "min_cosine": 0.7, "rule": "or"}}
    assert R.chunk_passes("hybrid", 0.4, 0.1, both, 0.0) and R.chunk_passes("hybrid", 0.0, 0.8, both, 0.0) and not R.chunk_passes("hybrid", 0.2, 0.6, both, 0.0)
    both_and = {"hybrid": {"min_coverage": 0.3, "min_cosine": 0.7, "rule": "and"}}
    assert R.chunk_passes("hybrid", 0.4, 0.8, both_and, 0.0) and not R.chunk_passes("hybrid", 0.4, 0.6, both_and, 0.0)
    assert not R.chunk_passes("hybrid", 0.9, 0.9, {"hybrid": {}}, 0.0)                    # no threshold configured = nothing passes (a missing signal is never a free pass)
    assert not R.chunk_passes("lexical", None, None, POLICY, 0.0)
    with pytest.raises(ValueError):
        R.chunk_passes("bm25", 1, 1, {"bm25": {}})


# ------------------------------------------------------------------------------------------------------------------------------------ the gate
def test_supported_query_is_relevant_and_keeps_the_ranking(lex):
    q = "river overflow inundation"
    hits = lex.search(q, SearchFilters(), 5)
    kept, ass, summary = R.gate("lexical", q, hits, lex, None, POLICY)
    assert hits and kept == [h for h, a in zip(hits, ass) if a["label"] == R.RELEVANT] and kept and [h.chunk_id for h in kept] == [h.chunk_id for h in hits if h in kept]
    assert summary["relevance_status"] == R.RELEVANT and summary["abstained"] is False and summary["abstention_reason"] is None
    assert summary["relevant_count"] == len(kept) and summary["policy"]["mode"] == "lexical" and summary["policy"]["version"] == R.POLICY_VERSION


def test_no_evidence_is_decided_by_the_signals_not_by_the_number_of_results(lex):
    q = "What did NDMA report about volcanic eruptions in Sindh?"
    hits = lex.search(q, SearchFilters(), 5)
    assert hits                                                                           # BM25 does return chunks for the frequent words
    kept, ass, summary = R.gate("lexical", q, hits, lex, None, POLICY)
    assert kept == [] and summary["relevance_status"] == R.NO_EVIDENCE and summary["abstained"] is True
    assert summary["low_relevance_count"] == len(hits) and summary["relevant_count"] == 0 and all(a["label"] == R.LOW_RELEVANCE for a in ass)
    assert "none passed the relevance check" in summary["abstention_reason"] and "absent from the corpus" in summary["abstention_reason"]


def test_an_empty_result_is_also_no_evidence_with_its_own_reason(lex):
    kept, ass, summary = R.gate("lexical", "bitcoin", [], lex, None, POLICY)
    assert kept == [] and ass == [] and summary["relevance_status"] == R.NO_EVIDENCE and summary["abstention_reason"] == "no chunk matched the question and filters"


def test_the_decision_looks_at_the_evaluated_depth_only(lex):
    chunks = [c["chunk_id"] for c in lex.chunks][:6]
    hits = [hit(c) for c in chunks]
    flags = iter([False] * R.EVAL_DEPTH + [True])
    from unittest import mock
    with mock.patch.object(R, "chunk_passes", side_effect=lambda *a, **k: next(flags)):
        kept, _, summary = R.gate("lexical", "x", hits, lex, None, POLICY)
    assert kept == [] and summary["abstained"] is True                                    # a relevant chunk beyond the evaluated top-5 does not rescue the query


@pytest.mark.parametrize("seed", range(20))
def test_gate_never_adds_reorders_or_fabricates(lex, seed):
    """Property: the kept hits are a sub-sequence of the input hits (same objects, same order); assessments align one-to-one with the input."""
    rng = random.Random(seed)
    ids = [c["chunk_id"] for c in lex.chunks]
    hits = [hit(rng.choice(ids), score=rng.random()) for _ in range(rng.randint(0, 12))]
    q = rng.choice(["river overflow", "volcanic eruption sindh", "heatwave plains", "landslide slope road", "zzz qqq", ""])
    kept, ass, summary = R.gate("lexical", q, hits, lex, None, POLICY)
    assert len(ass) == len(hits) and [a["chunk_id"] for a in ass] == [h.chunk_id for h in hits]
    it = iter(hits)
    assert all(any(k is h for h in it) for k in kept)                                    # sub-sequence by identity
    assert summary["relevant_count"] == len(kept) and summary["abstained"] == (not kept)


def test_semantic_and_hybrid_need_a_cosine_function_but_lexical_does_not(lex):
    hits = lex.search("river overflow", SearchFilters(), 3)
    seen = {}

    def cosines(q, ids):
        seen["args"] = (q, list(ids))
        return {i: 0.9 for i in ids}
    kept, ass, _ = R.gate("semantic", "river overflow", hits, lex, cosines, {"semantic": {"min_cosine": 0.63}})
    assert seen["args"][0] == "river overflow" and len(kept) == len(hits) and all(a["cosine"] == 0.9 for a in ass)
    seen.clear()
    R.gate("lexical", "river overflow", hits, lex, cosines, POLICY)
    assert not seen                                                                       # lexical never embeds anything


def test_the_gate_is_deterministic(lex):
    q = "river overflow volcanic"
    hits = lex.search(q, SearchFilters(), 5)
    runs = [R.gate("lexical", q, hits, lex, None, POLICY) for _ in range(5)]
    assert all(r[1] == runs[0][1] and r[2] == runs[0][2] for r in runs)


# ----------------------------------------------------------------------------------------------------------------------------- safety / scope
ROOT = Path(__file__).resolve().parents[2]


def test_the_relevance_module_has_no_geography_database_network_or_model_dependency():
    src = (ROOT / "pipeline" / "rag" / "relevance.py").read_text(encoding="utf-8")
    imports = set(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M))
    assert imports <= {"__future__", "typing", "pipeline.rag.retrieval"}, imports        # no scripts.geo, no pipeline.intelligence, no sqlalchemy, no numpy, no model
    assert "matches(" not in src and "SearchFilters" not in src                         # it never builds or alters a metadata filter


def test_the_retrieval_signals_use_no_geography_resolution():
    src = (ROOT / "pipeline" / "rag" / "retrieval.py").read_text(encoding="utf-8")
    assert "scripts.geo" not in src and "difflib" not in src and "fuzzy" not in src.lower().replace("no fuzzy", "")


def test_the_bm25_ranking_is_unchanged_by_the_new_signals(lex):
    """coverage / absent_share are read-only: searching before and after calling them gives the identical ranked list."""
    before = lex.search("river overflow inundation", SearchFilters(), 5)
    for c in lex.chunks:
        lex.coverage("river overflow", c["chunk_id"])
        lex.absent_share("river volcanic")
    assert lex.search("river overflow inundation", SearchFilters(), 5) == before
