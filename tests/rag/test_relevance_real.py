"""Task 35 -- the relevance policy on the REAL corpus (1,909 chunks), real embeddings and the frozen evaluation set (marker `real_model`; skipped without the runtime,
weights or stored embeddings, e.g. in CI). No LLM is involved. These record what was measured and make a regression visible; they do not claim the policy is optimal:
the evaluation is small, written by one author and judged by substring match."""

import pytest

from pipeline.rag import relevance as R
from pipeline.rag.embeddings import FastEmbedEmbedder
from pipeline.rag.hybrid import HybridRetriever
from pipeline.rag.retrieval import LexicalRetriever, SearchFilters
from pipeline.rag.semantic import DEFAULT_MIN_SCORE, SemanticRetriever
from tests.rag.test_embeddings_real import live

pytestmark = [pytest.mark.real_model]

KNOWN_INVALID = {"uns_capital_france", "neg_passengers_lahore"}            # 'paris' / 'passenger' DO occur in the corpus: excluded by the harness, not by hand


@pytest.fixture(scope="module")
def ev():
    from scripts.rag import evaluate_relevance as E
    cases, _ = E.load_cases()
    docs, chunks, emb, embedder = E.load_corpus(embedder=FastEmbedEmbedder()) if "embedder" in E.load_corpus.__code__.co_varnames else E.load_corpus()
    lex = LexicalRetriever(docs, chunks)
    sem = SemanticRetriever(docs, chunks, emb, embedder, DEFAULT_MIN_SCORE)
    hyb = HybridRetriever(lex, sem)
    rows = E.collect(cases, lex, sem, hyb, chunks, {d["document_id"]: d for d in docs})
    return {"E": E, "rows": rows, "lex": lex, "sem": sem, "hyb": hyb}


def row(ev, cid):
    return next(r for r in ev["rows"] if r["id"] == cid)


@live
def test_the_frozen_set_is_valid_against_the_corpus(ev):
    assert {r["id"] for r in ev["rows"] if r["invalid"]} == KNOWN_INVALID                  # every other absent term really is absent, every relevant term really present
    groups = {(r["group"], r["split"]) for r in ev["rows"] if not r["invalid"]}
    assert {("supported", "dev"), ("supported", "holdout"), ("supported", "holdout2"), ("supported", "holdout3"), ("difficult_negative", "holdout3")} <= groups


@live
@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_d4_is_no_evidence_without_a_d4_specific_rule(ev, mode):
    """Task 34 failure: 'What did NDMA report about volcanic eruptions in Sindh?' returned 5 chunks. Retrieval still returns them; the policy withholds them."""
    r = row(ev, "neg_volcano_sindh")
    assert len(r[mode]) == 5                                                              # retrieval itself is unchanged: BM25 / hybrid still find 5 keyword-overlap chunks
    assert all(a["label"] == R.LOW_RELEVANCE for a in r[mode]) and all(a["relevant"] is None for a in r[mode])
    q = r["query"]
    kept, _, summary = R.gate(mode, q, ev["lex"].search(q, SearchFilters(), 5) if mode == "lexical" else ev["hyb"].search(q, SearchFilters(), 5, DEFAULT_MIN_SCORE), ev["lex"],
                              ev["sem"].cosines)
    assert kept == [] and summary["relevance_status"] == R.NO_EVIDENCE


@live
@pytest.mark.parametrize("cid", ["neg_tsunami_karachi", "neg_avalanche_gb", "neg_election_sindh", "neg_internet_lahore",
                                 "h3_n_volcano_punjab", "h3_n_tsunami_balochistan", "h3_n_election_lahore", "h3_u_australia", "empty_hurricane", "empty_crypto"])
def test_other_unsupported_and_difficult_negative_queries_abstain_in_lexical_and_hybrid(ev, cid):
    r = row(ev, cid)
    for mode in ("lexical", "hybrid"):
        kept, answered = ev["E"].decide(mode, r[mode], R.POLICY[mode])
        assert not answered and kept == [], (cid, mode)


@live
@pytest.mark.parametrize("cid", ["neg_hurricane_relief", "neg_tornado_balochistan"])
def test_known_residual_false_positives_are_recorded_not_hidden(ev, cid):
    """The policy is not perfect: when the absent concept word carries less than half of the query's IDF weight (here 'hurricane' / 'tornado' next to several frequent
    corpus words) the question still passes. These stay answered; if the policy is improved this test should be tightened, not deleted."""
    r = row(ev, cid)
    assert ev["E"].decide("hybrid", r["hybrid"], R.POLICY["hybrid"])[1] is True


@live
@pytest.mark.parametrize("cid,mode", [("place_peshawar", "lexical"), ("place_peshawar", "hybrid"), ("province_balochistan", "hybrid"), ("district_rajanpur", "hybrid"),
                                      ("term_landslide", "lexical"), ("term_landslide", "hybrid"), ("t32_dengue", "hybrid"), ("h3_q_chitral", "hybrid"), ("h3_q_roads_bridges", "lexical")])
