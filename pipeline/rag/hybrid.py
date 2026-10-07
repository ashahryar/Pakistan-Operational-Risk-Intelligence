"""Hybrid retrieval: Reciprocal Rank Fusion (RRF) of the lexical (BM25) and semantic (cosine) result lists, behind the same
`search(query, filters, limit)` contract as the other retrievers.

BM25 scores and cosine similarities are on unrelated scales, so scores are never added or averaged. Only ranks are fused:
    fused(chunk) = sum over the lists that returned the chunk of 1 / (k + rank)        (rank is 1-based; k = RRF_K)
A chunk found by both retrievers therefore outranks a chunk found by one at the same rank. Ties are broken by chunk_id, so the
output is fully deterministic. Parameters are fixed constants (standard RRF k=60, a candidate pool of 50 per retriever); they
were NOT tuned on the evaluation set.

Lexical side: BM25 matches any query word, so function words ("how", "to", "of") alone would pull in unrelated chunks. For the
hybrid mode only, a small fixed stop-word list is removed from the query before the BM25 call (the standalone lexical mode is
unchanged). The semantic side keeps its cosine floor (`min_score`), so an unrelated query yields no semantic candidates.
"""

from __future__ import annotations

from typing import Optional

from pipeline.rag.retrieval import STOPWORDS, Hit, LexicalRetriever, SearchFilters, tokenize
from pipeline.rag.semantic import SemanticRetriever

HYBRID_METHOD = "hybrid_rrf"
RRF_K = 60
CANDIDATE_POOL = 50

_ = STOPWORDS            # the stop-word list now lives in retrieval.py (shared with the relevance signal); re-exported here


def query_terms(query: str) -> list[str]:
    """Query words with stop words removed (used only for the lexical side of the hybrid)."""
    return [t for t in dict.fromkeys(tokenize(query)) if t not in STOPWORDS]


def rrf_fuse(lexical: list[Hit], semantic: list[Hit], k: int = RRF_K) -> list[Hit]:
    """Fuse two ranked hit lists (best first) into one list of hybrid hits, best first. Pure and deterministic."""
    lex = {h.chunk_id: (i + 1, h) for i, h in enumerate(lexical)}
    sem = {h.chunk_id: (i + 1, h) for i, h in enumerate(semantic)}
    fused = []
    for cid in set(lex) | set(sem):
        lr, lh = lex.get(cid, (None, None))
        sr, sh = sem.get(cid, (None, None))
        score = (1.0 / (k + lr) if lr else 0.0) + (1.0 / (k + sr) if sr else 0.0)
        fused.append((-round(score, 10), cid, lr, lh, sr, sh))
    fused.sort(key=lambda t: (t[0], t[1]))
    out = []
    for pos, (neg, cid, lr, lh, sr, sh) in enumerate(fused, start=1):
        base = lh or sh
        out.append(Hit(cid, base.document_id, -neg, HYBRID_METHOD, lh.matched_terms if lh else (), sh.model_version if sh else None,
                       lr, sr, lh.score if lh else None, sh.score if sh else None, pos))
    return out


class HybridRetriever:
    method = HYBRID_METHOD

    def __init__(self, lexical: LexicalRetriever, semantic: SemanticRetriever, k: int = RRF_K, pool: int = CANDIDATE_POOL):
        self.lexical, self.semantic, self.k, self.pool = lexical, semantic, k, pool
        self.docs, self.chunks = lexical.docs, lexical.chunks
        self.min_score = semantic.min_score
        self.embedder = semantic.embedder

    def search(self, query: str, filters: SearchFilters = SearchFilters(), limit: int = 10,  # noqa: B008
               min_score: Optional[float] = None) -> list[Hit]:
        if not query or not query.strip() or limit <= 0:
            return []
        pool = max(self.pool, limit)
        terms = query_terms(query)
        lex = self.lexical.search(" ".join(terms), filters, pool) if terms else []
        sem = self.semantic.search(query, filters, pool, min_score)
        return rrf_fuse(lex, sem, self.k)[:limit]
