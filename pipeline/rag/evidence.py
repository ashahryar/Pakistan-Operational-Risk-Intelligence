"""Evidence/provenance: turn a retrieval hit into a self-describing evidence record. The snippet is a verbatim slice of
the stored text (with offsets into the document), so every statement can be traced to its document and position."""

from __future__ import annotations

from pipeline.rag.retrieval import Hit, tokenize

SNIPPET_CHARS = 300


def snippet_span(chunk: dict, terms: tuple[str, ...], size: int = SNIPPET_CHARS) -> tuple[int, int]:
    """Verbatim window inside the chunk, starting near the first matching term. Offsets are relative to the chunk text."""
    text = chunk["chunk_text"]
    first = None
    low = text.lower()
    for t in terms:
        i = low.find(t)
        if i >= 0 and (first is None or i < first):
            first = i
    start = max(0, (first or 0) - size // 4)
    if start and not text[start - 1].isspace():          # begin on a word boundary
        nxt = next((j for j in range(start, min(start + 40, len(text))) if text[j].isspace()), start)
        start = nxt + 1 if nxt < len(text) else start
    return start, min(len(text), start + size)


def build_evidence(hit: Hit, doc: dict, chunk: dict) -> dict:
    if hit.method.startswith(("semantic", "hybrid")):    # no single term anchor: the whole chunk is the evidence (still a verbatim slice)
        s, e = 0, len(chunk["chunk_text"])
    else:
        s, e = snippet_span(chunk, hit.matched_terms)
    return {
        "document_id": doc["document_id"], "chunk_id": chunk["chunk_id"], "title": doc.get("title"), "source": doc["source"],
        "source_type": doc["source_type"], "document_date": doc.get("document_date"),
        "geography": {"province": doc.get("province"), "admin_unit_id": doc.get("admin_unit_id"), "admin_unit_name": doc.get("admin_unit_name"),
                      "provinces": doc.get("provinces") or [], "status": doc.get("geography_status"), "basis": doc.get("geography_basis")},
        "event": {"event_type": doc.get("event_type"), "event_types": doc.get("event_types") or []},
        "relevance": {"score": hit.score, "method": hit.method, "relevance_type": hit.method, "matched_terms": list(hit.matched_terms),
                      "model_version": hit.model_version,
                      **({"lexical_rank": hit.lexical_rank, "semantic_rank": hit.semantic_rank, "fused_rank": hit.fused_rank,
                          "lexical_score": hit.lexical_score, "semantic_score": hit.semantic_score} if hit.method.startswith("hybrid") else {})},
        "snippet": chunk["chunk_text"][s:e], "snippet_document_char_start": chunk["char_start"] + s,
        "snippet_document_char_end": chunk["char_start"] + e,
        "source_reference": {"url": doc.get("url"), "file_path": doc.get("file_path"), "content_sha256": doc.get("content_sha256")},
    }


_ = tokenize
