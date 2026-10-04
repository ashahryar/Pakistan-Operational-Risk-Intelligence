from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    document_id: str
    source: str
    source_type: str
    title: Optional[str]
    document_date: Optional[str]
    document_date_text: Optional[str]
    document_date_basis: Optional[str]
    published_at: Optional[str]
    url: Optional[str]
    file_path: Optional[str]
    province: Optional[str]
    admin_unit_id: Optional[int]
    admin_unit_name: Optional[str]
    provinces: list[str]
    districts: list[dict[str, Any]]
    admin_unit_ids: list[int]
    geography_status: str
    geography_basis: Optional[str]
    event_type: Optional[str]
    event_types: list[str]
    language_script: Optional[str]
    content_sha256: str
    ingestion_timestamp: Optional[str]
    parser_version: Optional[str]
    normalization_version: str
    chunk_count: int
    text_chars: int


class ChunkRef(BaseModel):
    chunk_id: str
    chunk_index: int
    char_start: int
    char_end: int
    chunk_sha256: str


class DocumentDetail(BaseModel):
    document_id: str
    source: str
    source_type: str
    title: Optional[str]
    document_date: Optional[str]
    document_date_text: Optional[str]
    document_date_basis: Optional[str]
    published_at: Optional[str]
    url: Optional[str]
    file_path: Optional[str]
    province: Optional[str]
    admin_unit_id: Optional[int]
    admin_unit_name: Optional[str]
    provinces: list[str]
    districts: list[dict[str, Any]]
    admin_unit_ids: list[int]
    geography_status: str
    geography_basis: Optional[str]
    geography_text: list[str]
    event_type: Optional[str]
    event_types: list[str]
    event_type_raw: list[str]
    language_script: Optional[str]
    content_sha256: str
    metadata: dict[str, Any]
    ingestion_timestamp: Optional[str]
    parser_version: Optional[str]
    normalization_version: str
    raw_text: str
    chunks: list[ChunkRef]


class Geography(BaseModel):
    province: Optional[str]
    admin_unit_id: Optional[int]
    admin_unit_name: Optional[str]
    provinces: list[str]
    status: Optional[str]
    basis: Optional[str]


class EventInfo(BaseModel):
    event_type: Optional[str]
    event_types: list[str]


class Relevance(BaseModel):
    score: float
    method: str
    matched_terms: list[str]
    relevance_type: Optional[str] = None       # lexical_bm25_baseline | semantic_vector
    model_version: Optional[str] = None        # embedding model revision (semantic results only)


class SourceReference(BaseModel):
    url: Optional[str]
    file_path: Optional[str]
    content_sha256: Optional[str]


class Evidence(BaseModel):
    document_id: str
    chunk_id: str
    title: Optional[str]
    source: str
    source_type: str
    document_date: Optional[str]
    geography: Geography
    event: EventInfo
    relevance: Relevance
    snippet: str
    snippet_document_char_start: int
    snippet_document_char_end: int
    source_reference: SourceReference


class SearchResponse(BaseModel):
    query: str
    mode: str = "lexical"
    retrieval_method: str
    retrieval_note: str
    filters: dict[str, Any]
    count: int
    results: list[Evidence]
    embedding_model: Optional[dict[str, Any]] = None
    min_score: Optional[float] = None
