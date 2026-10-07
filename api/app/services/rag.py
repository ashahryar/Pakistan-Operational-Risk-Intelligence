"""Task 29 -- read-only access to the RAG corpus (rag.documents / rag.document_chunks) and evidence search.

Ranking is the deterministic lexical baseline in pipeline/rag/retrieval.py (keyword BM25, NOT semantic search). The
retriever is held in a small in-process cache keyed by the corpus version (document count + latest load time), so it is
rebuilt only after a new corpus load. No text is generated; results are evidence records.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from typing import Optional

from api.app.db import fetch_all
from pipeline.rag.contracts import RETRIEVAL_METHOD
from pipeline.rag.evidence import build_evidence
from pipeline.rag.retrieval import LexicalRetriever, SearchFilters

_DOC_META = """document_id, source, source_type, title, document_date, document_date_text, document_date_basis, published_at, url, file_path,
               province, admin_unit_id, admin_unit_name, provinces, districts, admin_unit_ids, geography_status, geography_basis,
               geography_text, event_type, event_types, event_type_raw, language_script, content_sha256, metadata,
               ingestion_timestamp, parser_version, normalization_version"""

_cache: dict = {"token": None, "retriever": None}
_lock = threading.Lock()


def _iso(row: dict) -> dict:
    d = dict(row)
    if isinstance(d.get("document_date"), date):
        d["document_date"] = d["document_date"].isoformat()
    return d


def corpus_token() -> tuple:
    r = fetch_all("SELECT count(*) AS n, max(loaded_at) AS t FROM rag.documents WHERE is_current")[0]
    return (r["n"], str(r["t"]))


def get_retriever() -> LexicalRetriever:
    token = corpus_token()
    with _lock:
        if _cache["token"] != token or _cache["retriever"] is None:
            docs = [_iso(r) for r in fetch_all(f"SELECT {_DOC_META} FROM rag.documents WHERE is_current ORDER BY document_id")]
            chunks = fetch_all("SELECT c.chunk_id, c.document_id, c.chunk_index, c.char_start, c.char_end, c.chunk_text "
                               "FROM rag.document_chunks c JOIN rag.documents d USING (document_id) "
                               "WHERE c.is_current AND d.is_current ORDER BY c.chunk_id")
            _cache.update(token=token, retriever=LexicalRetriever(docs, chunks))
        return _cache["retriever"]


class SemanticUnavailable(Exception):
    """Semantic retrieval cannot run in this deployment (runtime/weights missing, or no stored embeddings)."""


_embedder = None
_sem_cache: dict = {"token": None, "retriever": None}


def set_embedder(embedder) -> None:
    """Inject the query embedder (tests / alternative deployments). Must be the model that produced the stored vectors."""
    global _embedder
    _embedder = embedder
    _sem_cache.update(token=None, retriever=None)


def get_embedder():
    global _embedder
    if _embedder is None:
        from pipeline.rag.embeddings import FastEmbedEmbedder, runtime_available
        if not runtime_available():
            raise SemanticUnavailable("the embedding runtime is not installed in this deployment (see requirements/embeddings.txt)")
        _embedder = FastEmbedEmbedder()
    return _embedder


def get_semantic_retriever():
    from pipeline.rag.embeddings import EmbeddingUnavailable
    embedder = get_embedder()                       # raises SemanticUnavailable first when the runtime is not installed
    from pipeline.rag.semantic import DEFAULT_MIN_SCORE, IncompatibleEmbeddings, SemanticRetriever
    info = embedder.info
    stats = fetch_all("SELECT count(*) AS n, max(created_at) AS t FROM rag.chunk_embeddings WHERE model_name = :m AND model_version = :v",
                      {"m": info.name, "v": info.version})[0]
    if not stats["n"]:
        raise SemanticUnavailable(f"no embeddings are stored for {info.name}@{info.version} (run scripts/rag/embed_chunks.py)")
    lexical = get_retriever()
    token = (corpus_token(), stats["n"], str(stats["t"]), info.name, info.version)
    with _lock:
        if _sem_cache["token"] != token or _sem_cache["retriever"] is None:
            rows = fetch_all("SELECT e.chunk_id, e.model_name, e.model_version, e.embedding_dimension, e.embedding "
                             "FROM rag.chunk_embeddings e JOIN rag.document_chunks c USING (chunk_id) JOIN rag.documents d USING (document_id) "
                             "WHERE e.model_name = :m AND e.model_version = :v AND c.is_current AND d.is_current "
                             "AND e.chunk_sha256 = c.chunk_sha256 ORDER BY e.chunk_id", {"m": info.name, "v": info.version})
            if not rows:
                raise SemanticUnavailable(f"stored embeddings for {info.name}@{info.version} do not match the current chunks")
            try:
                retriever = SemanticRetriever(list(lexical.docs.values()), lexical.chunks, rows, embedder, DEFAULT_MIN_SCORE)
            except (IncompatibleEmbeddings, EmbeddingUnavailable) as exc:
                raise SemanticUnavailable(str(exc)) from exc
            _sem_cache.update(token=token, retriever=retriever)
        return _sem_cache["retriever"], lexical


# ---------------------------------------------------------------------------------------------------- Task 35: relevance gate
def _cosines_fn(retriever):
    """The cosine function of a semantic / hybrid retriever (None for lexical)."""
    fn = getattr(retriever, "cosines", None)
    if fn is None and getattr(retriever, "semantic", None) is not None:
        fn = retriever.semantic.cosines
    return fn


def _gate(mode: str, q: str, hits, retriever, lexical):
    from pipeline.rag import relevance
    return relevance.gate(mode, q, hits, lexical, _cosines_fn(retriever))


def _relevance_block(summary: dict, assessments: list) -> dict:
    """The relevance decision of a retrieval, for the ask / intelligence / agent responses. Withheld (low-relevance) chunks are listed by id and signals only,
    never as evidence."""
    return {**summary, "withheld_chunks": [{"chunk_id": a["chunk_id"], "coverage": a["coverage"], "cosine": a["cosine"]} for a in assessments if a["label"] != "RELEVANT"][:10]}


def _annotate(results: list, assessments: list, summary: dict, only_relevant: bool) -> dict:
    """Backward-compatible additions to a search response: every result gets `relevance.assessment`; the response gets the query-level decision.
    Results are not removed unless the caller asks (`only_relevant`)."""
    for r, a in zip(results, assessments):
        r["relevance"]["assessment"] = {"label": a["label"], "coverage": a["coverage"], "absent_share": a["absent_share"], "cosine": a["cosine"]}
    kept = [r for r in results if r["relevance"]["assessment"]["label"] == "RELEVANT"] if only_relevant else results
    return {"results": kept, "count": len(kept), "relevance_status": summary["relevance_status"], "abstained": summary["abstained"],
            "abstention_reason": summary["abstention_reason"], "relevance_policy": summary["policy"]}


def search_semantic_evidence(q: str, filters: SearchFilters, limit: int, min_score: Optional[float] = None, only_relevant: bool = False) -> dict:
    """Semantic (embedding) retrieval returning the same evidence records as the lexical search. 503 if unavailable."""
    from fastapi import HTTPException

    from pipeline.rag.embeddings import EmbeddingUnavailable
    try:
        retriever, lexical = get_semantic_retriever()
        hits = retriever.search(q, filters, limit, min_score)
    except (SemanticUnavailable, EmbeddingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=f"Semantic retrieval is unavailable: {exc}") from exc
    chunk_by_id = {c["chunk_id"]: c for c in lexical.chunks}
    results = [build_evidence(h, lexical.docs[h.document_id], chunk_by_id[h.chunk_id]) for h in hits]
    _, ass, summary = _gate("semantic", q, hits, retriever, lexical)
    extra = _annotate(results, ass, summary, only_relevant)
    info = retriever.embedder.info
    return {"query": q, "mode": "semantic", "retrieval_method": retriever.method,
            "retrieval_note": "Semantic vector retrieval: cosine similarity between the query embedding and stored chunk embeddings "
                              "from the same model. Finds text with similar meaning, not only identical words. Results are source "
                              "evidence; no answer is generated.",
            "embedding_model": {"name": info.name, "version": info.version, "dimension": info.dimension},
            "min_score": retriever.min_score if min_score is None else min_score,
            "filters": {k: v for k, v in filters.__dict__.items() if v is not None}, **extra}


def search_evidence(q: str, filters: SearchFilters, limit: int, only_relevant: bool = False) -> dict:
    retriever = get_retriever()
    chunk_by_id = {c["chunk_id"]: c for c in retriever.chunks}
    hits = retriever.search(q, filters, limit)
    results = [build_evidence(h, retriever.docs[h.document_id], chunk_by_id[h.chunk_id]) for h in hits]
    _, ass, summary = _gate("lexical", q, hits, retriever, retriever)
    extra = _annotate(results, ass, summary, only_relevant)
    return {"query": q, "mode": "lexical", "retrieval_method": RETRIEVAL_METHOD,
            "retrieval_note": "Lexical keyword baseline: matches words that literally occur in the text. Not semantic/vector search; "
                              "no answer is generated -- these are source evidence records.",
            "filters": {k: v for k, v in filters.__dict__.items() if v is not None}, **extra}


def _where(source, source_type, province, admin_unit_id, event_type, date_from, date_to) -> tuple[str, dict]:
    clauses = ["is_current"]
    p: dict = {}
    if source:
        clauses.append("source = :source"); p["source"] = source  # noqa: E702
    if source_type:
        clauses.append("source_type = :source_type"); p["source_type"] = source_type  # noqa: E702
    if province:
        clauses.append("EXISTS (SELECT 1 FROM jsonb_array_elements_text(provinces) pr WHERE lower(pr) = lower(:province))"); p["province"] = province  # noqa: E702
    if admin_unit_id is not None:
        clauses.append("(admin_unit_id = :aid OR admin_unit_ids @> CAST(:aid_json AS jsonb))")
        p.update(aid=admin_unit_id, aid_json=json.dumps([admin_unit_id]))
    if event_type:
        clauses.append("EXISTS (SELECT 1 FROM jsonb_array_elements_text(event_types) ev WHERE lower(ev) = lower(:event_type))"); p["event_type"] = event_type  # noqa: E702
    if date_from:
        clauses.append("document_date >= :date_from"); p["date_from"] = date_from  # noqa: E702
    if date_to:
        clauses.append("document_date <= :date_to"); p["date_to"] = date_to  # noqa: E702
    return " AND ".join(clauses), p


def list_documents(source: Optional[str], source_type: Optional[str], province: Optional[str], admin_unit_id: Optional[int],
                   event_type: Optional[str], date_from: Optional[date], date_to: Optional[date], limit: int, offset: int) -> list[dict]:
    where, p = _where(source, source_type, province, admin_unit_id, event_type, date_from, date_to)
    rows = fetch_all(f"""SELECT {_DOC_META}, (SELECT count(*) FROM rag.document_chunks c WHERE c.document_id = d.document_id AND c.is_current) AS chunk_count,
                              length(raw_text) AS text_chars
                         FROM rag.documents d WHERE {where}
                         ORDER BY document_date DESC NULLS LAST, document_id LIMIT :limit OFFSET :offset""", {**p, "limit": limit, "offset": offset})
    return [_iso(r) for r in rows]


def get_document(document_id: str) -> Optional[dict]:
    rows = fetch_all(f"SELECT {_DOC_META}, raw_text FROM rag.documents WHERE document_id = :id AND is_current", {"id": document_id})
    if not rows:
        return None
    doc = _iso(rows[0])
    doc["chunks"] = fetch_all("SELECT chunk_id, chunk_index, char_start, char_end, chunk_sha256 FROM rag.document_chunks "
                              "WHERE document_id = :id AND is_current ORDER BY chunk_index", {"id": document_id})
    return doc


# ---------------------------------------------------------------------------------------------------- Task 31: hybrid + grounded answers
_hyb_cache: dict = {"key": None, "retriever": None}
_llm_provider = None

DISCLAIMER = ("Generated from retrieved source reports only; not an official warning and not a risk assessment. "
              "Check the cited source chunks. Risk levels come from the risk engine, not from this answer.")

HYBRID_NOTE = ("Hybrid retrieval: BM25 keyword ranks and semantic cosine ranks are combined by reciprocal rank fusion "
               "(1/(60+rank) per list). Exact names and paraphrases can both match. Results are source evidence; no answer is generated.")


def set_llm_provider(provider) -> None:
    """Inject the answer provider (tests / alternative deployments). None restores configuration from the environment."""
    global _llm_provider
    _llm_provider = provider


def get_llm_provider():
    if _llm_provider is not None:
        return _llm_provider
    from pipeline.rag.llm import provider_from_env
    return provider_from_env()                                  # raises LLMUnavailable when not configured


def get_hybrid_retriever():
    sem, lexical = get_semantic_retriever()                      # first: raises SemanticUnavailable before numpy is imported (lexical-only image)
    from pipeline.rag.hybrid import HybridRetriever
    with _lock:
        key = (id(sem), id(lexical))
        if _hyb_cache["key"] != key or _hyb_cache["retriever"] is None:
            _hyb_cache.update(key=key, retriever=HybridRetriever(lexical, sem))
        return _hyb_cache["retriever"], lexical


def _embedding_info(retriever) -> dict:
    info = retriever.embedder.info
    return {"name": info.name, "version": info.version, "dimension": info.dimension}


def search_hybrid_evidence(q: str, filters: SearchFilters, limit: int, min_score: Optional[float] = None, only_relevant: bool = False) -> dict:
    """Hybrid (BM25 + semantic, reciprocal rank fusion) retrieval returning the usual evidence records. 503 if semantic is unavailable."""
    from fastapi import HTTPException

    from pipeline.rag.embeddings import EmbeddingUnavailable
    try:
        retriever, lexical = get_hybrid_retriever()
        hits = retriever.search(q, filters, limit, min_score)
    except (SemanticUnavailable, EmbeddingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=f"Hybrid retrieval is unavailable (it needs semantic retrieval): {exc}") from exc
    chunk_by_id = {c["chunk_id"]: c for c in lexical.chunks}
    results = [build_evidence(h, lexical.docs[h.document_id], chunk_by_id[h.chunk_id]) for h in hits]
    _, ass, summary = _gate("hybrid", q, hits, retriever, lexical)
    extra = _annotate(results, ass, summary, only_relevant)
    return {"query": q, "mode": "hybrid", "retrieval_method": retriever.method, "retrieval_note": HYBRID_NOTE,
            "embedding_model": _embedding_info(retriever), "min_score": retriever.min_score if min_score is None else min_score,
            "filters": {k: v for k, v in filters.__dict__.items() if v is not None}, **extra}


def _retrieve_for_ask(q: str, filters: SearchFilters, limit: int, mode: str, min_score: Optional[float]):
    """-> (hits, retriever, lexical, details). Raises SemanticUnavailable / EmbeddingUnavailable for semantic and hybrid."""
    if mode == "lexical":
        lexical = get_retriever()
        return lexical.search(q, filters, limit), lexical, lexical, {"min_score": None, "embedding_model": None}
    if mode == "semantic":
        sem, lexical = get_semantic_retriever()
        ms = sem.min_score if min_score is None else min_score
        return sem.search(q, filters, limit, min_score), sem, lexical, {"min_score": ms, "embedding_model": _embedding_info(sem)}
    hyb, lexical = get_hybrid_retriever()
    ms = hyb.min_score if min_score is None else min_score
    return hyb.search(q, filters, limit, min_score), hyb, lexical, {"min_score": ms, "embedding_model": _embedding_info(hyb)}


def ask_question(q: str, filters: SearchFilters, mode: str, top_k: int, min_score: Optional[float] = None) -> tuple[dict, int]:
    """Retrieve evidence, ask the configured LLM to answer from it only, validate the citations. -> (response body, HTTP status).
    Evidence is always returned. Status 503 (answer_status LLM_UNAVAILABLE) when no provider is configured or it fails."""
    from fastapi import HTTPException

    from pipeline.rag import grounding as g
    from pipeline.rag.embeddings import EmbeddingUnavailable
    from pipeline.rag.llm import LLMUnavailable, constraints_from_env
    try:
        hits, retriever, lexical, details = _retrieve_for_ask(q, filters, top_k * 3, mode, min_score)
    except (SemanticUnavailable, EmbeddingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=f"{mode.capitalize()} retrieval is unavailable: {exc}") from exc
    chunk_by_id = {c["chunk_id"]: c for c in lexical.chunks}
    rel_hits, ass, summary = _gate(mode, q, hits, retriever, lexical)                 # Task 35: only chunks that pass the relevance policy are evidence
    selected = g.select_evidence(rel_hits, chunk_by_id, top_k)
    records = [build_evidence(h, lexical.docs[h.document_id], chunk_by_id[h.chunk_id]) for h in selected]
    items = g.pack_evidence(records, chunk_by_id)
    retrieval = {"mode": mode, "method": retriever.method, "evidence_count": len(records), "top_k": top_k, "relevance": _relevance_block(summary, ass),
                 "filters": {k: v for k, v in filters.__dict__.items() if v is not None}, "min_score": details["min_score"],
                 "embedding_model": details["embedding_model"],
                 "note": "Evidence is the top-ranked distinct chunks that pass the relevance policy (duplicate boilerplate chunks are skipped; low-relevance chunks are withheld)."}
    note = "Deterministic provenance check: cited ids must be among the supplied evidence and each sentence must cite. It is not fact checking."

    def body(status, answer, outcome=None, model=None, cited=()):
        v = outcome.validation if outcome else None
        judged = v is not None and status in (g.ANSWERED, g.INVALID)
        return {"query": q, "answer": answer, "answer_status": status,
                "citations": [{"chunk_id": e["chunk_id"], "document_id": e["document_id"], "title": e["title"], "source": e["source"],
                               "document_date": e["document_date"], "source_reference": e["source_reference"]}
                              for e in records if e["chunk_id"] in cited],
                "evidence": records, "retrieval": retrieval, "model": model or {"provider": None, "model": None, "configured": False, "called": False},
                "groundedness": {"citations_valid": (not any(p["code"] in ("unknown_citation", "no_citations") for p in v.problems)) if judged else None,
                                 "all_sentences_cited": (not v.uncited_sentences) if judged else None,
                                 "evidence_supplied": len(records), "evidence_cited": len(cited), "problems": v.problems if v else [],
                                 "warnings": v.warnings if v else [],
                                 "rejected_answer_text": outcome.raw_answer if outcome and status == g.INVALID else None, "validation_note": note},
                "disclaimer": DISCLAIMER}

    if not records:
        return body(g.RETRIEVAL_EMPTY, None), 200
    try:
        provider = get_llm_provider()
    except LLMUnavailable as exc:
        return body(g.LLM_UNAVAILABLE, None, model={"provider": None, "model": None, "configured": False, "error": str(exc), "called": False}), 503
    outcome = g.answer_question(q, items, provider, constraints_from_env())
    model = {"provider": outcome.provider or getattr(provider, "name", None), "model": outcome.model or getattr(provider, "model", None),
             "configured": True, "error": outcome.llm_error, "called": True}
    if outcome.status == g.LLM_UNAVAILABLE:
        return body(g.LLM_UNAVAILABLE, None, outcome, model), 503
    return body(outcome.status, outcome.answer, outcome, model, outcome.validation.citations if outcome.status == g.ANSWERED else ()), 200


def retrieve_evidence(q: str, filters: SearchFilters, mode: str, top_k: int, min_score: Optional[float] = None) -> dict:
    """Evidence selection shared with other layers (Task 32): retrieve with the given mode, skip duplicate chunk text, return the evidence
    records, the items packed for a language model and the retrieval description. 503 when the mode needs an unavailable embedding runtime."""
    from fastapi import HTTPException

    from pipeline.rag import grounding as g
    from pipeline.rag.embeddings import EmbeddingUnavailable
    try:
        hits, retriever, lexical, details = _retrieve_for_ask(q, filters, top_k * 3, mode, min_score)
    except (SemanticUnavailable, EmbeddingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=f"{mode.capitalize()} retrieval is unavailable: {exc}") from exc
    chunk_by_id = {c["chunk_id"]: c for c in lexical.chunks}
    rel_hits, ass, summary = _gate(mode, q, hits, retriever, lexical)                 # Task 35: only chunks that pass the relevance policy are evidence
    selected = g.select_evidence(rel_hits, chunk_by_id, top_k)
    records = [build_evidence(h, lexical.docs[h.document_id], chunk_by_id[h.chunk_id]) for h in selected]
    return {"records": records, "items": g.pack_evidence(records, chunk_by_id),
            "retrieval": {"mode": mode, "method": retriever.method, "min_score": details["min_score"], "embedding_model": details["embedding_model"],
                          "relevance": _relevance_block(summary, ass)}}
