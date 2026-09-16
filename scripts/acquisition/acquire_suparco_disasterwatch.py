"""
scripts/acquisition/acquire_suparco_disasterwatch.py

Phase 1 / Task 15 (ADR-0001) -- Tier 1 raw acquisition for SUPARCO
DisasterWatch (per docs/source_inventory/ACQUISITION_PLAN.md's Tier 1
list, item 1). Fetches the two JSON API endpoints verified in Task 14
and preserves each response byte-for-byte as a raw artifact -- no
transformation, no field extraction, no normalization.

Endpoints (both directly verified working in Task 14 by fetching and
reading the actual JSON body):
    /disasterwatch/api/themes/global-themes?format=published
    /disasterwatch/api/resources/campaigns?live=true

Run manually:
    python scripts/acquisition/acquire_suparco_disasterwatch.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from scripts.acquisition.client import fetch_json  # noqa: E402
from scripts.acquisition.failures import record_failure  # noqa: E402
from scripts.acquisition.pipeline import save_fetch_result  # noqa: E402

ORGANIZATION = "suparco"
DATASET = "disasterwatch"
BASE_URL = "https://saccs.sgs-suparco.gov.pk"

ENDPOINTS = [
    {
        "endpoint": "/disasterwatch/api/themes/global-themes?format=published",
        "filename": "global-themes.json",
    },
    {
        "endpoint": "/disasterwatch/api/resources/campaigns?live=true",
        "filename": "campaigns-live.json",
    },
]


def acquire_one(endpoint: str, filename: str) -> dict:
    url = f"{BASE_URL}{endpoint}"
    result = fetch_json(url)

    if not result.ok:
        record_failure(
            source_organization=ORGANIZATION, dataset=DATASET, url=url,
            error_code=result.error_code, error_message=result.error_message,
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"endpoint": endpoint, "url": url, "status": "FAILED", "error_code": result.error_code}

    outcome = save_fetch_result(
        result=result, source_organization=ORGANIZATION, dataset=DATASET, url=url,
        filename=filename, acquisition_method="http_get_json", classification="LIVE_CURRENT",
        historical_or_current="current", geographic_scope="National + international", endpoint=endpoint,
    )
    outcome["endpoint"] = endpoint
    return outcome


def main():
    print("=" * 60)
    print("ACQUIRE: SUPARCO DisasterWatch (Tier 1)")
    print("=" * 60)

    results = [acquire_one(e["endpoint"], e["filename"]) for e in ENDPOINTS]

    for r in results:
        print(f"{r['status']:8s} | {r['endpoint']}")
        if r["status"] == "ACQUIRED":
            print(f"         -> {r['local_path']} ({r['byte_size']} bytes, sha256={r['sha256'][:12]}...)")

    print("=" * 60)
    return results


if __name__ == "__main__":
    main()
