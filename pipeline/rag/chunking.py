"""Deterministic chunking. Chunks are verbatim character slices of the document text (never rewritten), cut at whitespace,
with a fixed overlap. A chunk never spans two documents, and the same input always yields the same ids and spans."""

from __future__ import annotations

from pipeline.rag.contracts import CHUNKER_VERSION, make_chunk_id, sha256_text

DEFAULT_SIZE = 1200
DEFAULT_OVERLAP = 150


def chunk_spans(text: str, size: int = DEFAULT_SIZE, overlap: int = DEFAULT_OVERLAP) -> list[tuple[int, int]]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    n = len(text)
    spans: list[tuple[int, int]] = []
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:                                   # prefer a whitespace cut in the last 40% of the window
            cut = max(text.rfind(" ", start + int(size * 0.6), end), text.rfind("\n", start + int(size * 0.6), end))
            if cut > start:
                end = cut
        if text[start:end].strip():
            spans.append((start, end))
        if end >= n:
            break
        nxt = max(end - overlap, start + 1)
        while 0 < nxt < end and not text[nxt - 1].isspace():     # start the next chunk on a word boundary
            nxt += 1
        start = nxt if nxt < end else end
    return spans


def chunk_document(doc: dict, size: int = DEFAULT_SIZE, overlap: int = DEFAULT_OVERLAP) -> list[dict]:
    text = doc["raw_text"]
    return [{"chunk_id": make_chunk_id(doc["document_id"], i), "document_id": doc["document_id"], "chunk_index": i,
             "char_start": s, "char_end": e, "chunk_text": text[s:e], "chunk_sha256": sha256_text(text[s:e]),
             "chunker_version": CHUNKER_VERSION}
            for i, (s, e) in enumerate(chunk_spans(text, size, overlap))]
