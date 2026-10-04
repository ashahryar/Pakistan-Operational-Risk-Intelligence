"""Task 34 -- tool execution. The executor is the ONLY place a tool handler runs, and it only runs what validated.

Handlers are injected (`backends`: tool name -> callable(arguments) -> {"status", "result", "reason"}), so this module imports nothing from the API or the
database layer and can be tested with fakes. A handler is never handed a database connection, a query string, a path or a URL: only the validated,
typed arguments of its own tool. A handler exception is recorded as ERROR (never swallowed into an empty success).
"""

from __future__ import annotations

import time
from typing import Callable, Mapping

from pipeline.agents import contracts as C
from pipeline.agents.tools import TOOLS, provenance_for, validate_call

Backend = Callable[[dict], dict]


class ToolExecutor:
    def __init__(self, backends: Mapping[str, Backend], clock: Callable[[], float] = time.perf_counter):
        unknown = set(backends) - set(TOOLS)
        if unknown:
            raise ValueError(f"backends for tools that are not in the allowlist: {sorted(unknown)}")
        self._backends = dict(backends)
        self._clock = clock

    def execute(self, call: C.PlannedCall) -> C.ToolResult:
        v = validate_call(call.tool, call.arguments)
        if not v.ok:
            return C.ToolResult(str(call.tool)[:60], _safe_args(call.arguments), C.TOOL_REJECTED, None, {"sources": []}, v.reason(), 0.0, call.origin)
        backend = self._backends.get(call.tool)
        if backend is None:
            return C.ToolResult(call.tool, v.arguments, C.TOOL_UNAVAILABLE, None, {"sources": [], "capability": call.tool},
                                "this tool has no backend in this deployment", 0.0, call.origin)
        t0 = self._clock()
        try:
            out = backend(dict(v.arguments))
            status = out.get("status", C.TOOL_OK)
            if status not in C.TOOL_STATUSES or status == C.TOOL_REJECTED:
                status, reason, result = C.TOOL_ERROR, f"backend returned an invalid status {status!r}", None
            else:
                reason, result = out.get("reason"), out.get("result")
        except Exception as exc:                                            # noqa: BLE001 -- recorded, never hidden
            status, reason, result = C.TOOL_ERROR, f"{type(exc).__name__}: {str(exc)[:200]}", None
        ms = round((self._clock() - t0) * 1000.0, 2)
        prov = provenance_for(call.tool, result) if status in (C.TOOL_OK, C.TOOL_EMPTY) else {"sources": [], "capability": call.tool}
        return C.ToolResult(call.tool, v.arguments, status, result, prov, reason, ms, call.origin)


def _safe_args(arguments) -> dict:
    """Arguments of a REJECTED call, kept for the trace but bounded and stringified so nothing unexpected is echoed at length."""
    if not isinstance(arguments, dict):
        return {"_invalid": str(arguments)[:120]}
    return {str(k)[:40]: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:120]) for k, v in list(arguments.items())[:12]}


def summarize(result: C.ToolResult) -> dict:
    """A small, non-sensitive summary of a result for the trace (the full payloads travel in the response blocks)."""
    r, tool = result.result, result.tool_name
    if result.status not in (C.TOOL_OK, C.TOOL_EMPTY) or r is None:
        return {}
    if tool == "rag.retrieve":
        return {"evidence_count": len(r.get("records", [])), "chunk_ids": [e["chunk_id"] for e in r.get("records", [])]}
    if tool in ("risk.latest", "risk.on_date", "risk.coverage"):
        rec = r.get("record")
        return {"record_found": rec is not None, "risk_date": rec["risk_date"] if rec else None, "risk_status": rec["risk_status"] if rec else None}
    if tool == "risk.history":
        return {"records": len(r.get("records", []))}
    if tool == "ml.predictions":
        rows = r.get("predictions", [])
        return {"rows": len(rows), "status_counts": {s: sum(1 for x in rows if x["status"] == s) for s in ("PREDICTED", "BASELINE_ONLY", "INSUFFICIENT_DATA")}}
    if tool == "ml.models":
        return {"models": len(r.get("models", []))}
    if tool.startswith("geography."):
        return {k: r.get(k) for k in ("status", "count") if k in r} | ({"admin_unit_id": r["unit"]["id"]} if isinstance(r.get("unit"), dict) and "id" in r["unit"] else {})
    if tool == "intelligence.ask":
        return {"status": r.get("status"), "evidence_count": len(r.get("documentary_evidence", [])), "risk_context": (r.get("risk_context") or {}).get("status"),
                "ml_prediction": r.get("ml_prediction") is not None}
    return {}
