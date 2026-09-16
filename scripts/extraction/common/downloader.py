"""
downloader.py

Reusable PDF/image downloader used by the legacy NDMA/PDMA extractors
(scripts/extraction/extract_ndma.py, extract_pdma.py -- both confirmed
active, DAG-referenced by ndma_dag.py/pdma_dag.py/weekly_dag.py/
manual_dag.py per the Task 16 audit).

Task 16A (Phase 1 / ADR-0001), Part A item 6: hardened to the minimum
Task-15 acquisition safety standard by reusing Task 15's own utilities
rather than re-implementing HTTP validation or atomic-write logic a
second time:
  - scripts/acquisition/client.py::fetch_binary() -- real HTTP status
    validation, empty-response rejection, and Content-Type-mismatch
    detection (catches a PDF link that 404s into an HTML error page
    served with a 200 status, a real failure mode on the same
    WordPress/CMS-hosted government sites Task 15 already handles).
  - scripts/acquisition/raw_store.py::write_verified_bytes() -- atomic,
    checksum-verified write (never leaves a truncated file mistaken
    for a successful download).

Still returns a plain bool, preserving the existing call-site contract
in extract_ndma.py/extract_pdma.py (out of scope for this task -- see
Task 16A Part A item 6's "do not create a second acquisition
framework" instruction; this is a hardening of the existing entry
point, not a rewrite of the extractors that call it).
"""

import logging
from pathlib import Path

from scripts.acquisition.client import fetch_binary
from scripts.acquisition.raw_store import write_verified_bytes

logger = logging.getLogger(__name__)

_CONTENT_TYPE_BY_SUFFIX = {
    ".pdf": ("application/pdf",),
    ".jpg": ("image/",),
    ".jpeg": ("image/",),
    ".png": ("image/",),
}


def download_file(
    url: str,
    output: Path,
) -> bool:
    """
    Download any file (PDF or image, per the extensions the existing
    NDMA/PDMA extractors handle) to `output`, validating the response
    before ever writing it and verifying the write afterward.

    Returns True only if: the HTTP request succeeded with a 2xx
    status, the response was non-empty, the Content-Type (when the
    server sends one) matched what `output`'s extension implies, a
    PDF's content actually starts with the `%PDF` magic bytes (an
    HTML error page served with `Content-Type: application/pdf` --
    seen in practice on some misconfigured sites -- would otherwise
    slip past the Content-Type check alone), and the write was
    confirmed readable back off disk with a matching checksum.
    Returns False on any failure, logging the reason -- never raises,
    matching the existing call-site contract.
    """

    expected_content_types = _CONTENT_TYPE_BY_SUFFIX.get(output.suffix.lower(), ())

    result = fetch_binary(url, expected_content_type_prefixes=expected_content_types)

    if not result.ok:
        logger.error(
            "download_file failed for %s: %s (%s)",
            url, result.error_code, result.error_message,
        )
        return False

    if output.suffix.lower() == ".pdf" and not result.content.startswith(b"%PDF"):
        logger.error(
            "download_file rejected %s: Content-Type looked like a PDF but "
            "content lacks the %%PDF magic bytes (likely an HTML error page)",
            url,
        )
        return False

    try:
        write_verified_bytes(output, result.content)
    except (OSError, ValueError) as e:
        logger.error("download_file could not verify the write for %s: %s", output, e)
        return False

    logging.info("Downloaded %s", output.name)
    return True
