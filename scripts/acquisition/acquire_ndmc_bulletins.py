"""
scripts/acquisition/acquire_ndmc_bulletins.py

Phase 1 / Task 15 (ADR-0001) -- Tier 1 raw acquisition for PMD/NDMC
Bulletins (per docs/source_inventory/ACQUISITION_PLAN.md's Tier 1 list,
item 5). Acquires the bulletins listing page verbatim, plus a small,
controlled batch of the actual PDF bulletins it links to -- NOT the
full 64-entry, ~18-month archive in one run, per the task's explicit
"do not download every historical file blindly" instruction.

Run manually:
    python scripts/acquisition/acquire_ndmc_bulletins.py
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

ORGANIZATION = "pmd_ndmc"
DATASET = "bulletins"
BASE_URL = "https://weather.gov.pk"
LISTING_URL = f"{BASE_URL}/ndmc/bulletins"

MAX_PDF_DOWNLOADS = 5
PDF_DOWNLOAD_DELAY_SECONDS = 1

# Tolerate trailing whitespace before the closing quote in an href
# (same class of markup quirk observed live on ffc.gov.pk; applied
# here too for consistency/robustness).
_PDF_LINK_RE = re.compile(r'href="([^"]+?\.pdf)\s*"', re.IGNORECASE)


def acquire_listing() -> dict:
    result = fetch(LISTING_URL)

    if not result.ok:
        record_failure(
            source_organization=ORGANIZATION, dataset=DATASET, url=LISTING_URL,
            error_code=result.error_code, error_message=result.error_message,
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"url": LISTING_URL, "status": "FAILED", "error_code": result.error_code, "content": None}

    outcome = save_fetch_result(
        result=result, source_organization=ORGANIZATION, dataset=DATASET, url=LISTING_URL,
        filename="bulletins-listing.html", acquisition_method="http_get_html",
        classification="RECENT_OPERATIONAL_HISTORY", historical_or_current="recent_history",
        geographic_scope="National",
    )
    if outcome["status"] == "ACQUIRED":
        outcome["content"] = result.content.decode("utf-8", errors="replace")
    return outcome


def acquire_pdf(url: str, filename: str) -> dict:
    result = fetch_binary(url, expected_content_type_prefixes=("application/pdf",))

    if not result.ok:
        record_failure(
            source_organization=ORGANIZATION, dataset=DATASET, url=url,
            error_code=result.error_code, error_message=result.error_message,
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"url": url, "status": "FAILED", "error_code": result.error_code}

    if not result.content.startswith(b"%PDF"):
        record_failure(
            source_organization=ORGANIZATION, dataset=DATASET, url=url,
            error_code="not_a_pdf", error_message="content-type was PDF but content lacks the %PDF magic bytes",
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"url": url, "status": "FAILED", "error_code": "not_a_pdf"}

    return save_fetch_result(
        result=result, source_organization=ORGANIZATION, dataset=DATASET, url=url,
        filename=filename, acquisition_method="http_get_pdf", classification="Drought/Weather Bulletin",
        historical_or_current="recent_history", geographic_scope="National",
    )


def main():
    print("=" * 60)
    print("ACQUIRE: PMD/NDMC Bulletins (Tier 1)")
    print("=" * 60)

    results = []

    listing = acquire_listing()
    print(f"{listing['status']:8s} | {LISTING_URL}")
    results.append(listing)

    if listing["status"] == "ACQUIRED":
        pdf_links = sorted(set(_PDF_LINK_RE.findall(listing["content"])))
        print(f"  -> {len(pdf_links)} distinct PDF link(s) found in the listing")

        for href in pdf_links[:MAX_PDF_DOWNLOADS]:
            pdf_url = urljoin(LISTING_URL, href)
            filename = href.rsplit("/", 1)[-1]
            pdf_result = acquire_pdf(pdf_url, filename)
            print(f"{pdf_result['status']:8s} | {pdf_url}")
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
