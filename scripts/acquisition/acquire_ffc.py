"""
scripts/acquisition/acquire_ffc.py

Phase 1 / Task 15 (ADR-0001) -- Tier 1 raw acquisition for the Federal
Flood Commission (per docs/source_inventory/ACQUISITION_PLAN.md's Tier
1 list, items 3 and 4). Two datasets:

1. `reservoir_levels` -- the FFC homepage itself, saved verbatim. The
   live Tarbela/Mangla/Chashma reservoir figures Task 14 read are
   embedded directly in this page's HTML text (no separate API/endpoint
   exists for them) -- so "acquiring" this dataset means archiving the
   homepage HTML as-is; a later (out-of-scope-for-this-task) parsing
   step would extract the numbers from it.

2. `dfsr_glof_archive` -- the DFSR/GLOF/Press-Release archive listing
   page, saved verbatim, PLUS a small, controlled batch of the actual
   PDF documents it links to (NOT the full ~80-report season -- see
   MAX_PDF_DOWNLOADS below, per the task's explicit "do not download
   every historical file blindly" instruction).

Run manually:
    python scripts/acquisition/acquire_ffc.py
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from scripts.acquisition.client import fetch, fetch_binary  # noqa: E402
from scripts.acquisition.failures import record_failure  # noqa: E402
from scripts.acquisition.pipeline import save_fetch_result  # noqa: E402

ORGANIZATION = "ffc"
BASE_URL = "https://ffc.gov.pk"
HOMEPAGE_URL = f"{BASE_URL}/"
ARCHIVE_URL = f"{BASE_URL}/dfsr-glof-press-release-2025/"

# Controlled, rate-limited batch -- NOT the full season's archive. This
# proves the acquisition pipeline end-to-end against real files without
# bulk-downloading a whole season in one uncontrolled run.
MAX_PDF_DOWNLOADS = 5
PDF_DOWNLOAD_DELAY_SECONDS = 1

# Tolerate trailing whitespace before the closing quote in an href
# (observed live on ffc.gov.pk's GLOF-alert links specifically, e.g.
# href="....Glof-Alert.pdf " -- a real markup quirk on this site, not
# a hypothetical).
_PDF_LINK_RE = re.compile(r'href="([^"]+?\.pdf)\s*"', re.IGNORECASE)

# The archive page's footer/sidebar also links to unrelated content
# (e.g. a 2022 print magazine, ~75 MB) that happens to end in .pdf but
# has nothing to do with this dataset. Scope acquisition to filenames
# that actually look like DFSR/GLOF/flood documents -- matching what
# this specific archive page is actually named for
# ("dfsr-glof-press-release") -- rather than every .pdf link found on
# the page.
_RELEVANT_PDF_RE = re.compile(r"(dfsr|glof|flood|advisor|press)", re.IGNORECASE)


def _is_relevant_pdf(href: str) -> bool:
    return bool(_RELEVANT_PDF_RE.search(href))


def _classify_pdf_title(href: str) -> str:
    lower = href.lower()
    if "glof" in lower:
        return "GLOF alert"
    if "dfsr" in lower:
        return "Daily Flood Situation Report"
    return "Press release / other FFC document"


def acquire_html_page(dataset: str, url: str, filename: str, classification: str, historical_or_current: str) -> dict:
    result = fetch(url)

    if not result.ok:
        record_failure(
            source_organization=ORGANIZATION, dataset=dataset, url=url,
            error_code=result.error_code, error_message=result.error_message,
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"url": url, "status": "FAILED", "error_code": result.error_code, "content": None}

    outcome = save_fetch_result(
        result=result, source_organization=ORGANIZATION, dataset=dataset, url=url,
        filename=filename, acquisition_method="http_get_html", classification=classification,
        historical_or_current=historical_or_current, geographic_scope="National",
    )
    if outcome["status"] == "ACQUIRED":
        outcome["content"] = result.content.decode("utf-8", errors="replace")
    return outcome


def acquire_pdf(dataset: str, url: str, filename: str, classification: str) -> dict:
    result = fetch_binary(url, expected_content_type_prefixes=("application/pdf",))

    if not result.ok:
        record_failure(
            source_organization=ORGANIZATION, dataset=dataset, url=url,
            error_code=result.error_code, error_message=result.error_message,
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"url": url, "status": "FAILED", "error_code": result.error_code}

    if not result.content.startswith(b"%PDF"):
        record_failure(
            source_organization=ORGANIZATION, dataset=dataset, url=url,
            error_code="not_a_pdf", error_message="content-type was PDF but content lacks the %PDF magic bytes",
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"url": url, "status": "FAILED", "error_code": "not_a_pdf"}

    return save_fetch_result(
        result=result, source_organization=ORGANIZATION, dataset=dataset, url=url,
        filename=filename, acquisition_method="http_get_pdf", classification=classification,
        historical_or_current="recent_history", geographic_scope="National",
    )


def main():
    print("=" * 60)
    print("ACQUIRE: Federal Flood Commission (Tier 1)")
    print("=" * 60)

    results = []

    homepage = acquire_html_page(
        dataset="reservoir_levels", url=HOMEPAGE_URL, filename="homepage.html",
        classification="LIVE_CURRENT", historical_or_current="current",
    )
    print(f"{homepage['status']:8s} | {HOMEPAGE_URL} (reservoir_levels)")
    results.append(homepage)

    archive = acquire_html_page(
        dataset="dfsr_glof_archive", url=ARCHIVE_URL, filename="archive-listing.html",
        classification="RECENT_OPERATIONAL_HISTORY", historical_or_current="recent_history",
    )
    print(f"{archive['status']:8s} | {ARCHIVE_URL} (dfsr_glof_archive listing)")
    results.append(archive)

    if archive["status"] == "ACQUIRED":
        all_pdf_links = sorted(set(_PDF_LINK_RE.findall(archive["content"])))
        pdf_links = [h for h in all_pdf_links if _is_relevant_pdf(h)]
        skipped = len(all_pdf_links) - len(pdf_links)
        print(
            f"  -> {len(all_pdf_links)} distinct PDF link(s) found in the archive listing "
            f"({len(pdf_links)} match this dataset's DFSR/GLOF/press-release scope; "
            f"{skipped} unrelated link(s) skipped, e.g. print magazines)"
        )

        for href in pdf_links[:MAX_PDF_DOWNLOADS]:
            pdf_url = urljoin(ARCHIVE_URL, href)
            filename = href.rsplit("/", 1)[-1]
            classification = _classify_pdf_title(href)
            pdf_result = acquire_pdf("dfsr_glof_archive", pdf_url, filename, classification)
            print(f"{pdf_result['status']:8s} | {pdf_url} [{classification}]")
            results.append(pdf_result)
            time.sleep(PDF_DOWNLOAD_DELAY_SECONDS)

        if len(pdf_links) > MAX_PDF_DOWNLOADS:
            print(
                f"  -> {len(pdf_links) - MAX_PDF_DOWNLOADS} additional PDF link(s) found but "
                f"NOT downloaded this run (MAX_PDF_DOWNLOADS={MAX_PDF_DOWNLOADS}, per the "
                f"task's controlled-batch instruction)"
            )

    print("=" * 60)
    return results


if __name__ == "__main__":
    main()
