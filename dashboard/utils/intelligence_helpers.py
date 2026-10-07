"""Pure helpers for dashboard/pages/8_Intelligence.py (no Streamlit, no network)."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from dashboard.utils.risk_map_helpers import risk_score_text, signal_summary  # noqa: F401  (signal_summary is re-exported for the page)

AUTO = "Automatic (from the question)"

STATUS_BANNERS = {
    "ANSWERED": ("success", "A grounded explanation was generated. Computed risk-engine statements are marked [risk_engine]; documentary statements cite report chunks."),
    "INSUFFICIENT_EVIDENCE": ("warning", "The language model reported that the supplied risk context and documents do not answer the question."),
    "NO_RISK_CONTEXT": ("warning", "No risk-engine record exists for this question, so no risk classification can be explained. Any retrieved documents are shown below."),
    "RETRIEVAL_EMPTY": ("warning", "No matching report passages and no risk context were found."),
    "LLM_UNAVAILABLE": ("info", "The risk context and documentary evidence were retrieved, but AI generation is unavailable (no language model is configured or it did not respond)."),
    "INVALID_ANSWER": ("error", "The generated explanation failed the provenance check and was withheld. The risk context and evidence are shown below."),
}


def status_banner(status: Optional[str]) -> tuple[str, str]:
    return STATUS_BANNERS.get(status or "", ("warning", f"Unrecognised status: {status}"))


def area_options(units: list[dict]) -> dict[str, Optional[int]]:
    """Label -> admin_unit_id for the area selector (provinces first, then districts with their province)."""
    out: dict[str, Optional[int]] = {AUTO: None}
    for u in sorted(units, key=lambda u: (u["level"], u["name"])):
        label = u["name"] if u["level"] == 1 else f"{u['name']} ({u.get('province') or '?'})"
        out[label] = u["id"]
    return out


def risk_metrics(record: dict) -> dict[str, str]:
    cov = record.get("data_coverage_pct")
    return {"Status": record.get("risk_status") or "-", "Confidence": record.get("risk_confidence") or "-",
            "Coverage": "-" if cov is None else f"{cov:g}%", "Top domain": record.get("top_risk_domain") or "none",
            "Risk score": "Unavailable" if record.get("risk_score") is None else risk_score_text(record["risk_score"])}


def ml_table(predictions: list[dict]) -> pd.DataFrame:
    """Rows of the ML forecast table (all text, so mixed values never break Arrow conversion). Probability/confidence is never shown: none is calibrated."""
    rows = []
    for p in sorted(predictions, key=lambda p: p.get("horizon_days") or 0):
        value = "-" if p.get("prediction") is None else f"{p['prediction']:g} {p.get('unit') or ''}".strip()
        rows.append({"Horizon": f"{p.get('horizon_days')} day(s)", "Forecast for": p.get("prediction_date"), "Forecast": value, "Status": p.get("status"),
                     "Model": f"{p.get('model_name') or '-'} {p.get('model_version') or ''}".strip(), "Type": p.get("model_type"),
                     "Training cutoff": p.get("training_cutoff") or "-", "Features through": p.get("feature_cutoff")})
    return pd.DataFrame(rows, columns=["Horizon", "Forecast for", "Forecast", "Status", "Model", "Type", "Training cutoff", "Features through"])


def ml_caption(block: dict) -> str:
    validated = block.get("validated_against_baseline")
    return ("Validated ML model: beat the simple baselines on held-out validation and test periods." if validated else
            "NOT a validated ML model: the machine-learning candidates did not beat a simple baseline on held-out data, so these values are that baseline's forecast.")


def score_caption(record: dict) -> str:
    """Task 36: the numeric operational score is distinct from the status. Shows the real reason when it is unavailable (never a fake zero)."""
    if record.get("risk_score") is not None:
        return ("Operational score (provisional signal-intensity index, 0-100; not a probability and not calibrated): "
                f"{record['risk_score']:g}")
    s = record.get("score_v2") or {}
    return ("Operational score: not computed - " + (s.get("abstention_text") or "no score is stored for this record")
            + (f" [{s['abstention_reason']}]" if s.get("abstention_reason") else "") + ". The status above is a separate, provisional classification.")
