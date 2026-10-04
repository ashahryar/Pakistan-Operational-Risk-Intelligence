"""Assembly of the evidence package and the deterministic decisions around it (filter plan, status before generation).

`risk_context` (computed, RISK_ENGINE) and `documentary_evidence` (retrieved report chunks) stay separate end to end; they are only
combined, still labelled, in the final prompt. Nothing here calculates a risk score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pipeline.intelligence.risk_context import AVAILABLE, NO_RISK_CONTEXT, PROVENANCE

DOC_NOTE = "Documentary evidence = passages of NDMA / PDMA / PMD / FFC reports. They describe conditions; they are not risk-engine inputs."


@dataclass
class IntelligenceContext:
    question: str
    question_context: dict
    risk_context: dict
    retrieved_evidence: list = field(default_factory=list)
    retrieval: dict = field(default_factory=dict)
    ml_prediction: Optional[dict] = None          # Task 33: a forecast (provenance ML_MODEL); never merged into risk_context

    @property
    def provenance(self) -> dict:
        rec = self.risk_context.get("record")
        return {"risk_context": {"source": PROVENANCE, "available": self.risk_context["status"] == AVAILABLE,
                                 "calculation_version": rec["calculation_version"] if rec else None,
                                 "risk_date": rec["risk_date"] if rec else None},
                "documentary_evidence": {"source": "official reports retrieved by the RAG layer", "chunk_ids": [e["chunk_id"] for e in self.retrieved_evidence],
                                         "document_ids": sorted({e["document_id"] for e in self.retrieved_evidence})},
                "ml_prediction": {"source": "ML_MODEL", "available": self.ml_prediction is not None,
                                  "model_run_ids": sorted({p["model_run_id"] for p in self.ml_prediction["predictions"]}) if self.ml_prediction else []},
                "note": "Computed signals, ML forecasts and documentary evidence are kept separate: a document never becomes a risk-engine input, a "
                        "risk status is never attributed to a document, and an ML forecast is never a current risk status."}

    def to_dict(self) -> dict:
        return {"question": self.question, "question_context": self.question_context, "risk_context": self.risk_context,
                "documentary_evidence": self.retrieved_evidence, "retrieval": self.retrieval, "ml_prediction": self.ml_prediction,
                "provenance": self.provenance}


def plan_filters(*, unit: Optional[dict], province: Optional[dict], province_text: Optional[str], event_types: list[str],
                 date_from: Optional[str], date_to: Optional[str], source: Optional[str]) -> list[dict]:
    """Ordered retrieval attempts, strictest first. Each: {"filters": {...}, "relaxed": [names dropped so far]}.
    Relaxation order: event_type -> district_to_province -> date. The geography (province at least) and `source` are never dropped."""
    base: dict = {}
    if unit and unit["level"] == 2:
        base["admin_unit_id"] = unit["id"]
    elif province:
        base["province"] = province["name"]
    elif province_text:
        base["province"] = province_text
    if len(event_types) == 1:
        base["event_type"] = event_types[0]
    if date_from:
        base["date_from"] = date_from
    if date_to:
        base["date_to"] = date_to
    if source:
        base["source"] = source
    attempts = [{"filters": dict(base), "relaxed": []}]
    cur, relaxed = dict(base), []
    if "event_type" in cur:
        cur.pop("event_type")
        relaxed.append("event_type")
        attempts.append({"filters": dict(cur), "relaxed": list(relaxed)})
    if "admin_unit_id" in cur and province:
        cur.pop("admin_unit_id")
        cur["province"] = province["name"]
        relaxed.append("district_to_province")
        attempts.append({"filters": dict(cur), "relaxed": list(relaxed)})
    if "date_from" in cur or "date_to" in cur:
        cur.pop("date_from", None)
        cur.pop("date_to", None)
        relaxed.append("date")
        attempts.append({"filters": dict(cur), "relaxed": list(relaxed)})
    return attempts


def status_before_generation(*, risk_available: bool, risk_intent: bool, evidence_count: int, ml_available: bool = False) -> Optional[str]:
    """A terminal status decided without the language model, or None when generation should be attempted."""
    if risk_intent and not risk_available:
        return NO_RISK_CONTEXT                       # a classification was asked about but no risk record exists: nothing to explain
    if not risk_available and evidence_count == 0 and not ml_available:
        return "RETRIEVAL_EMPTY"
    return None
