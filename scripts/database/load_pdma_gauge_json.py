"""
scripts/database/load_pdma_gauge_json.py

DEPRECATED -- Task 16A (Phase 1 / ADR-0001) safety fix.

This file previously ran its own independent PDMA gauge loader with
an unconditional `TRUNCATE TABLE pdma_gauge_readings RESTART IDENTITY`
and the entire multi-file load wrapped in one `engine.begin()`
transaction (so a single bad row aborted and rolled back everything,
including the truncation), no `write_quarantine` call, and no
rejection-ratio gate -- the same anti-pattern Task 6 removed from the
loaders that DAGs actually run (see docs/architecture/CODEBASE_AUDIT.md).

Not referenced by any DAG (confirmed by grep across `pipeline/dags/`).
Its target columns (`report_datetime`, `station`, `river`,
`current_level_ft`, `danger_level_ft`, `discharge_cusecs`,
`flow_status`) do match the real `pdma_gauge_readings` schema, and its
source folder (`data/parsed/pdma/gauge`) is the same one
`scripts/database/load_pdma.py::load_gauge_readings()` already reads
-- that function is the real, Task-6-hardened implementation (per-row
transaction isolation, `ON CONFLICT DO NOTHING`, `write_quarantine` on
failure, rejection-ratio gate). Rather than maintain two independent
gauge-loading implementations, this file is kept only as a safe,
deprecated entry point that delegates to the real loader, so nothing
that still invokes `python scripts/database/load_pdma_gauge_json.py`
runs the old destructive code path by mistake.
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.database.load_pdma import load_gauge_readings as _load_gauge_readings


def load_json():
    warnings.warn(
        "load_pdma_gauge_json.py is deprecated and no longer runs its "
        "own (TRUNCATE-based) loader. Delegating to "
        "scripts/database/load_pdma.py::load_gauge_readings(), the "
        "real, Task-6-hardened gauge loader. Update callers to use "
        "load_pdma.py directly.",
        DeprecationWarning,
        stacklevel=2,
    )
    print("=" * 60)
    print("load_pdma_gauge_json.py is DEPRECATED -- delegating to load_pdma.py")
    print("=" * 60)

    processed, inserted, skipped, rejected = _load_gauge_readings()

    print()
    print("=" * 60)
    print("PDMA GAUGE LOAD (via load_pdma.py::load_gauge_readings)")
    print("=" * 60)
    print(f"Processed : {processed}")
    print(f"Inserted  : {inserted}")
    print(f"Skipped   : {skipped}")
    print(f"Rejected  : {rejected}")
    print("=" * 60)

    return processed, inserted, skipped, rejected


def main():
    load_json()


if __name__ == "__main__":
    main()
