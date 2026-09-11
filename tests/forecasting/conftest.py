"""
tests/forecasting/conftest.py

Phase 1 / Task 9 (ADR-0001) -- shared setup for forecasting tests.

Unlike tests/parsers/conftest.py, scripts/forecasting/features.py and
scripts/forecasting/gauge_discharge_forecast.py have no bare/relative
import landmine -- both are cleanly package-qualified
(`scripts.forecasting.features`) and neither opens a database
connection at import time (config.database's `engine` is created lazily
by SQLAlchemy; it does not connect until a query actually runs, and
these tests never call the DB-touching functions in
gauge_discharge_forecast.py -- only the pure, DB-free functions).

The only thing needed is PROJECT_ROOT on sys.path, so
`from scripts.forecasting.features import ...` resolves the same way
it would for any other package-qualified import in this repo.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
