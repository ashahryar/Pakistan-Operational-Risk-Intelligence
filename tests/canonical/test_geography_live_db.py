"""
tests/canonical/test_geography_live_db.py

Task 18 -- proves build_db_admin_unit_lookup() actually resolves a real
geo.admin_unit.id against the live database (Task 10's seeded
hierarchy), rather than trusting the dict-based unit tests alone.

Entirely read-only: a single SELECT per lookup, no INSERT/UPDATE/
DELETE anywhere in this file. Skips cleanly (not a failure) if no
database is reachable, matching the existing convention in
tests/dashboard/test_weather_summary_live.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _db_reachable() -> bool:
    try:
        from config.database import engine
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="no live database reachable")


def test_db_backed_lookup_resolves_a_real_seeded_province():
    from config.database import engine
    from pipeline.canonical.geography import build_db_admin_unit_lookup

    lookup = build_db_admin_unit_lookup(engine)
    punjab_id = lookup("Punjab")
    assert punjab_id is not None
    assert isinstance(punjab_id, int)


def test_db_backed_lookup_returns_none_for_a_name_not_in_admin_unit():
    from config.database import engine
    from pipeline.canonical.geography import build_db_admin_unit_lookup

    lookup = build_db_admin_unit_lookup(engine)
    assert lookup("Definitely Not A Seeded Admin Unit Name") is None


def test_db_backed_enrichment_end_to_end_via_enrich_location():
    from config.database import engine
    from scripts.geo.canonical_data import PROVINCES
    from pipeline.canonical.geography import build_db_admin_unit_lookup, enrich_location

    lookup = build_db_admin_unit_lookup(engine)
    result = enrich_location("Sindh", PROVINCES, admin_unit_lookup=lookup)
    assert result["resolution_status"] == "resolved"
    assert result["admin_unit_id"] is not None
