"""
scripts/acquisition/run_tier1_acquisition.py

Phase 1 / Task 15 (ADR-0001) -- runs all four Tier 1 acquisition
scripts in sequence and writes the run-level summary to
data/raw/manifests/acquisition_summary.json.

Run manually:
    python scripts/acquisition/run_tier1_acquisition.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from scripts.acquisition import (  # noqa: E402
    acquire_aqi_punjab,
    acquire_ffc,
    acquire_ndmc_bulletins,
    acquire_suparco_disasterwatch,
)
from scripts.acquisition.manifest import write_summary  # noqa: E402

SOURCES = [
    ("suparco_disasterwatch", acquire_suparco_disasterwatch.main),
    ("aqi_punjab", acquire_aqi_punjab.main),
    ("ffc", acquire_ffc.main),
    ("pmd_ndmc_bulletins", acquire_ndmc_bulletins.main),
]


def main():
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    print("#" * 60)
    print(f"TASK 15 TIER 1 ACQUISITION RUN -- run_id={run_id}")
    print("#" * 60)

    per_source_results = {}
    for name, fn in SOURCES:
        try:
            per_source_results[name] = fn()
        except Exception as e:
            per_source_results[name] = [{"status": "FAILED", "error_code": "unhandled_exception", "error_message": str(e)}]
            print(f"UNHANDLED EXCEPTION in {name}: {e}")

    completed_at = datetime.now(timezone.utc)

    successful_sources, partial_sources, failed_sources = [], [], []
    total_artifacts, total_bytes = 0, 0
    checksums = []

    for name, results in per_source_results.items():
        acquired = [r for r in results if r.get("status") == "ACQUIRED"]
        failed = [r for r in results if r.get("status") == "FAILED"]

        total_artifacts += len(acquired)
        for r in acquired:
            total_bytes += r.get("byte_size", 0)
            checksums.append({"path": r.get("local_path"), "sha256": r.get("sha256")})

        if acquired and not failed:
            successful_sources.append(name)
        elif acquired and failed:
            partial_sources.append(name)
        else:
            failed_sources.append(name)

    summary = {
        "task": "Task 15 -- Tier 1 National Raw Data Acquisition Foundation",
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "successful_sources": successful_sources,
        "partial_sources": partial_sources,
        "failed_sources": failed_sources,
        "total_artifacts": total_artifacts,
        "total_bytes": total_bytes,
        "checksums": checksums,
        "notes": (
            "Historical PDF archives (FFC DFSR/GLOF, PMD/NDMC Bulletins) were "
            "deliberately downloaded as a small controlled batch (see "
            "MAX_PDF_DOWNLOADS in the respective acquire_*.py scripts), not the "
            "full multi-month archive, per Task 15's explicit instruction not to "
            "download every historical file blindly."
        ),
    }

    write_summary(summary)

    print("#" * 60)
    print("SUMMARY")
    print(f"  successful_sources : {successful_sources}")
    print(f"  partial_sources    : {partial_sources}")
    print(f"  failed_sources     : {failed_sources}")
    print(f"  total_artifacts    : {total_artifacts}")
    print(f"  total_bytes        : {total_bytes}")
    print("#" * 60)

    return summary


if __name__ == "__main__":
    main()
