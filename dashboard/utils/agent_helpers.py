"""Pure helpers for dashboard/pages/9_Agent.py (no Streamlit, no network)."""

from __future__ import annotations

from typing import Optional

import pandas as pd

BASELINE_LABEL = "BASELINE_ONLY — NOT VALIDATED ML"

STATUS_BANNERS = {
    "ANSWERED": ("success", "A real language model answered and the existing grounding validation accepted it. Statements carry citations to their source."),
    "COMPLETED": ("success", "Structured lookup completed. No language generation was needed."),
    "LLM_UNAVAILABLE": ("info", "The tool results below were retrieved, but no natural-language answer exists: no real language model is configured or it did not respond. "
                                "Nothing was written on the model's behalf."),
    "UNSUPPORTED_REQUEST": ("warning", "This request is not supported (or was refused by a safety rule). Nothing was executed and nothing was invented."),
    "AMBIGUOUS_GEOGRAPHY": ("warning", "The place name is ambiguous. No area was guessed; choose one of the candidate interpretations below (or pick the area in the form)."),
    "INSUFFICIENT_DATA": ("warning", "The requested information is not available. What exists is shown below; nothing was substituted or invented."),
    "NO_EVIDENCE": ("warning", "No documentary evidence matched this question. No answer was given."),
    "INSUFFICIENT_EVIDENCE": ("warning", "The language model reported that the supplied information does not answer the question."),
    "INVALID_TOOL_CALL": ("error", "A model-proposed tool call failed validation and was not executed. See the tool trace."),
    "INVALID_ANSWER": ("error", "The generated answer failed the grounding validation and was withheld. The structured results are shown below."),
}


def status_banner(status: Optional[str]) -> tuple[str, str]:
    return STATUS_BANNERS.get(status or "", ("warning", f"Unrecognised status: {status}"))


def routing_text(trace: Optional[dict]) -> str:
    r = (trace or {}).get("routing") or {}
    if r.get("method") == "llm":
        return f"LLM-assisted ({(r.get('llm') or {}).get('provider')})"
    if r.get("fallback"):
        return "deterministic (model unavailable)"
    return "deterministic"


def tool_trace_table(trace: list[dict]) -> pd.DataFrame:
    rows = []
    for t in trace or []:
        rows.append({"Tool": t.get("tool_name"), "Origin": t.get("origin"), "Status": t.get("status"),
                     "Provenance": ", ".join((t.get("provenance") or {}).get("sources") or []) or "-", "ms": "-" if t.get("duration_ms") is None else f"{t['duration_ms']:g}",
                     "Arguments": str(t.get("arguments") or {}), "Note": t.get("reason") or ""})
    return pd.DataFrame(rows, columns=["Tool", "Origin", "Status", "Provenance", "ms", "Arguments", "Note"])


def provenance_rows(body: dict) -> pd.DataFrame:
    p = body.get("provenance") or {}
    rows = []
    g = p.get("geography") or {}
    rows.append({"Block": "Geography", "Source": g.get("source", "GEOGRAPHY"), "Available": str(bool(g.get("available"))), "Detail": f"admin_unit_id {g.get('admin_unit_id')}" if g.get("admin_unit_id") else "-"})
    r = p.get("risk_context") or {}
    rows.append({"Block": "Risk context", "Source": r.get("source", "RISK_ENGINE"), "Available": str(bool(r.get("available"))),
                 "Detail": f"{r.get('calculation_version')} / {r.get('risk_date')}" if r.get("available") else "-"})
    d = p.get("documentary_evidence") or {}
    rows.append({"Block": "Documentary evidence", "Source": d.get("source", "RAG_DOCUMENT"), "Available": str(bool(d.get("chunk_ids"))), "Detail": f"{len(d.get('chunk_ids') or [])} chunk(s)"})
    m = p.get("ml_prediction") or {}
    rows.append({"Block": "ML forecast", "Source": " + ".join(m.get("sources") or []) or "none", "Available": str(bool(m.get("available"))),
                 "Detail": ", ".join(m.get("model_run_ids") or []) or "-"})
    return pd.DataFrame(rows, columns=["Block", "Source", "Available", "Detail"])


def ml_rows(predictions: list[dict]) -> pd.DataFrame:
    rows = []
    for p in sorted(predictions or [], key=lambda p: p.get("horizon_days") or 0):
        value = "-" if p.get("prediction") is None else f"{p['prediction']:g} {p.get('unit') or ''}".strip()
        rows.append({"Horizon": f"{p.get('horizon_days')} day(s)", "Forecast for": p.get("prediction_date"), "Forecast": value, "Status": p.get("status"),
                     "Provenance": p.get("attribution") or "-", "Label": p.get("label") or "-", "Model": f"{p.get('model_name') or '-'} {p.get('model_version') or ''}".strip(),
                     "Training cutoff": p.get("training_cutoff") or "-", "Features through": p.get("feature_cutoff")})
    return pd.DataFrame(rows, columns=["Horizon", "Forecast for", "Forecast", "Status", "Provenance", "Label", "Model", "Training cutoff", "Features through"])


def candidate_rows(candidates: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{"Name": c.get("name"), "Level": {1: "province", 2: "district"}.get(c.get("level"), str(c.get("level"))), "admin_unit_id": str(c.get("id"))}
                         for c in candidates or []], columns=["Name", "Level", "admin_unit_id"])
