"""
tests/source_inventory/conftest.py

Phase 1 / Task 13 (ADR-0001) -- shared setup for source-inventory
validation tests. Reads the checked-in
docs/source_inventory/source_inventory.csv directly off disk -- no
database, no internet, deterministic (the CSV is a static repo file,
not fetched live).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INVENTORY_CSV = PROJECT_ROOT / "docs" / "source_inventory" / "source_inventory.csv"
