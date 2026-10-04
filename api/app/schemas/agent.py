from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class AgentResponse(BaseModel):
    """The structured result of one read-only agent execution. Blocks keep separate provenance; `answer` is null unless a real model produced one and
    the existing grounding validation accepted it."""
    question: str
    status: str            # ANSWERED | COMPLETED | LLM_UNAVAILABLE | UNSUPPORTED_REQUEST | AMBIGUOUS_GEOGRAPHY | INSUFFICIENT_DATA | INVALID_TOOL_CALL | NO_EVIDENCE | INSUFFICIENT_EVIDENCE | INVALID_ANSWER
    status_reason: Optional[str] = None
    reason_code: Optional[str] = None
    intent: Optional[str] = None
    answer: Optional[str] = None
    geography: Optional[dict[str, Any]] = None
    risk_context: Optional[dict[str, Any]] = None
    risk_history: Optional[list[dict[str, Any]]] = None
    documentary_evidence: list[dict[str, Any]] = []
    retrieval: Optional[dict[str, Any]] = None
    ml_prediction: Optional[dict[str, Any]] = None
    components: dict[str, Any] = {}
    premise_check: Optional[dict[str, Any]] = None
    tool_trace: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    model: dict[str, Any] = {}
    groundedness: Optional[dict[str, Any]] = None
    provenance: dict[str, Any] = {}
    policy: Optional[dict[str, Any]] = None
    trace: dict[str, Any] = {}
    disclaimer: str


class AgentTool(BaseModel):
    tool_name: str
    description: str
    read_only: bool
    provenance: list[str]
    arguments: dict[str, Any]
