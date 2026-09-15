"""
tests/geo/conftest.py

Phase 1 / Task 10 (ADR-0001) -- shared setup for geographic-resolution
tests.

scripts/geo/resolver.py and scripts/geo/canonical_data.py are both
cleanly package-qualified (`scripts.geo.resolver`,
`scripts.geo.canonical_data`) with no bare/relative import landmine
and no database import at all -- neither module touches
config.database. The only thing needed is PROJECT_ROOT on sys.path,
matching tests/parsers/conftest.py and tests/forecasting/conftest.py.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