def test_supported_exact_and_question_form_queries_keep_relevant_evidence(ev, cid, mode):
    r = row(ev, cid)
    kept, answered = ev["E"].decide(mode, r[mode], R.POLICY[mode])
    assert answered and any(a["relevant"] for a in kept), (cid, mode)


@live
@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_fresh_question_form_holdout_recorded_result(ev, mode):
    """holdout3 was written before its scores existed. Recorded: 0/14 unsupported false positives and 0/16 false abstentions (lexical and hybrid). Small sample."""
    sub = [r for r in ev["rows"] if r["split"] == "holdout3"]
    m = ev["E"].metrics(sub, mode, R.POLICY[mode])
    b = ev["E"].metrics(sub, mode, None)
    assert b["unsupported_false_positives"] == {"lexical": "14/14", "hybrid": "13/14"}[mode]               # ungated: (almost) every unsupported question 'finds' chunks
    assert m["unsupported_false_positives"] == "0/14" and m["false_abstentions"] == "0/16" and m["abstention_accuracy"] == 1.0


@live
@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_the_gate_improves_abstention_on_the_whole_pool_within_the_evidence_loss_cap(ev, mode):
    pool = [r for r in ev["rows"] if r["split"] in ev["E"].POOL_SPLITS]
    after, before = ev["E"].metrics(pool, mode, R.POLICY[mode]), ev["E"].metrics(pool, mode, None)
    assert before["unsupported_false_positive_rate"] > 0.8 and after["unsupported_false_positive_rate"] < 0.1
    assert after["evidence_loss_rate"] <= ev["E"].MAX_EVIDENCE_LOSS and after["false_abstention_rate"] <= 0.20      # recorded: lexical 0.17, hybrid 0.14 (the cost of abstaining)
    assert after["abstention_accuracy"] > before["abstention_accuracy"] + 0.10


@live
def test_semantic_mode_gate_is_weak_and_this_is_recorded_not_hidden(ev):
    """Embedding cosine did not separate off-topic questions from supported paraphrases on this corpus: the semantic-only policy abstains on few negatives."""
    sub = [r for r in ev["rows"] if r["split"] in ev["E"].POOL_SPLITS]
    m = ev["E"].metrics(sub, "semantic", R.POLICY["semantic"])
    assert m["unsupported_false_positive_rate"] > 0.4


@live
def test_module_policy_equals_the_deterministic_selection(ev):
    E = ev["E"]
    for mode in ("lexical", "hybrid"):
        chosen, _, _ = E.select(ev["rows"], mode)
        assert chosen == R.POLICY[mode], (mode, chosen)


@live
def test_the_real_endpoints_abstain_on_d4_and_keep_supported_evidence():
    from fastapi.testclient import TestClient

    import api.app.services.rag as svc
    from api.app.main import app
    svc.set_embedder(FastEmbedEmbedder())
    svc.set_llm_provider(None)
    c = TestClient(app)
    try:
        d4 = "What did NDMA report about volcanic eruptions in Sindh?"
        s = c.get("/api/v1/rag/search", params={"q": d4, "mode": "hybrid", "limit": 5}).json()
        assert s["count"] == 5 and s["relevance_status"] == "NO_EVIDENCE" and all(e["relevance"]["assessment"]["label"] == "LOW_RELEVANCE" for e in s["results"])
        a = c.get("/api/v1/rag/ask", params={"q": d4, "mode": "hybrid"})
        assert a.status_code == 200 and a.json()["answer_status"] == "RETRIEVAL_EMPTY" and a.json()["evidence"] == [] and a.json()["model"]["called"] is False
        i = c.get("/api/v1/intelligence/ask", params={"q": "What did NDMA report about volcanic eruptions?", "mode": "hybrid"})        # no place -> no risk context either
        assert i.status_code == 200 and i.json()["status"] == "RETRIEVAL_EMPTY" and i.json()["retrieval"]["relevance"]["relevance_status"] == "NO_EVIDENCE"
        assert i.json()["model"]["called"] is False and i.json()["documentary_evidence"] == []
        i = c.get("/api/v1/intelligence/ask", params={"q": d4, "mode": "hybrid"})                    # Sindh has a risk record: the Task 32 contract still generates from it alone
        assert i.json()["documentary_evidence"] == [] and i.json()["retrieval"]["relevance"]["relevance_status"] == "NO_EVIDENCE" and i.json()["risk_context"]["status"] == "AVAILABLE"
        assert i.json()["status"] == "LLM_UNAVAILABLE" and i.json()["model"]["called"] is False         # the unavailable provider concerns the risk-only explanation, not the documents
        g = c.get("/api/v1/agent/ask", params={"q": d4, "mode": "hybrid"}).json()
        assert g["status"] == "NO_EVIDENCE" and g["documentary_evidence"] == []
        ok = c.get("/api/v1/agent/ask", params={"q": "What did NDMA report about flooding in Sindh?", "mode": "hybrid"}).json()
        assert ok["documentary_evidence"] and ok["retrieval"]["relevance"]["relevance_status"] == "RELEVANT"
    finally:
        svc.set_embedder(None)
