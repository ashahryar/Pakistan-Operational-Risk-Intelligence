"""
tests/dashboard/test_weather_summary_live.py

Task 16A (Phase 1 / ADR-0001) -- regression test for a real bug found
while verifying the api/ FastAPI foundation against the live database:
dashboard/db.py::get_weather_summary() (fixed earlier in this same
task to stop querying the nonexistent `pmd_weather` table) initially
carried over a `NULLIF(w.temperature, '')::numeric` cast from the old
query, assuming `temperature`/`humidity` were stored as text. They are
actually `REAL` columns in `pmd_daily_forecast`
(scripts/database/create_pmd_tables.py) -- casting a REAL column
against an empty string literal raises
`psycopg2.errors.InvalidTextRepresentation` in real Postgres. This
was caught live (not by a mocked test) precisely because this
session's own `_read_sql()` fix made the failure loud (ERROR-logged
with a full traceback) instead of silently returning an empty
DataFrame -- the error-handling fix and this bug are directly linked.

This test requires a live Postgres connection (the same one the rest
of the project's Docker-based dev environment already provides) and
is skipped if one isn't reachable, matching the project's existing
convention for tests that need real infrastructure (e.g.
tests/acquisition/test_manifest_integrity.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _db_reachable() -> bool:
    """
    Checks reachability via dashboard.db's OWN engine, not
    config.database's -- the two build their connection URL
    differently (dashboard/db.py reads DB_HOST/DB_PORT directly from
    env with no Docker-awareness, unlike config/database.py's
    `/.dockerenv`-based auto-switch between `localhost:5433` and
    `postgres:5432`; a pre-existing difference, not something Task 16A
    introduced). Running this test suite from inside an Airflow
    container (where dashboard/db.py was never designed to run --
    `dashboard` is not one of docker-compose.yml's services) would
    otherwise report the DB as "reachable" via config.database while
    dashboard.db's own connection still fails, causing a false
    failure rather than a correct skip.
    """
    try:
        from dashboard.db import get_engine
        from sqlalchemy import text
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="no live database reachable")


def test_get_weather_summary_does_not_raise_on_real_data():
    from dashboard.db import get_weather_summary

    df = get_weather_summary()

    # A DataError here (the original bug) would be silently swallowed
    # by _read_sql() and returned as an empty DataFrame -- so the real
    # assertion is that the query succeeded (non-empty), not just that
    # no exception propagated.
    assert not df.empty
    assert "avg_temperature" in df.columns


def test_get_latest_weather_returns_real_typed_temperature_and_humidity():
    from dashboard.db import get_latest_weather

    df = get_latest_weather()

    assert not df.empty
    # Confirms the REAL-column fix: these must be numeric, not strings
    # left over from the old (incorrect) text-column assumption.
    import pandas as pd
    assert pd.api.types.is_numeric_dtype(df["max_temperature"])
    assert pd.api.types.is_numeric_dtype(df["humidity"])
