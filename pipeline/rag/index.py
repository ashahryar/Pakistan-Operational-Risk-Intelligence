"""Build the RAG corpus (normalize + chunk) from the existing parsed artifacts. Pure given its inputs; idempotent."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

from pipeline.rag.chunking import DEFAULT_OVERLAP, DEFAULT_SIZE, chunk_document
from pipeline.rag.contracts import validate_chunk, validate_document
from pipeline.rag.normalize import normalize_document
from pipeline.rag.sources import READERS, discover_non_document_artifacts


def build_corpus(root: Path, unit_lookup: Optional[dict[str, int]] = None, size: int = DEFAULT_SIZE,
                 overlap: int = DEFAULT_OVERLAP, readers=READERS) -> dict:
    docs: dict[str, dict] = {}
    discovered: dict[str, int] = {}
    skipped: list[dict] = []
    for name, reader in readers:
        found, skip = reader(root)
        discovered[name] = len(found) + len(skip)
        skipped += skip
        for s in found:
            d = normalize_document(s, unit_lookup)
            errs = validate_document(d)
            if errs:
                skipped.append({"source": d["source"], "id": d["document_id"], "reason": "; ".join(errs)})
            elif d["document_id"] in docs:
                skipped.append({"source": d["source"], "id": d["document_id"], "reason": "duplicate document_id (first occurrence kept)"})
            else:
                docs[d["document_id"]] = d
    documents = [docs[k] for k in sorted(docs)]
    chunks = []
    for d in documents:
        cs = chunk_document(d, size, overlap)
        bad = [e for c in cs for e in validate_chunk(c, d)]
        if bad:
            raise ValueError(f"chunk validation failed for {d['document_id']}: {bad[:3]}")
        chunks += cs
    return {"documents": documents, "chunks": chunks, "skipped": skipped, "discovered_by_reader": discovered,
            "non_document_artifacts": discover_non_document_artifacts(root),
            "summary": {"documents": len(documents), "chunks": len(chunks),
                        "documents_by_source_type": dict(sorted(Counter(f"{d['source']}/{d['source_type']}" for d in documents).items())),
                        "chunks_by_source": dict(sorted(Counter(c["document_id"].split(":")[0] for c in chunks).items())),
                        "documents_without_date": sum(1 for d in documents if d["document_date"] is None),
                        "documents_by_geography_status": dict(sorted(Counter(d["geography_status"] for d in documents).items())),
                        "documents_with_event_type": sum(1 for d in documents if d["event_types"]),
                        "chunk_size": size, "chunk_overlap": overlap}}
