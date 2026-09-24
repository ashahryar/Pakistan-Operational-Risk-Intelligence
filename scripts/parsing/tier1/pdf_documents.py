"""Shared, failure-isolated PDF text extraction for the Tier-1 document parsers.

A PDF that is corrupt, or has no usable text layer (image-only scans), is reported as a failure
record for quarantine -- it never raises and never stops the batch. No OCR is performed: image-only
files are a documented blocker, not something to guess at.
"""

from __future__ import annotations

import re

import pdfplumber

from .artifacts import Artifact, failure

MIN_TEXT_CHARS = 200
_ARABIC = re.compile(r"[؀-ۿ]")


def extract_pdf(artifact: Artifact):
    """Returns (document_dict | None, failures). document_dict has page_count, text, creation_date."""
    try:
        with pdfplumber.open(artifact.path) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
            creation = (pdf.metadata or {}).get("CreationDate")
    except Exception as exc:  # corrupt/encrypted PDFs raise assorted library errors; isolate them all
        return None, [failure("pdf_unreadable", f"{type(exc).__name__}: {exc}", artifact)]
    text = "\n".join(pages).strip()
    if len(text) < MIN_TEXT_CHARS:
        return None, [failure("no_text_layer",
                              f"only {len(text)} extractable characters across {len(pages)} page(s); "
                              "image-only scan, OCR required", artifact)]
    letters = [c for c in text if c.isalpha()]
    arabic_share = (len(_ARABIC.findall(text)) / len(letters)) if letters else 0.0
    return {"page_count": len(pages), "text": text, "pdf_creation_date": creation,
            "script": "arabic" if arabic_share > 0.3 else "latin"}, []
