"""Task 34 -- contracts of the read-only operational intelligence agent (pure Python: no database, no network, no framework).

The agent is an ORCHESTRATOR over existing trusted capabilities (geography, risk engine, RAG, ML predictions, the intelligence layer). It is not a
data source and it invents nothing. Everything it returns is either a tool result (with provenance) or an answer a real language model produced and
the existing grounding validator accepted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

AGENT_VERSION = "1.0.0"

# ---------------------------------------------------------------------------------------------------------------------------------- intents
CURRENT_RISK = "CURRENT_RISK"
HISTORICAL_RISK = "HISTORICAL_RISK"
DOCUMENT_SEARCH = "DOCUMENT_SEARCH"
EVIDENCE_GROUNDED_QUESTION = "EVIDENCE_GROUNDED_QUESTION"
ML_FORECAST = "ML_FORECAST"
GEOGRAPHY_LOOKUP = "GEOGRAPHY_LOOKUP"
COMBINED_INTELLIGENCE = "COMBINED_INTELLIGENCE"
UNSUPPORTED = "UNSUPPORTED"
INTENTS = (CURRENT_RISK, HISTORICAL_RISK, DOCUMENT_SEARCH, EVIDENCE_GROUNDED_QUESTION, ML_FORECAST, GEOGRAPHY_LOOKUP, COMBINED_INTELLIGENCE, UNSUPPORTED)

# ------------------------------------------------------------------------------------------------------------------------- agent statuses
ANSWERED = "ANSWERED"                              # a real LLM answered and the existing grounding validator accepted it
COMPLETED = "COMPLETED"                            # structured results returned; no language generation was needed (geography lookups)
LLM_UNAVAILABLE = "LLM_UNAVAILABLE"                # structured tool results returned; no real provider, so NO natural-language answer exists
UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
AMBIGUOUS_GEOGRAPHY = "AMBIGUOUS_GEOGRAPHY"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
INVALID_TOOL_CALL = "INVALID_TOOL_CALL"
NO_EVIDENCE = "NO_EVIDENCE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"    # the model abstained
INVALID_ANSWER = "INVALID_ANSWER"                  # the model's answer failed the existing grounding validation and was withheld
AGENT_STATUSES = (ANSWERED, COMPLETED, LLM_UNAVAILABLE, UNSUPPORTED_REQUEST, AMBIGUOUS_GEOGRAPHY, INSUFFICIENT_DATA, INVALID_TOOL_CALL, NO_EVIDENCE,
                  INSUFFICIENT_EVIDENCE, INVALID_ANSWER)

# ------------------------------------------------------------------------------------------------------------------------------ provenance
RISK_ENGINE = "RISK_ENGINE"
RAG_DOCUMENT = "RAG_DOCUMENT"
ML_MODEL = "ML_MODEL"
BASELINE_MODEL = "BASELINE_MODEL"
GEOGRAPHY = "GEOGRAPHY"
PROVENANCES = (RISK_ENGINE, RAG_DOCUMENT, ML_MODEL, BASELINE_MODEL, GEOGRAPHY)

# ------------------------------------------------------------------------------------------------------------------------- tool statuses
TOOL_OK = "OK"
TOOL_EMPTY = "EMPTY"                  # the tool ran and there is genuinely nothing (no row / no chunk / no valid prediction)
TOOL_UNAVAILABLE = "UNAVAILABLE"      # the capability could not run (e.g. semantic retrieval has no embedding runtime)
TOOL_ERROR = "ERROR"
TOOL_REJECTED = "INVALID_TOOL_CALL"   # failed validation; never executed
TOOL_STATUSES = (TOOL_OK, TOOL_EMPTY, TOOL_UNAVAILABLE, TOOL_ERROR, TOOL_REJECTED)

BASELINE_LABEL = "BASELINE_ONLY — NOT VALIDATED ML"
NOT_A_RISK_STATUS = "A forecast of an observed quantity at a future date. It is not a current risk status and not a risk score."
DISCLAIMER = ("Read-only orchestration of existing PORI capabilities. Every fact carries the provenance of the capability that produced it "
              "(RISK_ENGINE, RAG_DOCUMENT, ML_MODEL, BASELINE_MODEL, GEOGRAPHY). Not an official warning. No natural-language answer is shown unless a "
              "real language model produced one and the grounding validation accepted it.")


@dataclass(frozen=True)
class PlannedCall:
    """One tool call: the tool name and its (not yet validated) arguments, and where the plan came from."""
    tool: str
    arguments: dict
    origin: str = "deterministic"        # deterministic | llm | agent (the mandatory geography step)

    def to_dict(self) -> dict:
        return {"tool_name": self.tool, "arguments": dict(self.arguments), "origin": self.origin}


@dataclass
class ToolResult:
    """The uniform result of a tool call. `provenance` is always present, including for rejected or empty calls."""
    tool_name: str
    arguments: dict
    status: str
    result: Any = None
    provenance: dict = field(default_factory=lambda: {"sources": []})
    reason: Optional[str] = None
    duration_ms: Optional[float] = None
    origin: str = "deterministic"

    def to_dict(self, include_result: bool = True) -> dict:
        d = {"tool_name": self.tool_name, "arguments": self.arguments, "status": self.status, "provenance": self.provenance,
             "reason": self.reason, "duration_ms": self.duration_ms, "origin": self.origin}
        if include_result:
            d["result"] = self.result
        return d


@dataclass
class AgentRequest:
    q: str
    admin_unit_id: Optional[int] = None
    date: Optional[str] = None                 # ISO date; the risk date to look up
    mode: str = "hybrid"                       # retrieval mode for documentary evidence: lexical | semantic | hybrid
    routing: str = "auto"                      # auto = LLM-assisted when a provider is available, else deterministic | deterministic
    top_k: int = 5

    def to_dict(self) -> dict:
        return {"q": self.q, "admin_unit_id": self.admin_unit_id, "date": self.date, "mode": self.mode, "routing": self.routing, "top_k": self.top_k}
