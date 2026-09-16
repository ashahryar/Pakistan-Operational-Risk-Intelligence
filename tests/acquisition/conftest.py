"""
tests/acquisition/conftest.py

Phase 1 / Task 15 (ADR-0001) -- shared setup for raw-acquisition-layer
tests. No live network calls in these tests (see test_client.py, which
monkeypatches the HTTP layer) -- fully deterministic, no live DB.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
