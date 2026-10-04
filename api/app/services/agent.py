"""Task 34 -- the agent's tool backends: thin, read-only adapters from the closed tool allowlist onto EXISTING services.

Nothing is calculated, ranked or inferred here. Each backend takes the validated typed arguments of its own tool and calls an existing service function
(geography / risk serving / RAG retrieval / ML predictions / intelligence). No backend receives or builds arbitrary SQL, a path or a URL, and none writes.
The orchestration itself (policy, routing, tool execution, assembly, grounded generation, trace) lives in the pure package pipeline/agents.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException

from api.app.db import fetch_all
from api.app.services import geography as geo_service
from api.app.services.intelligence import ask_intelligence, load_units, lookup_risk
from api.app.services.ml import list_models, list_predictions
from api.app.services.rag import get_llm_provider, retrieve_evidence
from api.app.services.risk_serving import _COLS, _shape
from pipeline.agents import geography
from pipeline.agents.contracts import TOOL_ERROR, TOOL_OK, TOOL_EMPTY, TOOL_UNAVAILABLE, AgentRequest
from pipeline.agents.executor import ToolExecutor
from pipeline.agents.orchestrator import AgentDeps, run_agent
from pipeline.rag.llm import constraints_from_env
from pipeline.rag.retrieval import SearchFilters


def _guard(fn):
    """HTTP errors raised by the underlying services become explicit tool statuses (never an empty success)."""
    def wrapped(args: dict) -> dict:
        try:
            return fn(args)
        except HTTPException as exc:
            return {"status": TOOL_UNAVAILABLE if exc.status_code == 503 else TOOL_ERROR, "reason": f"{exc.status_code}: {exc.detail}"}
    return wrapped


@_guard
def resolve_place(args: dict) -> dict:
    return {"status": TOOL_OK, "result": geography.resolve_place(args["text"], load_units())}


@_guard
def get_admin_unit(args: dict) -> dict:
    rows = fetch_all("SELECT u.id, u.name, u.level, u.parent_id, CASE WHEN u.level = 1 THEN u.name ELSE p.name END AS province, "
                     "(cb.pori_admin_unit_id IS NOT NULL) AS has_geometry, cb.boundary_source "
                     "FROM geo.admin_unit u LEFT JOIN geo.admin_unit p ON p.id = u.parent_id AND p.level = 1 "
                     "LEFT JOIN geo.current_boundary cb ON cb.pori_admin_unit_id = u.id WHERE u.id = :id", {"id": args["admin_unit_id"]})
    if not rows or rows[0]["level"] not in (1, 2):
        return {"status": TOOL_EMPTY, "reason": f"admin_unit_id {args['admin_unit_id']} is not a province or district in geo.admin_unit"}
    return {"status": TOOL_OK, "result": {"status": "resolved", "unit": rows[0]}}


@_guard
def list_units(args: dict) -> dict:
    rows = geo_service.list_admin_unit_summaries(args.get("level"), args.get("province"), args.get("limit", 200))
    return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": {"count": len(rows), "units": rows}, "reason": None if rows else "no canonical unit matches"}


@_guard
def risk_latest(args: dict) -> dict:
    record, lookup = lookup_risk(args["admin_unit_id"], None, None, None)
    return {"status": TOOL_OK if record else TOOL_EMPTY, "result": {"record": record, "lookup": lookup, "reason": None if record else "no risk record exists for this area"}}


@_guard
def risk_on_date(args: dict) -> dict:
    record, lookup = lookup_risk(args["admin_unit_id"], args["date"], None, None)
    return {"status": TOOL_OK if record else TOOL_EMPTY,
            "result": {"record": record, "lookup": lookup, "reason": None if record else f"no risk record exists for this area on {args['date']} (no other date is substituted)"}}


@_guard
def risk_history(args: dict) -> dict:
    a = date.fromisoformat(args["date_from"]) if args.get("date_from") else None
    b = date.fromisoformat(args["date_to"]) if args.get("date_to") else None
    rows = fetch_all(f"SELECT {_COLS} FROM risk.operational_risk WHERE is_current AND admin_unit_id = :u "
                     "AND (CAST(:a AS date) IS NULL OR risk_date >= :a) AND (CAST(:b AS date) IS NULL OR risk_date <= :b) ORDER BY risk_date DESC LIMIT :n",
                     {"u": args["admin_unit_id"], "a": a, "b": b, "n": args.get("limit", 31)})
    recs = [_shape(r) for r in rows]
    lookup = {"basis": "window", "admin_unit_id": args["admin_unit_id"], "date_from": args.get("date_from"), "date_to": args.get("date_to")}
    return {"status": TOOL_OK if recs else TOOL_EMPTY, "result": {"records": recs, "lookup": lookup, "reason": None if recs else "no risk record in the requested window"}}


@_guard
def risk_coverage(args: dict) -> dict:
    record, lookup = lookup_risk(args["admin_unit_id"], None, None, None)
    if not record:
        return {"status": TOOL_EMPTY, "result": {"record": None, "coverage": None, "lookup": lookup}, "reason": "no risk record exists for this area"}
    cov = {k: record.get(k) for k in ("risk_date", "risk_status", "risk_confidence", "data_coverage_pct", "observed_signal_count", "missing_signal_count",
                                      "active_signal_count", "source_count", "source_record_count", "threshold_status", "calculation_version")}
    return {"status": TOOL_OK, "result": {"record": record, "coverage": cov, "lookup": lookup}}


@_guard
def rag_retrieve(args: dict) -> dict:
    f = SearchFilters(source=args.get("source"), province=args.get("province"), admin_unit_id=args.get("admin_unit_id"), event_type=args.get("event_type"),
                      date_from=args.get("date_from"), date_to=args.get("date_to"))
    out = retrieve_evidence(args["query"], f, args.get("mode", "hybrid"), args.get("top_k", 5))
    out["filters_applied"] = {k: v for k, v in f.__dict__.items() if v is not None}
    return {"status": TOOL_OK if out["records"] else TOOL_EMPTY, "result": out, "reason": None if out["records"] else "no document passage matched these filters"}


@_guard
def ml_predictions(args: dict) -> dict:
    uid = args["admin_unit_id"]
    rows = list_predictions(uid, None, args.get("horizon"), None, True, 50)
    result = {"predictions": rows}
    if args.get("horizon") and not rows:
        result["available_horizons"] = sorted({r["horizon_days"] for r in list_predictions(uid, None, None, None, True, 50)})
    return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": result, "reason": None if rows else "the ML layer holds no prediction row for this area/horizon"}


@_guard
def ml_models(args: dict) -> dict:
    rows = list_models()
    return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": {"models": rows}}


@_guard
def intelligence_ask(args: dict) -> dict:
    d = date.fromisoformat(args["date"]) if args.get("date") else None
    body, _http = ask_intelligence(args["question"], args.get("admin_unit_id"), None, d, None, None, None, args.get("mode", "hybrid"), args.get("top_k", 5), None)
    return {"status": TOOL_OK, "result": body}


BACKENDS = {"geography.resolve_place": resolve_place, "geography.get_admin_unit": get_admin_unit, "geography.list_units": list_units, "risk.latest": risk_latest,
            "risk.on_date": risk_on_date, "risk.history": risk_history, "risk.coverage": risk_coverage, "rag.retrieve": rag_retrieve, "ml.predictions": ml_predictions,
            "ml.models": ml_models, "intelligence.ask": intelligence_ask}


def make_deps() -> AgentDeps:
    return AgentDeps(executor=ToolExecutor(BACKENDS), provider_factory=get_llm_provider, constraints_factory=constraints_from_env)


def ask_agent(q: str, admin_unit_id: Optional[int], risk_date: Optional[date], mode: str, routing: str, top_k: int) -> tuple[dict, int]:
    req = AgentRequest(q=q, admin_unit_id=admin_unit_id, date=risk_date.isoformat() if risk_date else None, mode=mode, routing=routing, top_k=top_k)
    return run_agent(req, make_deps())
