"""
scripts/acquisition/acquire_aqi_punjab.py

Phase 1 / Task 15 (ADR-0001) -- Tier 1 raw acquisition for the EPA
Punjab AQI API (per docs/source_inventory/ACQUISITION_PLAN.md's Tier 1
list, item 2). Acquires exactly the endpoints Task 14 verified:
district list, one district's station list, and that district's
current-month AQI calendar -- not "every district's every month",
which Task 14 explicitly did not verify was safe/intended to bulk-pull
and this task explicitly forbids assuming.

Endpoints (all directly verified working in Task 14):
    /api/districts
    /api/district-stations/{district}
    /api/aqi-calendar-data?year={year}&month={month}&district={district}

`/api/district-stations/{district}` returns HTTP 403 INVALID_ORIGIN
without an Origin/Referer header matching the site's own domain --
confirmed live in this session. These headers are sent for every call
below; they are not a credential or an authorization bypass, just what
a normal browser page-load already sends.

Run manually:
    python scripts/acquisition/acquire_aqi_punjab.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from scripts.acquisition.client import fetch_json  # noqa: E402
from scripts.acquisition.failures import record_failure  # noqa: E402
from scripts.acquisition.pipeline import save_fetch_result  # noqa: E402

ORGANIZATION = "epa_punjab"
DATASET = "aqi_punjab"
BASE_URL = "https://aqi.punjab.gov.pk"

VERIFIED_DISTRICT = "Lahore"
_now = datetime.now(timezone.utc)
_BROWSER_HEADERS = {"Origin": BASE_URL, "Referer": f"{BASE_URL}/"}


def _endpoints():
    return [
        {"endpoint": "/api/districts", "filename": "districts.json"},
        {
            "endpoint": f"/api/district-stations/{VERIFIED_DISTRICT}",
            "filename": f"district-stations-{VERIFIED_DISTRICT.lower()}.json",
        },
        {
            "endpoint": f"/api/aqi-calendar-data?year={_now.year}&month={_now.month}&district={VERIFIED_DISTRICT}",
            "filename": f"aqi-calendar-{VERIFIED_DISTRICT.lower()}-{_now.year}-{_now.month:02d}.json",
        },
    ]


def acquire_one(endpoint: str, filename: str) -> dict:
    url = f"{BASE_URL}{endpoint}"
    result = fetch_json(url, extra_headers=_BROWSER_HEADERS)

    if not result.ok:
        record_failure(
            source_organization=ORGANIZATION, dataset=DATASET, url=url,
            error_code=result.error_code, error_message=result.error_message,
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"endpoint": endpoint, "url": url, "status": "FAILED", "error_code": result.error_code}

    outcome = save_fetch_result(
        result=result, source_organization=ORGANIZATION, dataset=DATASET, url=url,
        filename=filename, acquisition_method="http_get_json",
        classification="RECENT_OPERATIONAL_HISTORY", historical_or_current="current",
        geographic_scope=f"Punjab (district: {VERIFIED_DISTRICT})", endpoint=endpoint,
    )
    outcome["endpoint"] = endpoint
    return outcome


def main():
    print("=" * 60)
    print("ACQUIRE: EPA Punjab AQI (Tier 1)")
    print("=" * 60)

    results = [acquire_one(e["endpoint"], e["filename"]) for e in _endpoints()]

    for r in results:
        print(f"{r['status']:8s} | {r['endpoint']}")
        if r["status"] == "ACQUIRED":
            print(f"         -> {r['local_path']} ({r['byte_size']} bytes, sha256={r['sha256'][:12]}...)")

    print("=" * 60)
    return results


if __name__ == "__main__":
    main()
