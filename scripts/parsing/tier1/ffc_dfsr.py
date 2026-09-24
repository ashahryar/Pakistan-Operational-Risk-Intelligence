"""FFC DFSR / GLOF PDF parser.

The PDFs carry an OCR-style text layer with recognition noise (e.g. "Farbela", "DAILY WEATimR"), so
river-by-river statuses and figures are NOT structured -- they stay in the narrative `text`.
Only two things are extracted because they are reliable:
  * DFSR report date: the dateline "WEDNESDAY, JULY 01, 2026".
  * GLOF alert issue time ("27th June, 2026 09:00 Hours") and the province names the alert text
    literally names as affected.
Document class comes from the source's own file naming (DFSR*, Glof-Alert*, Press-Release*).
"""

from __future__ import annotations

import re
from datetime import datetime

from scripts.geo.canonical_data import PROVINCES

from .artifacts import Artifact
from .pdf_documents import extract_pdf

_DFSR_DATE = re.compile(r"(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),?\s+([A-Z]+)\s+(\d{1,2}),?\s+(\d{4})")
_GLOF_ISSUED = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})\s*\n?.*?(\d{2}):(\d{2})\s+Hours", re.S)
DFSR_TITLE = "Daily Weather & Flood Situation Report"


def classify(filename: str) -> str:
    lowered = filename.lower()
    if lowered.startswith("glof"):
        return "glof_alert"
    if lowered.startswith("press"):
        return "press_release"
    if lowered.startswith("dfsr"):
        return "dfsr"
    return "unknown"


def _date(month: str, day: str, year: str) -> str | None:
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{month.title()} {day} {year}", fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_ffc_pdf(artifact: Artifact):
    """Returns (records, failures). Records are `document` dicts; a GLOF alert additionally yields
    one `glof_alert` dict per province literally named in its opening paragraph."""
    doc, failures = extract_pdf(artifact)
    if doc is None:
        return [], failures
    doc_type = classify(artifact.filename)
    text = doc["text"]
    record = {"source_record_id": f"ffc:{doc_type}:{artifact.filename}", "artifact": artifact.provenance(),
              "record_kind": "document", "doc_type": doc_type, "issuing_organization": "Federal Flood Commission",
              "page_count": doc["page_count"], "text": text, "text_char_count": len(text),
              "pdf_creation_date": doc["pdf_creation_date"], "script": doc["script"],
              "text_quality_note": "OCR-style text layer; recognition noise present, figures not structured",
              "hazard_topic": None, "title": None, "title_basis": None, "report_date": None, "issued_at": None}
    records = [record]
    if doc_type == "dfsr":
        record["title"], record["title_basis"] = DFSR_TITLE, "document_type_label"
        record["hazard_topic"] = "flood"
        match = _DFSR_DATE.search(text)
        record["report_date"] = _date(*match.groups()) if match else None
    elif doc_type == "glof_alert":
        record["title"], record["title_basis"] = "GLOF Alert", "document_heading"
        record["hazard_topic"] = "glof"
        match = _GLOF_ISSUED.search(text)
        if match:
            day, month, year, hour, minute = match.groups()
            iso_day = _date(month, day, year)
            if iso_day:
                record["issued_at"] = f"{iso_day}T{hour}:{minute}:00"
        record["report_date"] = record["issued_at"][:10] if record["issued_at"] else None
        opening = text.split("Possible impacts", 1)[0]
        for province in PROVINCES:
            if re.search(re.escape(province["name"]), opening, re.I):
                records.append({"source_record_id": f"ffc:glof_alert:{artifact.filename}:{province['name']}",
                                "artifact": artifact.provenance(), "record_kind": "glof_alert",
                                "hazard_type": "glof", "issued_at": record["issued_at"],
                                "affected_area": province["name"], "title": "GLOF Alert",
                                "description": opening.strip(), "document_id": record["source_record_id"]})
    return records, failures
