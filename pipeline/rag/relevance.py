"""Task 35 -- relevance / abstention policy over retrieval results (pure; no database, no network).

Retrieval always returns the best-scoring chunks it can find, including chunks that only share frequent words with the query (BM25 has no relevance floor, and
cosine similarity of an off-topic query to NDMA-style boilerplate is not zero). This module decides, from measured signals, whether a returned chunk is EVIDENCE
for the question or only LOW_RELEVANCE overlap:

  coverage       the IDF-weighted share of the query's content words that occur in the chunk (`LexicalRetriever.coverage`); a word that occurs nowhere in the
                 corpus counts as unmatched with the highest weight
  absent_share   (query level) the IDF-weighted share of the query's content words that occur in NO chunk of the corpus (`LexicalRetriever.absent_share`):
                 keyword matching cannot supply the concept those words name
  cosine         the embedding cosine similarity between the query and the chunk (`SemanticRetriever.cosines`)

Per chunk: RELEVANT or LOW_RELEVANCE (thresholds below, per retrieval mode):
  lexical   coverage >= min_coverage AND absent_share <= max_absent_share
  semantic  cosine   >= min_cosine
  hybrid    (coverage >= min_coverage AND absent_share <= max_absent_share)  OR  cosine >= min_cosine      (the lexical branch and the semantic branch each suffice)
Per query: RELEVANT when at least one chunk is RELEVANT, otherwise NO_EVIDENCE (the retrieved chunks, if any, are LOW_RELEVANCE and are withheld from evidence).
The ranking itself (BM25, cosine, deterministic RRF) is never changed; the gate only classifies the ranked list, and metadata filters are applied before ranking
exactly as before, so the gate can never add, widen or remove a geography / source / date constraint.

THE THRESHOLDS ARE NOT TUNED BY HAND: `scripts/rag/evaluate_relevance.py --select` chooses them deterministically on the frozen evaluation set
(config/rag_relevance_eval.yaml) and the final policy is reported once on a fresh holdout; the report also states whether these constants equal the selection.
They are calibrated for this corpus and this embedding model (BAAI/bge-small-en-v1.5), they are heuristics and not probabilities, and they are not claimed to be
valid for another corpus or model. In particular embedding cosine did NOT separate off-topic questions from supported paraphrases on this corpus (see
docs/architecture/RAG_RELEVANCE_STATUS.md): no claim of semantic understanding is made.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from pipeline.rag.retrieval import Hit, LexicalRetriever

POLICY_VERSION = "relevance-1.2.0"
EVAL_DEPTH = 5            # the policy was evaluated on the top-5 of the ranked list: the query-level decision looks at the first EVAL_DEPTH results
RELEVANT = "RELEVANT"
LOW_RELEVANCE = "LOW_RELEVANCE"
NO_EVIDENCE = "NO_EVIDENCE"

# Selected by `python scripts/rag/evaluate_relevance.py --select` (see data/analytics/rag/relevance_eval_report.json). A key that is absent disables that signal.
POLICY = {
    "lexical": {"min_coverage": 0.25, "max_absent_share": 0.5},
    "semantic": {"min_cosine": 0.63},                                              # embedding cosine did not separate off-topic from supported queries: this gate is weak
    "hybrid": {"min_coverage": 0.0, "max_absent_share": 0.5, "rule": "or"},       # selected: the query-level absent-word share decides; the cosine branch was not selected
}


def _lexical_ok(p: dict, coverage: Optional[float], absent_share: Optional[float]) -> bool:
    if "min_coverage" not in p or coverage is None or coverage < p["min_coverage"]:
        return False
    return absent_share is None or absent_share <= p.get("max_absent_share", 1.0)


def _semantic_ok(p: dict, cosine: Optional[float]) -> bool:
    return "min_cosine" in p and cosine is not None and cosine >= p["min_cosine"]


def chunk_passes(mode: str, coverage: Optional[float], cosine: Optional[float], policy: Optional[dict] = None, absent_share: Optional[float] = None) -> bool:
    """Whether one chunk's signals pass the policy of the retrieval mode."""
    p = (policy or POLICY)[mode]
    if mode == "lexical":
        return _lexical_ok(p, coverage, absent_share)
    if mode == "semantic":
        return _semantic_ok(p, cosine)
    if mode == "hybrid":
        lex, sem = _lexical_ok(p, coverage, absent_share), _semantic_ok(p, cosine)
        return (lex and sem) if p.get("rule") == "and" else (lex or sem)
    raise ValueError(f"unknown retrieval mode {mode!r}")


