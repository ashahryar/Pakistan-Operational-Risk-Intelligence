"""Pure helpers for dashboard/pages/7_RAG_Ask.py (no Streamlit, no network) so they can be unit-tested."""

from __future__ import annotations

from typing import Optional

SOURCES = ["ndma", "pdma", "pmd"]
FALLBACK_PROVINCES = ["Azad Jammu & Kashmir", "Balochistan", "Gilgit-Baltistan", "Islamabad Capital Territory", "Khyber Pakhtunkhwa", "Punjab", "Sindh"]
MODES = {"hybrid": "Hybrid (keywords + meaning)", "semantic": "Semantic (meaning)", "lexical": "Lexical (keywords)"}

# status -> (streamlit level, message). The wording never presents a model answer as authoritative.
STATUS_BANNERS = {
    "ANSWERED": ("success", "Answer generated from the retrieved reports. Every statement carries a citation to a source chunk shown below."),
    "INSUFFICIENT_EVIDENCE": ("warning", "The retrieved reports do not contain enough information to answer. No answer was given rather than guessing."),
    "RETRIEVAL_EMPTY": ("warning", "No matching report passages were found for this question and filters."),
    "LLM_UNAVAILABLE": ("info", "Answer generation is not available (no language model is configured or it did not respond). "
                                "The retrieved evidence is shown below."),
    "INVALID_ANSWER": ("error", "The generated answer failed the citation check and was withheld. The retrieved evidence is shown below."),
}


def status_banner(status: Optional[str]) -> tuple[str, str]:
    return STATUS_BANNERS.get(status or "", ("warning", f"Unrecognised answer status: {status}"))


def citation_rows(citations: list[dict]) -> list[dict]:
    return [{"Chunk": c["chunk_id"], "Source": (c.get("source") or "").upper(), "Title": c.get("title") or "(untitled)",
             "Date": c.get("document_date") or "undated"} for c in citations or []]


def evidence_caption(e: dict) -> str:
    r = e.get("relevance") or {}
    parts = [f"{(e.get('source') or '').upper()} · {e.get('document_date') or 'undated'}", f"{r.get('relevance_type') or r.get('method')}",
             f"score {r.get('score')}"]
    if r.get("lexical_rank") is not None:
        parts.append(f"keyword rank {r['lexical_rank']}")
    if r.get("semantic_rank") is not None:
        parts.append(f"meaning rank {r['semantic_rank']}")
    ref = e.get("source_reference") or {}
    parts.append(ref.get("url") or ref.get("file_path") or "no source reference")
    return " · ".join(str(p) for p in parts)


def relevance_notice(retrieval: Optional[dict]) -> Optional[tuple[str, str]]:
    """Task 35: when retrieval found only low-relevance chunks the UI must say NO_EVIDENCE plainly (and never show those chunks as evidence).
    -> (streamlit level, message) or None when relevant evidence exists / the response carries no relevance decision."""
    rel = (retrieval or {}).get("relevance")
    if not rel or not rel.get("abstained"):
        return None
    withheld = rel.get("low_relevance_count") or 0
    return ("info", f"NO_EVIDENCE - no document passage passed the relevance check for this question"
                    f"{f' ({withheld} loosely matching passage(s) were withheld and are NOT shown as evidence)' if withheld else ''}. "
                    f"{rel.get('abstention_reason') or ''}".strip())


def evidence_rows(evidence: list[dict], cited_ids: set) -> list[dict]:
    """One row per retrieved passage that PASSED the relevance check (low-relevance passages are withheld by the API and never appear here).
    Columns: Status (Cited / Retrieved), Source, Document, Date, Geography, Relevance, Provenance. Missing values read 'not stated', never blank or zero."""
    rows = []
    for e in evidence or []:
        r = e.get("relevance") or {}
        geo = e.get("geography") or {}
        place = geo.get("district") or geo.get("province") or geo.get("name") or "not stated"
        ref = e.get("source_reference") or {}
        rows.append({"Status": "Cited" if e.get("chunk_id") in cited_ids else "Retrieved", "Source": (e.get("source") or "").upper() or "not stated",
                     "Document": e.get("title") or "(untitled)", "Date": e.get("document_date") or "undated", "Geography": place,
                     "Relevance": f"{r.get('relevance_type') or r.get('method') or 'not stated'} (score {r.get('score')})" if r else "not stated",
                     "Provenance": ref.get("url") or ref.get("file_path") or "no source reference"})
    return rows
