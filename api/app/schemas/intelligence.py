from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from api.app.schemas.ml import MlPrediction
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
    relevance: Optional[dict[str, Any]] = None    # Task 35: relevance_status RELEVANT | NO_EVIDENCE, abstained, abstention_reason, counts, policy, withheld chunk ids


class MlPredictionBlock(BaseModel):
    provenance: str                               # ML_MODEL
    kind: str
    predictions: list[MlPrediction]
    validated_against_baseline: bool
    note: str


class IntelligenceCitation(BaseModel):
    kind: str                                     # documentary | risk_engine | ml_prediction
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    document_date: Optional[str] = None
    source_reference: Optional[SourceReference] = None
    admin_unit_id: Optional[int] = None
    risk_date: Optional[str] = None
    calculation_version: Optional[str] = None
    model_run_ids: Optional[list[str]] = None


class IntelligenceModel(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    configured: bool
    error: Optional[str] = None
    called: Optional[bool] = None                 # Task 35: false when no language model was called (e.g. no relevant evidence)


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
    ml_prediction: Optional[MlPredictionBlock] = None   # null unless a valid ML forecast exists for the area; never part of risk_context
    answer: Optional[str]
    citations: list[IntelligenceCitation]
    model: IntelligenceModel
    groundedness: IntelligenceGroundedness
    provenance: dict[str, Any]
    disclaimer: str
