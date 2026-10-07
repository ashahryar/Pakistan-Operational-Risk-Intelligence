"""dashboard/utils/summary_helpers.py -- deterministic summaries for the Intelligence Workspace (Task 42).

When no language model is configured the API still returns the structured facts and the retrieved passages. These helpers turn exactly those into short, readable
statements. Nothing here is generated or inferred: every sentence is a template filled with a value the API returned (or says plainly that a value is missing),
and the page labels the result "assembled from the retrieved data; no AI model wrote this". Pure functions, no Streamlit, no network.
"""

from __future__ import annotations

from typing import Optional

from dashboard.ui import tokens

ENABLE_HINT = ("Written answers need a language model: set PORI_LLM_PROVIDER, PORI_LLM_MODEL and PORI_LLM_API_KEY in .env and restart the API. "
               "The risk status and the documents below are authoritative with or without one.")
EXAMPLES = ["What is the current risk status of Lahore?", "Why is Lahore currently classified LOW and is there any AQI forecast?",
            "What did NDMA report about deaths in Punjab?"]


def _date(v) -> str:
    return str(v) if v else "an unstated date"


def operational_summary(body: dict) -> list[str]:
    """Bullets for an agent / risk-analysis response body. Empty list when the body carries no structured facts."""
    out: list[str] = []
    rcx = body.get("risk_context")
    geo = (body.get("geography") or {}).get("unit") or {}
    if rcx and rcx.get("status") == "AVAILABLE":
        rec = rcx["record"]
        name = rec.get("admin_unit_name") or geo.get("name") or "The selected area"
        out.append(f"**{name}**: operational status is **{tokens.status_label(rec.get('risk_status'))}** as of {_date(rec.get('risk_date'))}. "
                   "This is the risk engine's provisional classification, not a probability.")
        observed, missing = rec.get("observed_signal_count"), rec.get("missing_signal_count")
        cov = rec.get("data_coverage_pct")
        if observed is not None and missing is not None:
            out.append(f"{observed} of {observed + missing} signal groups were observed" + (f" (data coverage {cov}%)." if cov is not None else "."))
        sig = rec.get("signals") or {}
        seen = [k.replace("_", " ") for k, v in sig.items() if v is not None]
        if seen:
            out.append("Observed: " + ", ".join(seen) + ". Not observed: " + (", ".join(k.replace("_", " ") for k, v in sig.items() if v is None) or "none") + ".")
        out.append("Numeric risk score: " + ("not computed (no evidence-based weights exist), so the status is the only classification."
                                             if rec.get("risk_score") is None else f"{rec['risk_score']}."))
    elif rcx:
        out.append(f"No risk record could be retrieved for this question: {rcx.get('reason') or rcx.get('status')}.")
    ml = body.get("ml_prediction")
    comp = (body.get("components") or {}).get("ml") or {}
    if ml:
        out.append("A forecast exists but it is a baseline, not a validated model." if (ml.get("baseline_label") or not ml.get("validated_against_baseline")) else "A validated forecast exists.")
    elif comp.get("status") == "INSUFFICIENT_DATA":
        out.append(f"No forecast: {comp.get('reason')}.")
    docs = body.get("documentary_evidence")
    if docs:
        titles = "; ".join(f"{d.get('title') or '(untitled)'} ({_date(d.get('document_date'))})" for d in docs[:3])
        out.append(f"{len(docs)} document passage(s) passed the relevance check, led by: {titles}.")
    elif body.get("retrieval"):
        rel = (body["retrieval"] or {}).get("relevance") or {}
        out.append("No document passage passed the relevance check for this question" + (f" ({rel.get('low_relevance_count')} loosely matching passage(s) were withheld)." if rel.get("low_relevance_count") else "."))
    return out


def extractive_passages(evidence: list[dict], n: int = 3, chars: int = 320) -> list[dict]:
    """The most relevant retrieved passages as verbatim excerpts (first `chars` characters), in the API's own relevance order. Not a summary."""
    out = []
    for e in (evidence or [])[:n]:
        text = (e.get("snippet") or "").strip().replace("\n", " ")
        out.append({"title": e.get("title") or "(untitled)", "source": (e.get("source") or "").upper() or "not stated", "date": e.get("document_date") or "undated",
                    "excerpt": text[:chars] + ("…" if len(text) > chars else "")})
    return out


def passage_markdown(p: dict) -> str:
    return f"**{p['title']}** · {p['source']} · {p['date']}\n\n> {p['excerpt']}"


def example_line(examples: Optional[list[str]] = None) -> str:
    return "Examples to try: " + " · ".join(f"“{q}”" for q in (examples or EXAMPLES))