def assess_hits(mode: str, query: str, hits: Sequence[Hit], lexical: LexicalRetriever, cosines_fn: Optional[Callable[[str, list], dict]] = None,
                policy: Optional[dict] = None) -> list[dict]:
    """One assessment per hit, in the hits' order: {chunk_id, label, coverage, absent_share, cosine}. `cosines_fn(query, chunk_ids)` is required for semantic / hybrid."""
    cos = cosines_fn(query, [h.chunk_id for h in hits]) if (mode in ("semantic", "hybrid") and hits) else {}
    share = lexical.absent_share(query) if hits else 0.0
    out = []
    for h in hits:
        coverage = lexical.coverage(query, h.chunk_id)
        cosine = cos.get(h.chunk_id)
        out.append({"chunk_id": h.chunk_id, "coverage": coverage, "absent_share": share, "cosine": cosine,
                    "label": RELEVANT if chunk_passes(mode, coverage, cosine, policy, share) else LOW_RELEVANCE})
    return out


def summarize(mode: str, assessments: Sequence[dict], policy: Optional[dict] = None) -> dict:
    """The query-level outcome. NO_EVIDENCE is decided by the signals, not by the number of results."""
    relevant = [a for a in assessments if a["label"] == RELEVANT]
    low = [a for a in assessments if a["label"] != RELEVANT]
    if relevant:
        reason = None
    elif low:
        cos = [a["cosine"] for a in low if a["cosine"] is not None]
        reason = (f"{len(low)} retrieved chunk(s) shared words with the question but none passed the relevance check "
                  f"(best query-word coverage {max(a['coverage'] for a in low):.2f}, share of query words absent from the corpus {low[0]['absent_share']:.2f}"
                  + (f", best embedding similarity {max(cos):.2f}" if cos else "") + ")")
    else:
        reason = "no chunk matched the question and filters"
    return {"relevance_status": RELEVANT if relevant else NO_EVIDENCE, "abstained": not relevant, "abstention_reason": reason, "relevant_count": len(relevant),
            "low_relevance_count": len(low), "policy": {"version": POLICY_VERSION, "mode": mode, **(policy or POLICY)[mode]}}


def gate(mode: str, query: str, hits: Sequence[Hit], lexical: LexicalRetriever, cosines_fn: Optional[Callable[[str, list], dict]] = None,
         policy: Optional[dict] = None) -> tuple[list[Hit], list[dict], dict]:
    """Classify ranked hits. -> (relevant hits in the original order, assessments of every hit, query-level summary).
    The query is RELEVANT when one of the first EVAL_DEPTH results passes (the evaluated decision); then every passing hit is evidence. Otherwise NO_EVIDENCE:
    no hit is evidence, whatever the number of results."""
    ass = assess_hits(mode, query, hits, lexical, cosines_fn, policy)
    summary = summarize(mode, ass[:EVAL_DEPTH] if any(a["label"] == RELEVANT for a in ass[:EVAL_DEPTH]) else ass, policy)
    if summary["abstained"]:
        return [], ass, {**summary, "relevant_count": 0, "low_relevance_count": len(ass)}
    keep = [h for h, a in zip(hits, ass) if a["label"] == RELEVANT]
    return keep, ass, {**summary, "relevant_count": len(keep), "low_relevance_count": len(ass) - len(keep)}
