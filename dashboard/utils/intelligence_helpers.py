"""Pure helpers for dashboard/pages/8_Intelligence.py (no Streamlit, no network)."""

from __future__ import annotations

from typing import Optional

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
