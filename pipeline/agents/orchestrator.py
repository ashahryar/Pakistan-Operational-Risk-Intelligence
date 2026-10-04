"""Task 34 -- the agent's control flow. A fixed pipeline, not an autonomous loop:

  guardrails -> analysis/intent -> geography (mandatory, deterministic) -> plan (deterministic, or LLM-proposed and validated) -> execute allowlisted
  read-only tools -> assemble separate provenance-labelled blocks -> (only with a real provider) generate through the EXISTING Task 32 grounding
  (`answer_intelligence`: citation validation, risk/ML/document separation) -> structured response + audit trace.

The agent never queries data itself, never writes, never calls itself, and never produces a natural-language answer that a real model did not write and the
existing validator accept. Without a provider the status is LLM_UNAVAILABLE and the structured tool results are returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from pipeline.agents import assembly as A
from pipeline.agents import contracts as C
from pipeline.agents import llm_router, router
from pipeline.agents.contracts import AgentRequest, PlannedCall, ToolResult
from pipeline.agents.executor import ToolExecutor
from pipeline.agents.policy import check_request
from pipeline.agents.trace import Trace, utcnow
from pipeline.intelligence import risk_context as rc
from pipeline.intelligence.assembly import plan_filters
from pipeline.intelligence.grounding import answer_intelligence
from pipeline.rag import grounding as g
from pipeline.rag.llm import GenerationConstraints, LLMUnavailable

DOC_NOTE = "Documentary evidence = passages of NDMA / PDMA / PMD / FFC reports. They describe conditions; they are not risk-engine inputs."


@dataclass
class AgentDeps:
    executor: ToolExecutor
    provider_factory: Callable[[], object]                   # raises LLMUnavailable when no real provider is configured
    constraints_factory: Callable[[], GenerationConstraints] = GenerationConstraints
    now: Callable[[], datetime] = utcnow


def _empty_response(req: AgentRequest, trace: Trace, status: str, reason: Optional[str], intent: Optional[str], **extra) -> dict:
    t = trace.finish(status, reason)
    body = {"question": req.q, "status": status, "status_reason": reason, "reason_code": extra.pop("reason_code", None), "intent": intent, "answer": None, "geography": extra.pop("geography", None),
            "risk_context": None, "risk_history": None, "documentary_evidence": [], "retrieval": None, "ml_prediction": None, "components": {}, "premise_check": None,
            "tool_trace": t["tool_calls"], "citations": [], "model": {"provider": None, "model": None, "configured": False},
            "groundedness": None, "provenance": A.provenance_block(geography=None, risk_block=None, records=[], ml_block=None, tool_trace=t["tool_calls"]),
            "policy": t["policy"], "trace": t, "disclaimer": C.DISCLAIMER}
    body.update(extra)
    return body


def _first(results: list, *names: str) -> Optional[ToolResult]:
    return next((r for r in results if r.tool_name in names), None)


def _geo_block(res: Optional[ToolResult]) -> Optional[dict]:
    if res is None or res.result is None:
        return None
    r = res.result
    return {"provenance": C.GEOGRAPHY, "status": r.get("status"), "unit": r.get("unit"), "province": r.get("province"), "mentions": r.get("mentions", []),
            "candidates": r.get("candidates", []), "unrecognized_places": r.get("unrecognized_places", []), "notes": r.get("notes", []), "basis": r.get("basis")}


def run_agent(req: AgentRequest, deps: AgentDeps) -> tuple[dict, int]:
    """-> (response body, HTTP status). 503 only for LLM_UNAVAILABLE (the structured results are still in the body); everything else is 200."""
    trace = Trace(req, deps.now)
    executed: list[ToolResult] = []

    def run(call: PlannedCall) -> ToolResult:
        res = deps.executor.execute(call)
        trace.add_tool(res)
        executed.append(res)
        return res

    # ---------------------------------------------------------------------------------------------------------------------- 1. guardrails
    pol = check_request(req.q)
    trace.policy = pol.to_dict()
    if not pol.allowed:
        trace.intent = C.UNSUPPORTED
        return _empty_response(req, trace, C.UNSUPPORTED_REQUEST, pol.message, C.UNSUPPORTED, reason_code=pol.code), 200

    # ------------------------------------------------------------------------------------------------------------------ 2. analysis / intent
    a = router.analyze(req.q, req.date)
    trace.analysis = a.to_dict()
    trace.intent = a.intent
    trace.routing["deterministic_intent"] = a.intent
    if a.intent == C.UNSUPPORTED:
        return _empty_response(req, trace, C.UNSUPPORTED_REQUEST, a.reason, C.UNSUPPORTED, reason_code="NO_SUPPORTED_INTENT"), 200

    # ----------------------------------------------------------------------------- 3. geography (mandatory, deterministic, never model-chosen)
    geo_res = None
    unit = province = None
    wants_geo = router.needs_unit(a.intent) or a.intent in (C.DOCUMENT_SEARCH, C.GEOGRAPHY_LOOKUP)
    if wants_geo:
        if req.admin_unit_id is not None:
            geo_res = run(PlannedCall("geography.get_admin_unit", {"admin_unit_id": req.admin_unit_id}, "agent"))
            if geo_res.status != C.TOOL_OK or not (geo_res.result or {}).get("unit"):
                return _empty_response(req, trace, C.UNSUPPORTED_REQUEST, geo_res.reason or f"admin_unit_id {req.admin_unit_id} is not a province or district",
                                       a.intent, reason_code="GEOGRAPHY_NOT_RESOLVED"), 200
            u = geo_res.result["unit"]
            unit = {"id": u["id"], "level": u["level"], "name": u["name"], "province": u.get("province") or u["name"]}
            province = ({"id": u["id"], "name": u["name"]} if u["level"] == 1 else
                        ({"id": u["parent_id"], "name": u["province"]} if u.get("parent_id") else None))
            geo_res.result["basis"] = "explicit_admin_unit_id"
        else:
            geo_res = run(PlannedCall("geography.resolve_place", {"text": req.q}, "agent"))
            if geo_res.status != C.TOOL_OK:
                return _empty_response(req, trace, C.INSUFFICIENT_DATA, f"geography resolution failed: {geo_res.reason}", a.intent, geography=_geo_block(geo_res)), 200
            r = geo_res.result
            r["basis"] = "question_text"
            if r["status"] in ("ambiguous", "multiple"):
                return _empty_response(req, trace, C.AMBIGUOUS_GEOGRAPHY, "; ".join(r.get("notes") or []) or "the place name is ambiguous; no area was guessed", a.intent,
                                       geography=_geo_block(geo_res), reason_code="AMBIGUOUS_GEOGRAPHY"), 200
            if r.get("unit"):
                unit, province = r["unit"], r.get("province")
            elif a.intent != C.DOCUMENT_SEARCH:
                missing = r.get("unrecognized_places")
                if not (a.intent == C.GEOGRAPHY_LOOKUP and not missing and router.asks_for_provinces(a.question)):
                    msg = (f"the place {', '.join(repr(m) for m in missing)} is not a province or district known to the canonical geography; no area was inferred"
                           if missing else "no province or district was identified in the question (name one, or pass admin_unit_id)")
                    return _empty_response(req, trace, C.UNSUPPORTED_REQUEST, msg, a.intent, geography=_geo_block(geo_res),
                                           reason_code="GEOGRAPHY_NOT_RESOLVED" if missing or r["status"] == "unresolved" else "GEOGRAPHY_REQUIRED"), 200
        if unit is not None and r_unrecognized(geo_res):
            trace.notes.append("other place names in the question were not recognised and were ignored: " + ", ".join(geo_res.result["unrecognized_places"]))

    # ------------------------------------------------------------------------------------------------------------------------- 4. plan
    plan = router.build_plan(a, unit, province, req.mode, req.top_k, explicit_unit=req.admin_unit_id is not None)
    intent = a.intent
    provider = None
    if req.routing == "auto":
        try:
            provider = deps.provider_factory()
        except LLMUnavailable as exc:
            trace.routing["llm"] = {"available": False, "reason": str(exc)[:160]}
    if provider is not None:
        grounded = {"admin_unit_ids": [unit["id"]] if unit else [], "dates": [d for d in (a.date, a.date_from, a.date_to) if d]}
        llm_plan, info = llm_router.propose_plan(provider, deps.constraints_factory(), req.q, grounded)
        trace.routing["llm"] = {"available": True, **(info or {})}
        if llm_plan is None:
            trace.routing["fallback"] = "provider failure during routing; the deterministic plan is used"
        else:
            trace.routing["llm_plan"] = llm_plan.to_dict()
            if not llm_plan.ok:
                trace.routing["method"] = "llm"
                for rj in llm_plan.rejected:
                    rr = ToolResult(rj.get("tool_name") or "?", rj.get("arguments") or {}, C.TOOL_REJECTED, None, {"sources": []},
                                    "; ".join(e["code"] + (f" ({e['argument']})" if e.get("argument") else "") for e in rj["errors"]), 0.0, "llm")
                    trace.add_tool(rr)
                    executed.append(rr)
                reason = llm_plan.parse_error or "a model-proposed tool call failed validation and was not executed"
                return _empty_response(req, trace, C.INVALID_TOOL_CALL, reason, llm_plan.intent or intent, geography=_geo_block(geo_res), reason_code="INVALID_TOOL_CALL"), 200
            trace.routing["method"] = "llm"
            if llm_plan.intent == C.UNSUPPORTED:
                return _empty_response(req, trace, C.UNSUPPORTED_REQUEST, llm_plan.reason or "the routing model judged the request unsupported", C.UNSUPPORTED,
                                       geography=_geo_block(geo_res), reason_code="MODEL_DECLINED"), 200
            plan, intent = llm_plan.calls, llm_plan.intent
            trace.intent = intent
    trace.routing["final_intent"] = intent

    # ----------------------------------------------------------------------------------------------------------------------- 5. execute
    relaxed: list = []
    filters_requested = filters_applied = None
    for call in plan:
        if call.tool == "rag.retrieve" and call.origin == "deterministic":
            res, relaxed, filters_requested, filters_applied = _retrieve_with_relaxation(run, call, a, unit, province, req)
        else:
            run(call)
    tool_results = [r for r in executed if r.origin != "agent"]
    if not plan:
        return _empty_response(req, trace, C.UNSUPPORTED_REQUEST, "no tool call is needed or possible for this question", intent, geography=_geo_block(geo_res),
                               reason_code="NO_PLAN"), 200

    # ------------------------------------------------------------------------------------------------------------------------ 6. assemble
    intel = _first(tool_results, "intelligence.ask")
    body_intel = intel.result if intel and intel.status == C.TOOL_OK else None
    risk_res = _first(tool_results, "risk.latest", "risk.on_date")
    hist_res = _first(tool_results, "risk.history")
    cov_res = _first(tool_results, "risk.coverage")
    rag_res = [r for r in tool_results if r.tool_name == "rag.retrieve"]
    rag_final = next((r for r in reversed(rag_res) if r.status == C.TOOL_OK), rag_res[-1] if rag_res else None)
    ml_res = _first(tool_results, "ml.predictions", "ml.models")

    risk_block, risk_history, records, retrieval, ml_block = None, None, [], None, None
    components: dict = {}
    if body_intel is not None:
        risk_block = body_intel["risk_context"]
        records = body_intel.get("documentary_evidence") or []
        retrieval = body_intel.get("retrieval")
        ml_raw = body_intel.get("ml_prediction")
        if ml_raw:
            ml_block, ml_comp = A.ml_components({"predictions": ml_raw["predictions"]})
        else:
            ml_block, ml_comp = None, {"status": "INSUFFICIENT_DATA", "reason": "no valid ML forecast exists for this area"}
        components = {"risk": {"status": risk_block["status"], "reason": risk_block.get("reason")},
                      "evidence": {"status": "AVAILABLE" if records else "NO_EVIDENCE", "count": len(records)}, "ml": ml_comp}
    else:
        if risk_res is not None:
            r = risk_res.result or {}
            risk_block = rc.risk_context_block(r.get("record"), r.get("reason") or (risk_res.reason if risk_res.status != C.TOOL_OK else None), r.get("lookup") or {})
        elif hist_res is not None:
            r = hist_res.result or {}
            recs = r.get("records") or []
            risk_history = recs
            risk_block = rc.risk_context_block(recs[0] if recs else None, None if recs else (r.get("reason") or hist_res.reason or "no risk record in the window"),
                                               r.get("lookup") or {})
        if risk_block is not None:
            components["risk"] = {"status": risk_block["status"], "reason": risk_block.get("reason")}
            if risk_res is not None and risk_res.status in (C.TOOL_UNAVAILABLE, C.TOOL_ERROR):
                components["risk"] = {"status": "UNAVAILABLE", "reason": risk_res.reason}
        if cov_res is not None and cov_res.result:
            components["risk_coverage"] = cov_res.result.get("coverage")
        if rag_final is not None:
            if rag_final.status == C.TOOL_OK:
                records = rag_final.result["records"]
                retrieval = {**rag_final.result["retrieval"], "evidence_count": len(records), "filters_requested": filters_requested or {}, "filters_applied": filters_applied or {},
                             "filters_relaxed": relaxed, "note": DOC_NOTE + (" Inferred filters were relaxed because the stricter search found nothing." if relaxed else "")}
                components["evidence"] = {"status": "AVAILABLE", "count": len(records)}
            elif rag_final.status == C.TOOL_EMPTY:
                retrieval = {"mode": req.mode, "evidence_count": 0, "filters_requested": filters_requested or {}, "filters_applied": filters_applied or {}, "filters_relaxed": relaxed, "note": DOC_NOTE}
                components["evidence"] = {"status": "NO_EVIDENCE", "count": 0}
            else:
                components["evidence"] = {"status": "UNAVAILABLE", "reason": rag_final.reason, "count": 0}
        if ml_res is not None:
            if ml_res.tool_name == "ml.models":
                models = (ml_res.result or {}).get("models") or []
                ml_block, ml_comp = A.ml_components({"predictions": [], "unsupported_target": (a.forecast_target or "").split(":", 1)[-1],
                                                     "targets": sorted({m["target"] for m in models})})
            elif ml_res.status in (C.TOOL_OK, C.TOOL_EMPTY):
                ml_block, ml_comp = A.ml_components({**(ml_res.result or {}), "horizon_requested": a.horizon})
            else:
                ml_block, ml_comp = None, {"status": "UNAVAILABLE", "reason": ml_res.reason}
            components["ml"] = ml_comp

    risk_record = (risk_block or {}).get("record")
    premise = router.premise_check(a.stated_status, risk_record)
    tool_trace = [t for t in trace.tool_calls]
    geo_block = _geo_block(geo_res)
    base = {"question": req.q, "intent": intent, "reason_code": None, "geography": geo_block, "risk_context": risk_block, "risk_history": risk_history, "documentary_evidence": records,
            "retrieval": retrieval, "ml_prediction": ml_block, "components": components, "premise_check": premise, "tool_trace": tool_trace, "policy": trace.policy,
            "provenance": A.provenance_block(geography=geo_block, risk_block=risk_block, records=records, ml_block=ml_block, tool_trace=tool_trace), "disclaimer": C.DISCLAIMER}

    def done(status, reason=None, answer=None, citations=(), model=None, groundedness=None, http=200):
        t = trace.finish(status, reason)
        return {**base, "status": status, "status_reason": reason, "answer": answer, "citations": list(citations),
                "model": model or {"provider": None, "model": None, "configured": False}, "groundedness": groundedness, "tool_trace": t["tool_calls"], "trace": t}, http

    # ------------------------------------------------------------------------------------------------------------ 7. status / generation
    if intent == C.GEOGRAPHY_LOOKUP:
        failed = [r for r in tool_results if r.status in (C.TOOL_UNAVAILABLE, C.TOOL_ERROR)]
        if failed:
            return done(C.INSUFFICIENT_DATA, f"the geography lookup failed: {failed[0].reason}")
        return done(C.COMPLETED, "geography lookup; no language generation is needed")
    if body_intel is not None:
        return _from_intelligence(body_intel, base, trace, done, records, risk_record, ml_block)
    if intel is not None:                                   # the intelligence tool itself failed / was unavailable
        return done(C.INSUFFICIENT_DATA, f"the intelligence service did not run: {intel.reason or intel.status}")

    f = a.facets
    planned = {c.tool for c in plan}
    llm_rag = any(c.tool == "rag.retrieve" and c.origin == "llm" for c in plan)
    required = {"risk": bool(planned & {"risk.latest", "risk.on_date", "risk.history"}), "ml": bool(planned & {"ml.predictions", "ml.models"}),
                "evidence": "rag.retrieve" in planned and (f["docs"] or intent == C.DOCUMENT_SEARCH or llm_rag)}
    missing = [k for k, need in required.items() if need and components.get(k, {}).get("status") not in ("AVAILABLE", "PREDICTED", "BASELINE_ONLY")]
    if missing:
        only_docs = missing == ["evidence"] and not (required["risk"] or required["ml"])
        unavailable = any(components.get(k, {}).get("status") == "UNAVAILABLE" for k in missing)
        why = "; ".join(f"{k}: {components.get(k, {}).get('reason') or components.get(k, {}).get('status')}" for k in missing)
        return done(C.NO_EVIDENCE if (only_docs and not unavailable) else C.INSUFFICIENT_DATA, f"requested information is not available ({why})")

    try:
        provider = provider or deps.provider_factory()
    except LLMUnavailable as exc:
        return done(C.LLM_UNAVAILABLE, "no real language model is configured; the structured tool results are returned and no answer was generated",
                    model={"provider": None, "model": None, "configured": False, "error": str(exc)}, http=503)
    items = (rag_final.result["items"] if rag_final is not None and rag_final.status == C.TOOL_OK else [])
    risk_item = rc.risk_prompt_item(risk_block) if risk_block else None
    ml_item = rc.ml_prompt_item(ml_block)
    trace.generation = {"attempted": True, "provider": getattr(provider, "name", None), "model": getattr(provider, "model", None)}
    outcome = answer_intelligence(req.q, risk_item, items, provider, deps.constraints_factory(), ml_item)
    model = {"provider": outcome.provider or getattr(provider, "name", None), "model": outcome.model or getattr(provider, "model", None), "configured": True,
             "error": outcome.llm_error}
    trace.generation.update(status=outcome.status, error=outcome.llm_error)
    v = outcome.validation
    judged = outcome.status in (g.ANSWERED, g.INVALID)
    groundedness = {"citations_valid": (not any(p["code"] in ("unknown_citation", "no_citations", "mixed_provenance_sentence", "engine_citation_without_risk_context",
                                                              "ml_citation_without_prediction") for p in v.problems)) if judged else None,
                    "risk_context_supplied": risk_record is not None, "evidence_supplied": len(records), "ml_forecast_supplied": ml_block is not None,
                    "problems": v.problems, "warnings": v.warnings, "rejected_answer_text": outcome.raw_answer if outcome.status == g.INVALID else None,
                    "validation_note": "Existing deterministic provenance validation (Task 31/32/33 rules): citations must be supplied chunks, [risk_engine] only with an engine "
                                       "record, [ml_prediction] only as a forecast, never mixed, no risk status attributed to a document. Heuristic wording checks, not fact checking."}
    if outcome.status == g.LLM_UNAVAILABLE:
        return done(C.LLM_UNAVAILABLE, outcome.llm_error or "the language model did not respond", model=model, groundedness=groundedness, http=503)
    if outcome.status == g.ANSWERED:
        return done(C.ANSWERED, None, outcome.answer, A.citations_for(records, v.citations, outcome.answer, risk_record, ml_block), model, groundedness)
    if outcome.status == g.INSUFFICIENT:
        return done(C.INSUFFICIENT_EVIDENCE, "the model reported that the supplied information does not answer the question", model=model, groundedness=groundedness)
    return done(C.INVALID_ANSWER, "the generated answer failed the grounding validation and was withheld", model=model, groundedness=groundedness)


def r_unrecognized(geo_res: Optional[ToolResult]) -> bool:
    return bool(geo_res and geo_res.result and geo_res.result.get("unrecognized_places"))


def _from_intelligence(body_intel: dict, base: dict, trace: Trace, done, records, risk_record, ml_block):
    """The existing intelligence service produced the answer (or its own terminal status); map it onto the agent statuses without re-validating."""
    st = body_intel["status"]
    model = body_intel.get("model") or {"provider": None, "model": None, "configured": False}
    trace.generation = {"attempted": st not in ("NO_RISK_CONTEXT", "RETRIEVAL_EMPTY"), "provider": model.get("provider"), "model": model.get("model"), "status": st,
                        "error": model.get("error"), "via": "intelligence.ask"}
    grounded = body_intel.get("groundedness")
    cites = []
    for c in body_intel.get("citations") or []:
        c = dict(c)
        if c["kind"] == "documentary":
            c["provenance"] = C.RAG_DOCUMENT
        elif c["kind"] == "risk_engine":
            c["provenance"] = C.RISK_ENGINE
        elif c["kind"] == "ml_prediction" and ml_block:
            c["attributions"] = ml_block["attributions"]
            c["provenance"] = "+".join(ml_block["attributions"])
        cites.append(c)
    if st == "ANSWERED":
        return done(C.ANSWERED, None, body_intel["answer"], cites, model, grounded)
    if st == "LLM_UNAVAILABLE":
        return done(C.LLM_UNAVAILABLE, "no real language model is configured or it did not respond; the structured results are returned and no answer was generated",
                    model=model, groundedness=grounded, http=503)
    if st == "NO_RISK_CONTEXT":
        return done(C.INSUFFICIENT_DATA, (body_intel["risk_context"] or {}).get("reason") or "no risk-engine record exists for this question", model=model, groundedness=grounded)
    if st == "RETRIEVAL_EMPTY":
        return done(C.INSUFFICIENT_DATA, "no risk context, no documentary evidence and no ML forecast were found", model=model, groundedness=grounded)
    if st == "INSUFFICIENT_EVIDENCE":
        return done(C.INSUFFICIENT_EVIDENCE, "the model reported that the supplied information does not answer the question", model=model, groundedness=grounded)
    return done(C.INVALID_ANSWER, "the generated answer failed the grounding validation and was withheld", model=model, groundedness=grounded)


def _retrieve_with_relaxation(run, call: PlannedCall, a: router.Analysis, unit, province, req: AgentRequest):
    """Run rag.retrieve; if the strictest filters find nothing, relax INFERRED filters in the existing Task 32 order (event_type -> district_to_province -> date).
    Every attempt is a separate, recorded tool call. Geography (province at least) and `source` are never dropped."""
    args = call.arguments
    attempts = plan_filters(unit=unit, province=province, province_text=None, event_types=a.events,
                            date_from=args.get("date_from"), date_to=args.get("date_to"), source=args.get("source"))
    res, used = None, attempts[0]
    for attempt in attempts:
        full = {"query": args["query"], "mode": args.get("mode", "hybrid"), "top_k": args.get("top_k", 5), **attempt["filters"]}
        res = run(PlannedCall("rag.retrieve", full, call.origin))
        used = attempt
        if res.status != C.TOOL_EMPTY:
            break
    return res, used["relaxed"], attempts[0]["filters"], used["filters"]
