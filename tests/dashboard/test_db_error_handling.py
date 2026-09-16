"""
tests/dashboard/test_db_error_handling.py

Task 16A (Phase 1 / ADR-0001) -- regression tests for dashboard/db.py's
error-handling fix: `_read_sql()` must distinguish an expected
missing-table/column error (UndefinedTable/UndefinedColumn, SQLSTATE
42P01/42703) from any other, genuinely unexpected failure, instead of
folding both into the same silent "return empty DataFrame, log
nothing distinguishable" path.

These tests exercise the real `_is_missing_relation_error()` function
against synthetic exceptions shaped like real psycopg2/SQLAlchemy
errors -- no live database connection is used or required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.db import _is_missing_relation_error  # noqa: E402


def _fake_db_error(pgcode: str | None) -> Exception:
    """Builds an exception shaped like a real SQLAlchemy DBAPIError:
    exc.orig.pgcode, matching what psycopg2 actually sets."""
    exc = Exception("simulated database error")
    exc.orig = SimpleNamespace(pgcode=pgcode)
    return exc


def test_undefined_table_is_recognized_as_a_missing_relation_error():
    exc = _fake_db_error("42P01")  # Postgres UndefinedTable
    assert _is_missing_relation_error(exc) is True


def test_undefined_column_is_recognized_as_a_missing_relation_error():
    exc = _fake_db_error("42703")  # Postgres UndefinedColumn
    assert _is_missing_relation_error(exc) is True


def test_connection_failure_is_not_a_missing_relation_error():
    exc = _fake_db_error("08006")  # Postgres connection_failure
    assert _is_missing_relation_error(exc) is False


def test_permission_denied_is_not_a_missing_relation_error():
    exc = _fake_db_error("42501")  # Postgres insufficient_privilege
    assert _is_missing_relation_error(exc) is False


def test_exception_with_no_orig_attribute_is_not_a_missing_relation_error():
    """A plain Python exception (e.g. a network timeout raised before
    any DBAPI error object exists) must not be misclassified as an
    expected schema gap."""
    exc = ValueError("something unrelated went wrong")
    assert _is_missing_relation_error(exc) is False


def test_get_latest_weather_and_get_weather_summary_no_longer_reference_pmd_weather():
    """
    Static guard: these two functions previously queried a
    `pmd_weather` table that exists in no DDL script anywhere in the
    repository (docs/architecture/CODEBASE_AUDIT.md). They must now
    read from the real `pmd_daily_forecast` table instead.
    """
    source = (PROJECT_ROOT / "dashboard" / "db.py").read_text(encoding="utf-8")

    start = source.index("def get_latest_weather")
    end = source.index("def get_pdma_rainfall")
    weather_section = source[start:end]

    assert "FROM pmd_weather" not in weather_section
    assert "pmd_daily_forecast" in weather_section
