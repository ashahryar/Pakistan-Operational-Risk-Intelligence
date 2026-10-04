"""Canonical document / chunk contract for the RAG foundation (Phase A: documents, chunks, provenance, lexical retrieval).

Nothing here invents metadata: a field the source does not provide is None. Text is stored verbatim and never rewritten.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

NORMALIZATION_VERSION = "rag-normalize-1.0.0"
CHUNKER_VERSION = "rag-chunker-1.0.0"
RETRIEVAL_METHOD = "lexical_bm25_baseline"

DOCUMENT_FIELDS = [
    "document_id", "source", "source_type", "title", "document_date", "document_date_text", "document_date_basis",
    "published_at", "url", "file_path", "province", "admin_unit_id", "admin_unit_name", "provinces", "districts",
    "admin_unit_ids", "geography_status", "geography_basis", "geography_text", "event_type", "event_types",
    "event_type_raw", "language_script", "raw_text", "content_sha256", "metadata", "ingestion_timestamp", "parser_version",
    "normalization_version",
]
CHUNK_FIELDS = ["chunk_id", "document_id", "chunk_index", "char_start", "char_end", "chunk_text", "chunk_sha256", "chunker_version"]
GEOGRAPHY_STATUSES = {"resolved", "resolved_multi", "partial", "unresolved", "not_stated"}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug(value: Any) -> str:
    """Stable identifier fragment: keeps letters/digits/._- ; everything else becomes '-'."""
    return re.sub(r"[^\w.\-]+", "-", str(value), flags=re.UNICODE).strip("-")


def make_document_id(source: str, source_type: str, native_id: str) -> str:
    """Stable across reruns: derived only from the source system's own identifier."""
    if not native_id:
        raise ValueError("a document needs a native identifier")
    return f"{slug(source)}:{slug(source_type)}:{slug(native_id)}"


def make_chunk_id(document_id: str, index: int) -> str:
    return f"{document_id}#c{index:04d}"


def validate_document(doc: dict) -> list[str]:
    errs = [f"missing field {k}" for k in DOCUMENT_FIELDS if k not in doc]
    if errs:
        return errs
    if not doc["document_id"] or not doc["source"] or not doc["raw_text"]:
        errs.append("document_id, source and raw_text are required")
    if doc["content_sha256"] != sha256_text(doc["raw_text"] or ""):
        errs.append("content_sha256 does not match raw_text")
    if doc["geography_status"] not in GEOGRAPHY_STATUSES:
        errs.append(f"unknown geography_status {doc['geography_status']}")
    if doc["document_date"] is None and doc["document_date_basis"] not in (None, "unparseable", "not_stated"):
        errs.append("a missing date must not claim a basis")
    return errs


def validate_chunk(chunk: dict, doc: Optional[dict] = None) -> list[str]:
    errs = [f"missing field {k}" for k in CHUNK_FIELDS if k not in chunk]
    if errs:
        return errs
    if not chunk["chunk_id"].startswith(chunk["document_id"] + "#c"):
        errs.append("chunk_id does not carry its document_id")
    if chunk["chunk_sha256"] != sha256_text(chunk["chunk_text"]):
        errs.append("chunk_sha256 does not match chunk_text")
    if doc is not None and doc["raw_text"][chunk["char_start"]:chunk["char_end"]] != chunk["chunk_text"]:
        errs.append("chunk_text is not a verbatim slice of the document text")
    return errs
