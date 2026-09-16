"""
tests/database/test_legacy_loader_safety.py

Task 16A (Phase 1 / ADR-0001) -- regression tests proving the two
unsafe legacy loaders flagged by the Task 16 audit
(docs/architecture/CODEBASE_AUDIT.md) no longer contain destructive
SQL:

  - scripts/database/load_ndma_v2.py       (was: unconditional TRUNCATE,
                                             one whole-load transaction,
                                             column lists that didn't
                                             match the current schema)
  - scripts/database/load_pdma_gauge_json.py (was: unconditional TRUNCATE,
                                             one whole-load transaction)

Both are now thin, deprecated wrappers delegating to the real,
Task-6-hardened loaders (load_ndma.py / load_pdma.py::load_gauge_readings).
These tests check the actual current source of both files (not a
re-implementation of the fix) and confirm the delegation actually
happens, using a fully mocked database so no live connection is used.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _mock_out_database_engine(monkeypatch):
    """
    scripts/database/load_ndma.py and load_pdma.py both do
    `from config.database import engine` at import time. Mock
    config.database.engine to a MagicMock BEFORE either module is
    first imported, so importing them never opens a real connection --
    matching the established pattern already used by
    tests/parsers/test_type_coercion.py for the same reason.
    """
    import config.database as db_module

    fake_engine = MagicMock()
    monkeypatch.setattr(db_module, "engine", fake_engine)
    return fake_engine


@pytest.fixture
def clean_modules(monkeypatch):
    """Remove any previously-imported copies of the modules under test
    so each test gets a fresh import against the mocked engine."""
    for name in [
        "scripts.database.load_ndma_v2",
        "scripts.database.load_ndma",
        "scripts.database.load_pdma_gauge_json",
        "scripts.database.load_pdma",
    ]:
        sys.modules.pop(name, None)
    yield
    for name in [
        "scripts.database.load_ndma_v2",
        "scripts.database.load_ndma",
        "scripts.database.load_pdma_gauge_json",
        "scripts.database.load_pdma",
    ]:
        sys.modules.pop(name, None)


def _executable_lines(source: str) -> str:
    """Strips the module docstring (which documents the historical bug
    in prose, including the literal word TRUNCATE) so these checks
    look only at real, executable code."""
    import ast
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree) or ""
    return source.replace(docstring, "")


def test_neither_loader_executes_sql_directly_anymore(clean_modules):
    """Both wrappers should contain zero conn.execute()/engine.begin()
    calls -- all SQL now lives exclusively in the real, hardened
    loaders they delegate to."""
    for fname in ("load_ndma_v2.py", "load_pdma_gauge_json.py"):
        source = _executable_lines((PROJECT_ROOT / "scripts" / "database" / fname).read_text(encoding="utf-8"))
        assert "conn.execute" not in source, f"{fname} still executes SQL directly"
        assert "engine.begin" not in source, f"{fname} still opens its own transaction"


def test_load_ndma_v2_delegates_to_the_real_load_ndma_main(monkeypatch, clean_modules):
    _mock_out_database_engine(monkeypatch)

    import scripts.database.load_ndma as real_ndma_loader
    called = {"count": 0}

    def fake_main():
        called["count"] += 1

    monkeypatch.setattr(real_ndma_loader, "main", fake_main)

    import scripts.database.load_ndma_v2 as v2
    monkeypatch.setattr(v2, "_load_ndma_main", fake_main)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        v2.main()

    assert called["count"] == 1
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_load_pdma_gauge_json_delegates_to_the_real_gauge_loader(monkeypatch, clean_modules):
    _mock_out_database_engine(monkeypatch)

    import scripts.database.load_pdma_gauge_json as wrapper

    def fake_load_gauge_readings():
        return (5, 4, 1, 0)

    monkeypatch.setattr(wrapper, "_load_gauge_readings", fake_load_gauge_readings)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = wrapper.load_json()

    assert result == (5, 4, 1, 0)
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_load_ndma_v2_no_longer_defines_schema_incompatible_sql(clean_modules):
    """
    The old version defined CASUALTIES_SQL/DAMAGE_SQL/RELIEF_SQL/
    RESCUE_SQL INSERT statements referencing columns (source_file,
    district, houses_damaged, ...) that do not exist in
    create_tables.py's DDL. Confirm those are gone, not just unused.
    """
    source = _executable_lines((PROJECT_ROOT / "scripts" / "database" / "load_ndma_v2.py").read_text(encoding="utf-8"))
    for stale_column in ("houses_damaged", "roads_damaged", "bridges_damaged", "camps", "beneficiaries", "rescued_people"):
        assert stale_column not in source, f"{stale_column!r} (schema-incompatible column) still referenced"
