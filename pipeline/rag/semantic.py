"""Semantic retrieval over stored chunk embeddings: cosine similarity between the query vector and chunk vectors, behind the same
`search(query, filters, limit)` contract as the lexical retriever. Pure similarity search: metadata filters narrow the candidates,
there is no hybrid scoring. Query and chunk vectors must come from the same (model_name, model_version); a mismatch is an error,
never a silent comparison of incompatible vectors.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from pipeline.rag.embeddings import Embedder
from pipeline.rag.retrieval import Hit, SearchFilters, matches

SEMANTIC_METHOD = "semantic_vector"
# Cosine similarity below this is reported as "no useful result". Calibrated on the evaluation set (see
# config/rag_semantic_eval.yaml and docs); it is a heuristic cut-off for this model, not a probability.
DEFAULT_MIN_SCORE = 0.60


class IncompatibleEmbeddings(ValueError):
    pass


class SemanticRetriever:
    method = SEMANTIC_METHOD

    def __init__(self, documents: Sequence[dict], chunks: Sequence[dict], embeddings: Sequence[dict], embedder: Embedder,
                 min_score: float = DEFAULT_MIN_SCORE):
        info = embedder.info
        self.embedder, self.min_score = embedder, min_score
        self.docs = {d["document_id"]: d for d in documents}
        by_id = {c["chunk_id"]: c for c in chunks if c["document_id"] in self.docs}
        rows = []
        for e in embeddings:
            if (e["model_name"], e["model_version"]) != (info.name, info.version):
                raise IncompatibleEmbeddings(f"stored vector for {e['chunk_id']} is from {e['model_name']}@{e['model_version']}, "
                                             f"the query embedder is {info.name}@{info.version}")
            if e["embedding_dimension"] != info.dimension or len(e["embedding"]) != info.dimension:
                raise IncompatibleEmbeddings(f"dimension mismatch for {e['chunk_id']}")
            if e["chunk_id"] in by_id:
                rows.append(e)
        rows.sort(key=lambda e: e["chunk_id"])
        self.chunks = [by_id[e["chunk_id"]] for e in rows]
        self.matrix = np.asarray([e["embedding"] for e in rows], dtype=np.float32).reshape(len(rows), info.dimension)

    def search(self, query: str, filters: SearchFilters = SearchFilters(), limit: int = 10,  # noqa: B008
               min_score: Optional[float] = None) -> list[Hit]:
        if not query or not query.strip() or limit <= 0 or not len(self.chunks):
            return []
        q = np.asarray(self.embedder.embed_query(query), dtype=np.float32)
        if q.shape != (self.embedder.info.dimension,) or not np.all(np.isfinite(q)):
            raise IncompatibleEmbeddings("query embedding has the wrong shape or non-finite values")
        sims = self.matrix @ q                                    # unit vectors: dot product == cosine similarity
        floor = self.min_score if min_score is None else min_score
        cand = []
        for i, c in enumerate(self.chunks):
            score = float(sims[i])
            if score >= floor and matches(self.docs[c["document_id"]], filters):
                cand.append((-round(score, 6), c["chunk_id"], c["document_id"]))
        cand.sort()                                               # best score first; ties broken by chunk_id (deterministic)
        v = self.embedder.info.version
        return [Hit(cid, did, -s, self.method, (), v) for s, cid, did in cand[:limit]]
