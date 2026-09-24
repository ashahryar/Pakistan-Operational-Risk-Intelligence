"""PMD / NDMC (National Drought Monitoring and Early Warning Centre) bulletin PDF parser.

Bulletins are narrative documents, so each becomes one `document` record preserving the full
extracted text (future RAG source). Structured fields are extracted only where the text states
them plainly: the title (first heading line containing bulletin/report/outlook/review), and a
reporting period when the title carries one like "(1st to 15th January, 2026)". A publication
date is NOT invented: the PDF's own CreationDate metadata is kept separately and labelled.
Every document in this dataset is issued by the NDMC drought centre, hence hazard_topic=drought.
"""

from __future__ import annotations

import re
from datetime import datetime

from .artifacts import Artifact
from .pdf_documents import extract_pdf

_TITLE_WORDS = re.compile(r"\b(bulletin|report|outlook|review)\b", re.I)
_PERIOD = re.compile(r"\((\d{1,2})(?:st|nd|rd|th)?\s+to\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})\)")


def _iso(day: str, month: str, year: str) -> str | None:
    try:
        return datetime.strptime(f"{day} {month.title()} {year}", "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def parse_bulletin_pdf(artifact: Artifact):
    doc, failures = extract_pdf(artifact)
    if doc is None:
        return [], failures
    lines = [ln.strip() for ln in doc["text"].splitlines() if ln.strip()]
    head = lines[:15]
    title = next((ln for ln in head if _TITLE_WORDS.search(ln) and doc["script"] == "latin"), None)
    period = _PERIOD.search("\n".join(head))
    record = {"source_record_id": f"ndmc:bulletin:{artifact.filename}", "artifact": artifact.provenance(),
              "record_kind": "document", "doc_type": "ndmc_bulletin",
              "issuing_organization": "National Drought Monitoring and Early Warning Centre, Pakistan Meteorological Department",
              "hazard_topic": "drought", "title": title, "heading_lines": lines[:5],
              "period_start": _iso(period.group(1), period.group(3), period.group(4)) if period else None,
              "period_end": _iso(period.group(2), period.group(3), period.group(4)) if period else None,
              "publication_date": None, "pdf_creation_date": doc["pdf_creation_date"],
              "page_count": doc["page_count"], "text": doc["text"], "text_char_count": len(doc["text"]),
              "script": doc["script"]}
    return [record], []
