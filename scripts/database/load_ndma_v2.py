"""
scripts/database/load_ndma_v2.py

DEPRECATED -- Task 16A (Phase 1 / ADR-0001) safety fix.

This file previously ran its own independent NDMA loader with an
unconditional `TRUNCATE ... CASCADE` on all four NDMA tables, one
`engine.begin()` transaction wrapping the entire multi-file load (so
a single bad row aborted and rolled back everything, including the
truncation), no `write_quarantine` call, and no rejection-ratio gate.
Its INSERT column lists (`source_file`, `district`, `houses_damaged`,
`roads_damaged`, `bridges_damaged`, `camps`, `beneficiaries`,
`rescued_people`) did not match `scripts/database/create_tables.py`'s
actual DDL at all -- running it against the current schema would have
raised `UndefinedColumn` on the very first row (confirmed by direct
comparison during the Task 16 audit, docs/architecture/CODEBASE_AUDIT.md).

Not referenced by any DAG (confirmed by grep across `pipeline/dags/`).
The real, Task-6-hardened NDMA loader is `scripts/database/load_ndma.py`
-- it already implements everything this file was trying to do
(per-row transaction isolation, no TRUNCATE, quarantine on failure,
rejection-ratio gate) against the columns that actually exist. Rather
than maintain two independent NDMA-loading implementations, this file
is kept only as a safe, deprecated entry point that delegates to the
real loader, so nothing that still invokes
`python scripts/database/load_ndma_v2.py` runs the old destructive
code path by mistake.
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.database.load_ndma import main as _load_ndma_main


def load_json():
    warnings.warn(
        "load_ndma_v2.py is deprecated and no longer runs its own "
        "(schema-incompatible, TRUNCATE-based) loader. Delegating to "
        "scripts/database/load_ndma.py, the real, Task-6-hardened "
        "NDMA loader. Update callers to use load_ndma.py directly.",
        DeprecationWarning,
        stacklevel=2,
    )
    print("=" * 60)
    print("load_ndma_v2.py is DEPRECATED -- delegating to load_ndma.py")
    print("=" * 60)
    _load_ndma_main()


def main():
    load_json()


if __name__ == "__main__":
    main()
