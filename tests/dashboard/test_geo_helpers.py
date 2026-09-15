"""
tests/dashboard/test_geo_helpers.py

Phase 1 / Task 12 (ADR-0001) -- deterministic tests for
dashboard/utils/geo_helpers.py::summarize_geo_observations(). No live
DB, no Streamlit, no internet -- pure function tested against small
in-memory DataFrames shaped exactly like
dashboard/db.py::get_geo_summary()'s real columns (admin_unit_id,
level, admin_unit_name, source, domain, observation_count).
"""

from __future__ import annotations

import pandas as pd

from dashboard.utils.geo_helpers import summarize_geo_observations


def _row(admin_unit_id, level, name, source, domain, count):
    return {
        "admin_unit_id": admin_unit_id,
        "level": level,
        "admin_unit_name": name,
        "source": source,
        "domain": domain,
        "observation_count": count,
    }


def test_summarize_empty_input_returns_zeros_not_fabricated_values():
    stats = summarize_geo_observations(pd.DataFrame(
        columns=["admin_unit_id", "level", "admin_unit_name", "source", "domain", "observation_count"]
    ))

    assert stats["total_observations"] == 0
    assert stats["admin_unit_count"] == 0
    assert stats["by_admin_unit"].empty
    assert stats["by_source_domain"].empty


def test_summarize_totals_and_admin_unit_count():
    df = pd.DataFrame([
        _row(2, 1, "Punjab", "ndma", "casualties", 69),
        _row(2, 1, "Punjab", "ndma", "damage", 64),
        _row(3, 1, "Sindh", "ndma", "casualties", 69),
    ])

    stats = summarize_geo_observations(df)

    assert stats["total_observations"] == 69 + 64 + 69
    # 2 distinct admin_unit_id values (Punjab, Sindh), even though
    # Punjab appears in 2 rows.
    assert stats["admin_unit_count"] == 2


def test_by_admin_unit_sums_across_source_domain_and_sorts_descending():
    df = pd.DataFrame([
        _row(2, 1, "Punjab", "ndma", "casualties", 10),
        _row(2, 1, "Punjab", "pmd", "pmd_city", 5),
        _row(3, 1, "Sindh", "ndma", "casualties", 100),
    ])

    stats = summarize_geo_observations(df)
    by_unit = stats["by_admin_unit"]

    assert list(by_unit["admin_unit_name"]) == ["Sindh", "Punjab"]
    assert list(by_unit["observation_count"]) == [100, 15]


def test_by_source_domain_sums_across_admin_units_and_sorts_descending():
    df = pd.DataFrame([
        _row(2, 1, "Punjab", "pdma", "rainfall_station", 20),
        _row(9, 2, "Attock", "pdma", "rainfall_station", 22),
        _row(7, 1, "AJK", "ndma", "casualties", 5),
    ])

    stats = summarize_geo_observations(df)
    by_domain = stats["by_source_domain"]

    assert list(by_domain[["source", "domain"]].itertuples(index=False, name=None)) == [
        ("pdma", "rainfall_station"),
        ("ndma", "casualties"),
    ]
    assert list(by_domain["observation_count"]) == [42, 5]


def test_summarize_never_mutates_the_input_dataframe():
    df = pd.DataFrame([_row(2, 1, "Punjab", "ndma", "casualties", 10)])
    original = df.copy(deep=True)

    summarize_geo_observations(df)

    pd.testing.assert_frame_equal(df, original)
