from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from api.app.schemas.rag import Evidence, SourceReference
from api.app.schemas.risk import OperationalRisk


class RiskContext(BaseModel):
    status: str                                   # AVAILABLE | NO_RISK_CONTEXT
    provenance: str                               # RISK_ENGINE
    record: Optional[OperationalRisk] = None      # the risk-engine row exactly as served by /api/v1/risk (risk_score is null in v1.0.0)
    reason: Optional[str] = None
    lookup: dict[str, Any]
    note: str


class IntelligenceRetrieval(BaseModel):
    mode: str
    method: Optional[str] = None
    evidence_count: int
    top_k: int
    filters_requested: dict[str, Any]
    filters_applied: dict[str, Any]
    filters_relaxed: list[str]
    min_score: Optional[float] = None
    embedding_model: Optional[dict[str, Any]] = None
    note: str


class IntelligenceCitation(BaseModel):
    kind: str                                     # documentary | risk_engine
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    document_date: Optional[str] = None
    source_reference: Optional[SourceReference] = None
    admin_unit_id: Optional[int] = None
    risk_date: Optional[str] = None
    calculation_version: Optional[str] = None


class IntelligenceModel(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    configured: bool
    error: Optional[str] = None


class IntelligenceGroundedness(BaseModel):
    citations_valid: Optional[bool] = None
    risk_context_supplied: bool
    evidence_supplied: int
    evidence_cited: int
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rejected_answer_text: Optional[str] = None
    validation_note: str


class IntelligenceResponse(BaseModel):
    question: str
    status: str            # ANSWERED | LLM_UNAVAILABLE | NO_RISK_CONTEXT | RETRIEVAL_EMPTY | INSUFFICIENT_EVIDENCE | INVALID_ANSWER
    question_context: dict[str, Any]
    risk_context: RiskContext
    documentary_evidence: list[Evidence]
    retrieval: IntelligenceRetrieval
    answer: Optional[str]
    citations: list[IntelligenceCitation]
    model: IntelligenceModel
    groundedness: IntelligenceGroundedness
    provenance: dict[str, Any]
    disclaimer: str
