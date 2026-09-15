"""
tests/dashboard/conftest.py

Phase 1 / Task 12 (ADR-0001) -- shared setup for dashboard helper
tests.

dashboard/utils/geo_helpers.py imports only pandas -- no streamlit, no
database, no .env/dotenv load (that lives in dashboard/db.py, not
imported here). The only thing needed is PROJECT_ROOT on sys.path,
matching tests/geo/conftest.py and tests/forecasting/conftest.py.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
