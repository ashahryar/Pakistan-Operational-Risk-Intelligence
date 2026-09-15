"""
tests/geo/test_summary_format.py

Phase 1 / Task 11 (ADR-0001) -- deterministic tests for
scripts/geo/summary_format.py::build_summary_records(). No live DB, no
internet -- pure function tested against small in-memory row lists
shaped exactly like geo.resolved_observation_counts's real columns
(admin_unit_id, level, admin_unit_name, source, domain,
observation_count).
"""

from __future__ import annotations

from scripts.geo.summary_format import build_summary_records


def test_build_summary_records_maps_columns_correctly():
    rows = [(3, 1, "Punjab", "ndma", "casualties", 312)]
    records = build_summary_records(rows, "2026-09-15T00:00:00+00:00")

    assert records == [
        {
            "admin_unit_id": 3,
            "level": 1,
            "admin_unit_name": "Punjab",
            "source": "ndma",
            "domain": "casualties",
            "observation_count": 312,
            "generated_at": "2026-09-15T00:00:00+00:00",
        }
    ]


def test_build_summary_records_empty_input():
    assert build_summary_records([], "2026-09-15T00:00:00+00:00") == []


def test_build_summary_records_deterministic_order_regardless_of_input_order():
    # Deliberately unsorted input (as a live DB's UNION ALL row order
    # is not guaranteed) -- output must be stable/sorted every time.
    rows = [
        (5, 2, "Rajanpur", "pdma", "gauge_station", 7),
        (3, 1, "Punjab", "ndma", "damage", 44),
        (3, 1, "Punjab", "ndma", "casualties", 312),
    ]
    records_a = build_summary_records(rows, "t")
    records_b = build_summary_records(list(reversed(rows)), "t")

    assert records_a == records_b
    assert [r["admin_unit_name"] for r in records_a] == ["Punjab", "Punjab", "Rajanpur"]
    assert [r["domain"] for r in records_a[:2]] == ["casualties", "damage"]


def test_build_summary_records_preserves_all_required_keys():
    rows = [(1, 0, "Pakistan", "ndma", "casualties", 1)]
    records = build_summary_records(rows, "t")
    required_keys = {
        "admin_unit_id", "level", "admin_unit_name",
        "source", "domain", "observation_count", "generated_at",
    }
    assert set(records[0].keys()) == required_keys


def test_build_summary_records_does_not_mutate_or_fabricate_counts():
    # The function must pass counts through unchanged -- never round,
    # clamp, or default a count (CLAUDE.md rule 7: never fabricate).
    rows = [(1, 1, "Sindh", "pdma", "rainfall_station", 0), (2, 1, "Sindh", "pdma", "gauge_station", 9999)]
    records = build_summary_records(rows, "t")
    counts = {r["domain"]: r["observation_count"] for r in records}
    assert counts == {"rainfall_station": 0, "gauge_station": 9999}
