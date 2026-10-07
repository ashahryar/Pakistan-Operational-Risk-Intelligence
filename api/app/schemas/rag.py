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
    model_version: Optional[str] = None        # embedding model revision (semantic / hybrid results only)
    lexical_rank: Optional[int] = None         # hybrid only: 1-based rank in the BM25 list (null = not retrieved lexically)
    semantic_rank: Optional[int] = None        # hybrid only: 1-based rank in the semantic list (null = below the cosine floor)
    fused_rank: Optional[int] = None
    lexical_score: Optional[float] = None
    semantic_score: Optional[float] = None
    assessment: Optional[dict[str, Any]] = None  # Task 35: {label RELEVANT|LOW_RELEVANCE, coverage, absent_share, cosine}


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
    relevance_status: Optional[str] = None      # Task 35: RELEVANT | NO_EVIDENCE (decided by the relevance policy, not by the number of results)
    abstained: Optional[bool] = None
    abstention_reason: Optional[str] = None
    relevance_policy: Optional[dict[str, Any]] = None


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    title: Optional[str]
    source: str
    document_date: Optional[str]
    source_reference: SourceReference


class AskRetrieval(BaseModel):
    mode: str
    method: str
    evidence_count: int
    top_k: int
    filters: dict[str, Any]
    min_score: Optional[float] = None
    embedding_model: Optional[dict[str, Any]] = None
    note: str
    relevance: Optional[dict[str, Any]] = None  # Task 35: relevance_status, abstained, abstention_reason, counts, policy


class AskModel(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    configured: bool
    error: Optional[str] = None
    called: Optional[bool] = None               # Task 35: whether a language model was actually called (false when retrieval found no relevant evidence)


class AskGroundedness(BaseModel):
    citations_valid: Optional[bool] = None          # null when no answer was produced
    all_sentences_cited: Optional[bool] = None
    evidence_supplied: int
    evidence_cited: int
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rejected_answer_text: Optional[str] = None      # model output withheld because validation failed (kept for audit only)
    validation_note: str


class AskResponse(BaseModel):
    query: str
    answer: Optional[str]
    answer_status: str                              # ANSWERED | INSUFFICIENT_EVIDENCE | INVALID_ANSWER | LLM_UNAVAILABLE | RETRIEVAL_EMPTY
    citations: list[Citation]
    evidence: list[Evidence]
    retrieval: AskRetrieval
    model: AskModel
    groundedness: AskGroundedness
    disclaimer: str
