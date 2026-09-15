"""
scripts/geo/summary_format.py

Phase 1 / Task 11 (ADR-0001) -- pure formatting logic for
scripts/geo/geo_summary.py. No database import, no I/O -- directly
unit-tested by tests/geo/test_summary_format.py with small in-memory
row lists.
"""

from __future__ import annotations


def build_summary_records(rows: list[tuple], generated_at: str) -> list[dict]:
    """
    Converts raw `geo.resolved_observation_counts` query result rows
    -- (admin_unit_id, level, admin_unit_name, source, domain,
    observation_count) tuples -- into the flat-object JSON house style
    already used by data/analytics/ndma/*.json and
    data/analytics/pdma/gauge_forecast.json (Task 9).

    Pure function: does not touch the database, does not sort by
    anything database-dependent (sorts deterministically by
    admin_unit_name then domain, so output is stable across runs
    regardless of the database's own row order).
    """
    records = [
        {
            "admin_unit_id": admin_unit_id,
            "level": level,
            "admin_unit_name": admin_unit_name,
            "source": source,
            "domain": domain,
            "observation_count": observation_count,
            "generated_at": generated_at,
        }
        for admin_unit_id, level, admin_unit_name, source, domain, observation_count in rows
    ]
    records.sort(key=lambda r: (r["admin_unit_name"], r["source"], r["domain"]))
    return records
