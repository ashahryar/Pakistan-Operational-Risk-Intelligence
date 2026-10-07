"""Task 32 -- evidence-grounded operational intelligence: serve the EXISTING risk-engine context next to retrieved documentary evidence.

Read-only. No risk is calculated, adjusted or interpreted here: the risk record is read through the same columns/shape as /api/v1/risk
(api/app/services/risk_serving.py). Retrieval reuses the RAG service (lexical / semantic / hybrid unchanged). The pure parts live in
pipeline/intelligence (context extraction, assembly, grounding); this module only performs the database reads and wires them together.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException

from api.app.db import fetch_all
from api.app.services.ml import unit_predictions
from api.app.services.rag import DISCLAIMER, get_llm_provider, retrieve_evidence
from api.app.services.risk_serving import _COLS, _shape
from pipeline.intelligence import risk_context as rc
from pipeline.intelligence.assembly import DOC_NOTE, IntelligenceContext, plan_filters, status_before_generation
from pipeline.intelligence.context import build_index, extract_context, normalize_name
from pipeline.intelligence.grounding import answer_intelligence
from pipeline.rag import grounding as g
from pipeline.rag.llm import LLMUnavailable, constraints_from_env
from pipeline.rag.retrieval import SearchFilters

VALIDATION_NOTE = ("Deterministic provenance check: [chunk:<id>] must be a supplied chunk, [risk_engine] only with an engine record, the two never in "
                   "one sentence, no risk status attributed to a document. Heuristic wording checks, not fact checking.")


def load_units() -> list[dict]:
    return fetch_all("SELECT u.id, u.level, u.name, p.name AS province FROM geo.admin_unit u "
                     "LEFT JOIN geo.admin_unit p ON p.id = u.parent_id AND p.level = 1 WHERE u.level IN (1, 2) ORDER BY u.level, u.id")


def lookup_risk(unit_id: int, risk_date: Optional[str], date_from: Optional[str], date_to: Optional[str]) -> tuple[Optional[dict], dict]:
    """The existing risk row for one unit: a specific date, the latest row inside a window, or the latest row. Never substitutes another date."""
    if risk_date:
        lookup = {"basis": "date", "admin_unit_id": unit_id, "date": risk_date}
        rows = fetch_all(f"SELECT {_COLS} FROM risk.operational_risk WHERE is_current AND admin_unit_id = :u AND risk_date = :d LIMIT 1",
                         {"u": unit_id, "d": date.fromisoformat(risk_date)})
    elif date_from or date_to:
        lookup = {"basis": "window", "admin_unit_id": unit_id, "date_from": date_from, "date_to": date_to}
        rows = fetch_all(f"SELECT {_COLS} FROM risk.operational_risk WHERE is_current AND admin_unit_id = :u "
                         "AND (CAST(:a AS date) IS NULL OR risk_date >= :a) AND (CAST(:b AS date) IS NULL OR risk_date <= :b) "
                         "ORDER BY risk_date DESC LIMIT 1",
                         {"u": unit_id, "a": date.fromisoformat(date_from) if date_from else None, "b": date.fromisoformat(date_to) if date_to else None})
    else:
        lookup = {"basis": "latest", "admin_unit_id": unit_id}
        rows = fetch_all(f"SELECT {_COLS} FROM risk.latest_operational_risk WHERE admin_unit_id = :u LIMIT 1", {"u": unit_id})
    return (_shape(rows[0]) if rows else None), lookup


def _no_risk_reason(lookup: dict, unit: Optional[dict], geography_status: str) -> str:
    if unit is None:
        return {"ambiguous": "the place name in the question is ambiguous, so no area was chosen",
                "multiple": "several different places were mentioned, so no single area was chosen",
                "unresolved": "the place in the question could not be matched to a known province or district"}.get(
            geography_status, "no province or district was identified (pass admin_unit_id or name one in the question)")
    basis = lookup["basis"]
    if basis == "date":
        return f"no risk record exists for {unit['name']} on {lookup['date']}"
    if basis == "window":
        return f"no risk record exists for {unit['name']} between {lookup.get('date_from')} and {lookup.get('date_to')}"
    return f"no risk record exists for {unit['name']}"


def _resolve_target(q: str, units: list[dict], admin_unit_id: Optional[int], province: Optional[str]):
    """-> (question context, unit, province unit, basis). Explicit parameters win over names found in the question text."""
    qctx = extract_context(q, units)
    by_id = {u["id"]: u for u in units}
    if admin_unit_id is not None:
        u = by_id.get(admin_unit_id)
        if u is None:
            raise HTTPException(status_code=404, detail=f"admin_unit_id {admin_unit_id} is not a province or district in geo.admin_unit")
        unit = {"id": u["id"], "level": u["level"], "name": u["name"], "province": u["province"] or u["name"], "match_method": "explicit_parameter", "raw": None}
        prov = {"id": u["id"], "name": u["name"]} if u["level"] == 1 else next(({"id": p["id"], "name": p["name"]} for p in units if p["level"] == 1 and p["name"] == u["province"]), None)
        return qctx, unit, prov, "explicit_admin_unit_id"
    if province:
        hits = [h for h in build_index(units).get(normalize_name(province), []) if h["level"] == 1]
        if len(hits) == 1:
            h = hits[0]
            return qctx, {"id": h["id"], "level": 1, "name": h["name"], "province": h["name"], "match_method": "explicit_parameter", "raw": province}, \
                {"id": h["id"], "name": h["name"]}, "explicit_province"
        return qctx, None, None, "explicit_province_unresolved"
    return qctx, qctx.admin_unit, qctx.province, "question_text"


def ask_intelligence(q: str, admin_unit_id: Optional[int], province: Optional[str], risk_date: Optional[date], date_from: Optional[date],
                     date_to: Optional[date], source: Optional[str], mode: str, top_k: int, min_score: Optional[float]) -> tuple[dict, int]:
    units = load_units()
    qctx, unit, prov, basis = _resolve_target(q, units, admin_unit_id, province)
    qd = qctx.to_dict()
    qd["target_basis"] = basis
    qd["province_parameter_unresolved"] = province if basis == "explicit_province_unresolved" else None

    r_date = risk_date.isoformat() if risk_date else qctx.date
    d_from = date_from.isoformat() if date_from else (qctx.date_from or qctx.date)
    d_to = date_to.isoformat() if date_to else (qctx.date_to or qctx.date)
    if risk_date and not date_from and not date_to:
        d_from = d_to = None                                       # an explicit risk date does not by itself restrict the documents

    # ---- risk context (existing engine record; no calculation)
    if unit is None:
        record, lookup = None, {"basis": "none"}
    else:
        record, lookup = lookup_risk(unit["id"], r_date, None if r_date else (date_from.isoformat() if date_from else qctx.date_from),
                                     None if r_date else (date_to.isoformat() if date_to else qctx.date_to))
    block = rc.risk_context_block(record, None if record else _no_risk_reason(lookup, unit, qctx.geography_status), lookup)

    # ---- ML forecast (a separate provenance: never merged into risk_context; null unless a valid prediction exists for the area)
    ml_block = rc.ml_prediction_block(unit_predictions(unit["id"])) if unit else None

    # ---- documentary evidence (existing RAG retrieval; filters relaxed only for inferred, narrowing ones)
    attempts = plan_filters(unit=unit, province=prov, province_text=province if basis == "explicit_province_unresolved" else None,
                            event_types=qctx.event_types, date_from=d_from, date_to=d_to, source=source)
    result, used = {"records": [], "items": [], "retrieval": {"mode": mode, "method": None, "min_score": None, "embedding_model": None}}, attempts[-1]
    for attempt in attempts:
        result = retrieve_evidence(q, SearchFilters(**attempt["filters"]), mode, top_k, min_score)
        used = attempt
        if result["records"]:
            break
    records, items = result["records"], result["items"]
    retrieval = {"mode": mode, "method": result["retrieval"]["method"], "evidence_count": len(records), "top_k": top_k,
                 "filters_requested": attempts[0]["filters"], "filters_applied": used["filters"], "filters_relaxed": used["relaxed"],
                 "min_score": result["retrieval"]["min_score"], "embedding_model": result["retrieval"]["embedding_model"],
                 "relevance": result["retrieval"].get("relevance"),
                 "note": DOC_NOTE + (" Inferred filters were relaxed because the stricter search found nothing." if used["relaxed"] else "")}
    ctx = IntelligenceContext(q, qd, block, records, retrieval, ml_block)

    def body(status, answer=None, outcome=None, model=None, cites=()):
        v = outcome.validation if outcome else None
        judged = v is not None and status in (g.ANSWERED, g.INVALID)
        citations = [{"kind": "documentary", "chunk_id": e["chunk_id"], "document_id": e["document_id"], "title": e["title"], "source": e["source"],
                      "document_date": e["document_date"], "source_reference": e["source_reference"]} for e in records if e["chunk_id"] in cites]
        if status == g.ANSWERED and answer and rc.CITATION_TAG in answer and record:
            citations.append({"kind": "risk_engine", "admin_unit_id": record["admin_unit_id"], "risk_date": record["risk_date"],
                              "calculation_version": record["calculation_version"]})
        if status == g.ANSWERED and answer and rc.ML_CITATION_TAG in answer and ml_block:
            citations.append({"kind": "ml_prediction", "model_run_ids": sorted({p["model_run_id"] for p in ml_block["predictions"]})})
        d = ctx.to_dict()
        return {**d, "status": status, "answer": answer, "citations": citations,
                "model": model or {"provider": None, "model": None, "configured": False, "called": False},
                "groundedness": {"citations_valid": (not any(p["code"] in ("unknown_citation", "no_citations", "mixed_provenance_sentence",
                                                                           "engine_citation_without_risk_context", "ml_citation_without_prediction") for p in v.problems)) if judged else None,
                                 "risk_context_supplied": block["status"] == rc.AVAILABLE, "evidence_supplied": len(records),
                                 "evidence_cited": len([c for c in citations if c["kind"] == "documentary"]),
                                 "problems": v.problems if v else [], "warnings": v.warnings if v else [],
                                 "rejected_answer_text": outcome.raw_answer if outcome and status == g.INVALID else None,
                                 "validation_note": VALIDATION_NOTE},
                "disclaimer": DISCLAIMER + " Computed risk context and documentary evidence are separate; documents are not risk-engine inputs."}

    terminal = status_before_generation(risk_available=block["status"] == rc.AVAILABLE, risk_intent=qctx.risk_intent, evidence_count=len(records),
                                       ml_available=ml_block is not None)
    if terminal:
        return body(terminal), 200
    try:
        provider = get_llm_provider()
    except LLMUnavailable as exc:
        return body(g.LLM_UNAVAILABLE, model={"provider": None, "model": None, "configured": False, "error": str(exc), "called": False}), 503
    outcome = answer_intelligence(q, rc.risk_prompt_item(block), items, provider, constraints_from_env(), rc.ml_prompt_item(ml_block))
    model = {"provider": outcome.provider or getattr(provider, "name", None), "model": outcome.model or getattr(provider, "model", None),
             "configured": True, "error": outcome.llm_error, "called": True}
    if outcome.status == g.LLM_UNAVAILABLE:
        return body(g.LLM_UNAVAILABLE, outcome=outcome, model=model), 503
    return body(outcome.status, outcome.answer, outcome, model, outcome.validation.citations if outcome.status == g.ANSWERED else ()), 200
