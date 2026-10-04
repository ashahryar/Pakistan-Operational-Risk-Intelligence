"""Task 34 -- the structured audit trace of one agent execution.

Records: the request, the guardrail decision, the analysis and resolved intent, the routing method, the planned and validated tool calls, every tool
status with its provenance, the generation outcome and the final status, with timestamps from the injected clock. It never contains an API key, a
credential or a prompt; a model's raw routing text is only kept as a short redacted excerpt when it could not be parsed.

Reproducibility: `plan_fingerprint` is a SHA-256 over (request without timestamps, resolved intent, validated tool calls). `replay_plan(trace, executor)`
re-executes exactly the recorded validated calls, so a deterministic run can be repeated from its trace alone.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Optional

from pipeline.agents import contracts as C
from pipeline.agents.executor import summarize


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(request: dict, intent: Optional[str], plan: list) -> str:
    canonical = json.dumps({"request": request, "intent": intent, "plan": [{"tool_name": p["tool_name"], "arguments": p["arguments"]} for p in plan]},
                           sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Trace:
    def __init__(self, request: C.AgentRequest, now: Callable[[], datetime] = utcnow):
        self._now = now
        self.started_at = now()
        self.request = request.to_dict()
        self.policy: dict = {"allowed": True}
        self.analysis: dict = {}
        self.routing: dict = {"method": "deterministic", "requested": request.routing}
        self.plan: list = []                   # validated calls that were (or would have been) executed, in order
        self.tool_calls: list = []
        self.generation: dict = {"attempted": False}
        self.intent: Optional[str] = None
        self.status: Optional[str] = None
        self.status_reason: Optional[str] = None
        self.notes: list = []

    def add_tool(self, result: C.ToolResult) -> None:
        d = result.to_dict(include_result=False)
        d["result_summary"] = summarize(result)
        self.tool_calls.append(d)
        if result.status != C.TOOL_REJECTED:
            self.plan.append({"tool_name": result.tool_name, "arguments": result.arguments, "origin": result.origin})

    def finish(self, status: str, reason: Optional[str] = None) -> dict:
        self.status, self.status_reason = status, reason
        return self.to_dict()

    def to_dict(self) -> dict:
        end = self._now()
        return {"agent_version": C.AGENT_VERSION, "request": self.request, "started_at": self.started_at.isoformat(), "finished_at": end.isoformat(),
                "policy": self.policy, "analysis": self.analysis, "intent": self.intent, "routing": self.routing, "plan": self.plan, "tool_calls": self.tool_calls,
                "generation": self.generation, "final_status": self.status, "status_reason": self.status_reason, "notes": self.notes,
                "plan_fingerprint": fingerprint(self.request, self.intent, self.plan)}


def replay_plan(trace: dict, executor) -> list[C.ToolResult]:
    """Re-execute the validated calls recorded in a trace (same arguments, same order) with the given executor."""
    return [executor.execute(C.PlannedCall(p["tool_name"], p["arguments"], p.get("origin", "deterministic"))) for p in trace["plan"]]
