"""Task 34 -- DEVELOPMENT evaluation of the read-only operational intelligence agent on the real local data (config/agent_eval.yaml, frozen before it was run).

Everything runs in process against the real services (risk serving, RAG lexical retrieval, ML predictions, geography) with NO language model:
  * routing accuracy        resolved intent == expected intent
  * tool-selection accuracy executed tool names (agent geography step included) == the expected ordered list
  * status / abstention     expected status; refusals, ambiguity and data gaps must return NO risk record / forecast / evidence / answer
  * provenance correctness  per tool result and per response block (RISK_ENGINE / RAG_DOCUMENT / ML_MODEL / BASELINE_MODEL / GEOGRAPHY), the risk record equals an
                            INDEPENDENT SQL read, ML row statuses equal an independent SQL read of ml.predictions
  * invalid-call rejection  a fixed battery of dangerous / malformed tool calls and model-proposed plans: every one must be rejected and NO backend may run
  * grounding validation    a SCRIPTED provider (not a model) returns correct and incorrect answers built from the REAL returned records; the EXISTING Task 31-33
                            validator must accept the separated answer and withhold every wrong one
  * false-premise handling  the question asserts a wrong risk status; the engine value (independent SQL) must be the one returned and flagged
  * reproducibility         each supported case is run twice; the trace plan fingerprints must be identical
These measure the agent's orchestration and OUR validation, not whether a real model routes or explains well (no credential was available).
Report: data/analytics/agent/agent_eval_report.json

Usage: python scripts/agents/evaluate_agent.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from pipeline.agents import contracts as C  # noqa: E402
from pipeline.agents import llm_router  # noqa: E402
from pipeline.agents.executor import ToolExecutor  # noqa: E402
from pipeline.agents.orchestrator import AgentDeps, run_agent  # noqa: E402
from pipeline.rag.llm import LLMResult, LLMUnavailable  # noqa: E402

CONFIG = PROJECT_ROOT / "config" / "agent_eval.yaml"
REPORT = PROJECT_ROOT / "data" / "analytics" / "agent" / "agent_eval_report.json"
FIXED_PROVENANCE = {"geography": {C.GEOGRAPHY}, "risk": {C.RISK_ENGINE}, "rag": {C.RAG_DOCUMENT}}


class Scripted:
    """A scripted stand-in for a language model (NOT a model): returns the given texts in order, the last one repeating."""
    name, model = "scripted", "scripted-eval"

    def __init__(self, *texts):
        self.texts, self.calls = list(texts), 0

    def generate(self, system, question, evidence, constraints):
        t = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return LLMResult(t, self.name, self.model)


def no_llm():
    raise LLMUnavailable("no LLM provider is configured")


def independent_risk(conn, unit_name: str, risk_date: Optional[str]) -> Optional[dict]:
    if risk_date:
        sql = ("SELECT admin_unit_id, risk_date::text AS risk_date, risk_status, calculation_version FROM risk.operational_risk r JOIN geo.admin_unit u ON u.id = r.admin_unit_id "
               "WHERE r.is_current AND u.name = :n AND r.risk_date = :d")
        row = conn.execute(text(sql), {"n": unit_name, "d": risk_date}).fetchone()
    else:
        row = conn.execute(text("SELECT admin_unit_id, risk_date::text AS risk_date, risk_status, calculation_version FROM risk.latest_operational_risk WHERE admin_unit_name = :n"),
                           {"n": unit_name}).fetchone()
    return dict(row._mapping) if row else None


def unit_id(conn, name: str) -> int:
    return conn.execute(text("SELECT id FROM geo.admin_unit WHERE name = :n AND level = 2"), {"n": name}).scalar()


def independent_ml(conn, uid: int) -> list:
    rows = conn.execute(text("SELECT horizon_days, status, model_type FROM ml.predictions WHERE is_current AND admin_unit_id = :u ORDER BY horizon_days"), {"u": uid}).fetchall()
    return [dict(r._mapping) for r in rows]


def executed_tools(body: dict) -> list:
    out = []
    for t in body["tool_trace"]:
        if t["status"] == C.TOOL_REJECTED:
            continue
        if out and out[-1] == t["tool_name"] == "rag.retrieve":                 # relaxation attempts are one logical retrieval
            continue
        out.append(t["tool_name"])
    return out


def ask(q: str, mode: str, admin_unit_id: Optional[int] = None, date: Optional[str] = None, deps: Optional[AgentDeps] = None, routing: str = "deterministic"):
    from api.app.services.agent import make_deps
    d = deps or make_deps()
    return run_agent(C.AgentRequest(q=q, admin_unit_id=admin_unit_id, date=date, mode=mode, routing=routing), d)


def provenance_checks(case: dict, body: dict, conn) -> list[tuple[str, bool]]:
    checks = []
    union = set()
    for t in body["tool_trace"]:
        srcs = t["provenance"].get("sources", [])
        checks.append((f"{t['tool_name']}: provenance present and in the allowed set", "sources" in t["provenance"] and set(srcs) <= set(C.PROVENANCES)))
        if t["status"] == C.TOOL_OK:
            fam = t["tool_name"].split(".")[0]
            if fam in FIXED_PROVENANCE:
                checks.append((f"{t['tool_name']}: provenance is exactly {sorted(FIXED_PROVENANCE[fam])}", set(srcs) == FIXED_PROVENANCE[fam]))
        if t["origin"] != "agent":
            union |= set(srcs)
    if case.get("provenance"):
        checks.append(("expected provenance classes are present among the tool results", set(case["provenance"]) <= union))
    rc = body.get("risk_context")
    if rc:
        checks.append(("risk_context block is RISK_ENGINE", rc["provenance"] == C.RISK_ENGINE))
    if body.get("geography"):
        checks.append(("geography block is GEOGRAPHY", body["geography"]["provenance"] == C.GEOGRAPHY))
    prov_ids = set(body["provenance"]["documentary_evidence"]["chunk_ids"])
    checks.append(("every evidence chunk is listed in the RAG_DOCUMENT provenance", all(e["chunk_id"] in prov_ids for e in body["documentary_evidence"]) and len(prov_ids) == len(body["documentary_evidence"])))
    ml = body.get("ml_prediction")
    if ml:
        rows = ml["predictions"]
        checks.append(("every forecast row is attributed by its status (BASELINE_ONLY -> BASELINE_MODEL, PREDICTED -> ML_MODEL)",
                       all(r["attribution"] == (C.BASELINE_MODEL if r["status"] == "BASELINE_ONLY" else C.ML_MODEL) for r in rows)))
        checks.append(("a BASELINE_ONLY row carries the 'NOT VALIDATED ML' label", all(r["label"] == C.BASELINE_LABEL for r in rows if r["status"] == "BASELINE_ONLY")))
        checks.append(("no INSUFFICIENT_DATA row is presented as a prediction", all(r["status"] in ("PREDICTED", "BASELINE_ONLY") and r["prediction"] is not None for r in rows)))
        truth = independent_ml(conn, rows[0]["admin_unit_id"])
        checks.append(("ML row statuses equal an independent SQL read of ml.predictions", sorted((r["horizon_days"], r["status"]) for r in rows) ==
                       sorted((t["horizon_days"], t["status"]) for t in truth if t["status"] != "INSUFFICIENT_DATA")))
    return checks


def run_cases(cfg: dict, conn) -> list[dict]:
    rows = []
    for c in cfg["cases"]:
        params = c.get("params") or {}
        uid = unit_id(conn, params["admin_unit_name"]) if params.get("admin_unit_name") else None
        body, http = ask(c["q"], cfg["mode"], uid, params.get("date"))
        body2, _ = ask(c["q"], cfg["mode"], uid, params.get("date"))
        row = {"id": c["id"], "group": c["group"], "question": c["q"], "http": http, "intent": body["intent"], "status": body["status"], "reason_code": body.get("reason_code"),
               "tools": executed_tools(body), "answer_is_null": body["answer"] is None}
        row["intent_correct"] = body["intent"] == c["intent"]
        row["tools_correct"] = row["tools"] == c["tools"]
        row["status_correct"] = body["status"] == c["status"] and (not c.get("code") or body.get("reason_code") == c["code"])
        row["reproducible"] = body["trace"]["plan_fingerprint"] == body2["trace"]["plan_fingerprint"] and executed_tools(body2) == row["tools"]
        pc = provenance_checks(c, body, conn)
        row["provenance_checks"] = {"passed": sum(ok for _, ok in pc), "total": len(pc), "failed": [n for n, ok in pc if not ok]}
        rec = (body.get("risk_context") or {}).get("record")
        row["risk"] = {"status": rec["risk_status"], "date": rec["risk_date"]} if rec else None
        row["evidence"] = len(body["documentary_evidence"])
        row["ml"] = [(p["horizon_days"], p["status"], p["attribution"]) for p in (body.get("ml_prediction") or {}).get("predictions", [])] or None
        if c.get("risk_unit"):
            truth = independent_risk(conn, c["risk_unit"], c.get("risk_date"))
            row["risk_equals_independent_sql"] = bool(truth and rec and rec["admin_unit_id"] == truth["admin_unit_id"] and rec["risk_date"] == truth["risk_date"] and
                                                       rec["risk_status"] == truth["risk_status"] and rec["calculation_version"] == truth["calculation_version"] and rec["risk_score"] is None)
        if c.get("ml") == "BASELINE_ONLY":
            row["ml_is_baseline_labelled"] = bool(body.get("ml_prediction")) and body["ml_prediction"]["validated_against_baseline"] is False and \
                body["ml_prediction"]["attributions"] == [C.BASELINE_MODEL] and body["ml_prediction"]["baseline_label"] == C.BASELINE_LABEL
        if c.get("evidence"):
            row["evidence_returned"] = len(body["documentary_evidence"]) > 0
        if c.get("candidates"):
            row["candidates_correct"] = {x["name"] for x in (body.get("geography") or {}).get("candidates", [])} >= set(c["candidates"])
        if c.get("no_facts"):
            row["abstained_without_facts"] = (body["status"] == c["status"] and rec is None and not body.get("ml_prediction") and body["answer"] is None
                                              and body["documentary_evidence"] == [] and not body["citations"])
        if c["group"] == "false_premise":
            truth = independent_risk(conn, c["risk_unit"], None)
            pcheck = body.get("premise_check") or {}
            row["false_premise_handled"] = bool(truth and rec and rec["risk_status"] == truth["risk_status"] and pcheck.get("stated_status") == c["stated"] and
                                                pcheck.get("engine_status") == truth["risk_status"] and pcheck.get("matches") == (c["stated"] == truth["risk_status"]) and body["answer"] is None)
            row["premise"] = {"stated": c["stated"], "engine_sql": truth["risk_status"] if truth else None, "matches": pcheck.get("matches")}
        rows.append(row)
    return rows


def run_invalid_calls(cfg: dict) -> dict:
    from api.app.services.agent import BACKENDS
    counter = {"n": 0}

    def counting(fn):
        def w(a):
            counter["n"] += 1
            return fn(a)
        return w
    ex = ToolExecutor({k: counting(v) for k, v in BACKENDS.items()})
    results = []
    for call in cfg["invalid_calls"]:
        r = ex.execute(C.PlannedCall(call["tool"], call["args"]))
        results.append({"tool": call["tool"], "args": call["args"], "status": r.status, "reason": r.reason, "rejected": r.status == C.TOOL_REJECTED and r.result is None})
    grounded = {"admin_unit_ids": [30], "dates": ["2026-07-01"]}
    plans = []
    for p in cfg["invalid_plans"]:
        plan = llm_router.validate_plan(p, grounded)
        plans.append({"plan": p[:90], "rejected": not plan.ok, "errors": [e["code"] for rj in plan.rejected for e in rj["errors"]] or [plan.parse_error]})
    return {"direct_calls": {"total": len(results), "rejected": sum(r["rejected"] for r in results), "backend_invocations": counter["n"], "detail": results},
            "model_plans": {"total": len(plans), "rejected": sum(p["rejected"] for p in plans), "detail": plans}}


def run_invalid_plans_end_to_end(cfg: dict, mode: str) -> dict:
    from api.app.services.agent import BACKENDS
    from api.app.services.rag import get_llm_provider  # noqa: F401
    out = []
    for p in cfg["invalid_plans"]:
        deps = AgentDeps(executor=ToolExecutor(BACKENDS), provider_factory=lambda p=p: Scripted(p))
        body, http = run_agent(C.AgentRequest(q="What is the current risk in Lahore?", mode=mode, routing="auto"), deps)
        ran = [t["tool_name"] for t in body["tool_trace"] if t["status"] != C.TOOL_REJECTED and t["origin"] != "agent"]
        out.append({"plan": p[:70], "status": body["status"], "non_geography_tools_executed": ran, "ok": body["status"] == C.INVALID_TOOL_CALL and ran == [] and body["risk_context"] is None})
    return {"total": len(out), "correct": sum(o["ok"] for o in out), "detail": out}


def run_grounding_battery(cfg: dict, conn) -> dict:
    """The REAL Lahore risk record and baseline forecast, with a scripted provider returning right and wrong answers: the existing validator decides."""
    from api.app.services.agent import BACKENDS
    q = "What is Lahore's risk status and its AQI forecast?"
    base, _ = ask(q, cfg["mode"])
    rec, ml = base["risk_context"]["record"], base["ml_prediction"]["predictions"][0]
    st, v, d = rec["risk_status"], ml["prediction"], ml["prediction_date"]
    wrong = "HIGH" if st != "HIGH" else "LOW"
    probes = {
        "separated_answer": (f"The risk engine reports status {st} [risk_engine]. A simple baseline forecast of {v:g} AQI is given for {d} [ml_prediction].", C.ANSWERED),
        "wrong_risk_status": (f"The risk engine reports status {wrong} [risk_engine].", C.INVALID_ANSWER),
        "false_causality": (f"The risk engine reports status {st} because of the NDMA flooding reports [risk_engine].", C.INVALID_ANSWER),
        "baseline_called_validated_ml": (f"The validated machine learning model forecasts {v:g} AQI for {d} [ml_prediction].", C.INVALID_ANSWER),
        "forecast_as_current_risk": ("The ML layer predicts that the current risk is HIGH [ml_prediction].", C.INVALID_ANSWER),
        "forecast_given_a_risk_status": (f"The forecast for {d} is risk level {st} [ml_prediction].", C.INVALID_ANSWER),
        "unknown_citation": ("River overflow was reported in the documents [chunk:ghost#c9].", C.INVALID_ANSWER),
        "mixed_provenance": (f"The risk engine reports status {st} and the forecast is {v:g} AQI for {d} [risk_engine] [ml_prediction].", C.INVALID_ANSWER),
        "abstention": ("INSUFFICIENT_EVIDENCE", C.INSUFFICIENT_EVIDENCE),
    }
    res = {}
    for name, (txt, expected) in probes.items():
        deps = AgentDeps(executor=ToolExecutor(BACKENDS), provider_factory=lambda t=txt: Scripted(t))
        body, _ = run_agent(C.AgentRequest(q=q, mode=cfg["mode"], routing="deterministic"), deps)
        res[name] = {"status": body["status"], "expected": expected, "ok": body["status"] == expected and (body["answer"] is not None) == (expected == C.ANSWERED),
                     "problems": [p["code"] for p in (body.get("groundedness") or {}).get("problems", [])]}
    return {"total": len(res), "as_expected": sum(r["ok"] for r in res.values()), "probes": res,
            "note": "Scripted answers, not model output: this tests the validator and the agent's handling, not a real model's behaviour."}


def pct(a, b):
    return f"{a}/{b}"


def main() -> int:
    import api.app.services.rag as rag_service
    from scripts.database.apply_serving_migration import engine_for
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    rag_service.set_llm_provider(None)
    for k in ("PORI_LLM_PROVIDER", "PORI_LLM_MODEL", "PORI_LLM_API_KEY"):
        import os
        os.environ.pop(k, None)
    with engine_for(None).connect() as conn:
        rows = run_cases(cfg, conn)
        calls = run_invalid_calls(cfg)
        plans_e2e = run_invalid_plans_end_to_end(cfg, cfg["mode"])
        grounding = run_grounding_battery(cfg, conn)
    n = len(rows)
    risk = [r for r in rows if "risk_equals_independent_sql" in r]
    abst = [r for r in rows if "abstained_without_facts" in r]
    fp = [r for r in rows if "false_premise_handled" in r]
    pt = sum(r["provenance_checks"]["passed"] for r in rows)
    pn = sum(r["provenance_checks"]["total"] for r in rows)
    by_group = {g: {"cases": sum(r["group"] == g for r in rows), "status_correct": sum(r["status_correct"] for r in rows if r["group"] == g),
                    "intent_correct": sum(r["intent_correct"] for r in rows if r["group"] == g), "tools_correct": sum(r["tools_correct"] for r in rows if r["group"] == g)}
                for g in sorted({r["group"] for r in rows})}
    summary = {
        "cases": n, "live_llm": False,
        "routing_accuracy": pct(sum(r["intent_correct"] for r in rows), n),
        "tool_selection_accuracy": pct(sum(r["tools_correct"] for r in rows), n),
        "status_accuracy": pct(sum(r["status_correct"] for r in rows), n),
        "by_group": by_group,
        "invalid_tool_call_rejection": {"direct_calls_rejected": pct(calls["direct_calls"]["rejected"], calls["direct_calls"]["total"]),
                                        "backend_invocations_for_rejected_calls": calls["direct_calls"]["backend_invocations"],
                                        "model_plans_rejected_by_validator": pct(calls["model_plans"]["rejected"], calls["model_plans"]["total"]),
                                        "model_plans_end_to_end_invalid_tool_call_and_nothing_executed": pct(plans_e2e["correct"], plans_e2e["total"])},
        "provenance_correctness": {"checks_passed": pct(pt, pn), "cases_with_all_checks_passing": pct(sum(r["provenance_checks"]["passed"] == r["provenance_checks"]["total"] for r in rows), n),
                                   "risk_record_equals_independent_sql": pct(sum(r["risk_equals_independent_sql"] for r in risk), len(risk)),
                                   "baseline_forecasts_labelled_and_attributed": pct(sum(r["ml_is_baseline_labelled"] for r in rows if "ml_is_baseline_labelled" in r), len([r for r in rows if "ml_is_baseline_labelled" in r]))},
        "abstention_correctness": {"cases_expected_to_abstain_without_facts": len(abst), "abstained_correctly": pct(sum(r["abstained_without_facts"] for r in abst), len(abst)),
                                   "cases_with_a_fabricated_answer": sum(not r["answer_is_null"] for r in rows)},
        "grounding_validation_scripted_probes": pct(grounding["as_expected"], grounding["total"]),
        "false_premise_handling": pct(sum(r["false_premise_handled"] for r in fp), len(fp)),
        "reproducibility_same_plan_fingerprint_on_rerun": pct(sum(r["reproducible"] for r in rows), n),
        "status_counts": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})},
        "note": "No real language model was available: LLM routing quality, answer quality, hallucination and causal-claim behaviour of a real model are NOT measured. "
                "Scripted-provider results test our validators and the agent's handling only.",
    }
    report = {"summary": summary, "cases": rows, "invalid_calls": calls, "invalid_plans_end_to_end": plans_e2e, "grounding": grounding}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    for r in rows:
        flag = "ok " if r["intent_correct"] and r["tools_correct"] and r["status_correct"] else "MISS"
        extra = {k: r[k] for k in ("risk_equals_independent_sql", "abstained_without_facts", "false_premise_handled", "ml_is_baseline_labelled", "evidence_returned", "candidates_correct") if k in r}
        print(f"[{flag}] {r['id']}: intent={r['intent']} status={r['status']} tools={r['tools']} prov={r['provenance_checks']['passed']}/{r['provenance_checks']['total']} {extra}")
        if flag == "MISS" or r["provenance_checks"]["failed"]:
            print("      ", {k: r[k] for k in ("intent", "status", "reason_code", "tools")}, r["provenance_checks"]["failed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
