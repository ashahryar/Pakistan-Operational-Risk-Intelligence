"""
dashboard/utils/geo_helpers.py

Phase 1 / Task 12 (ADR-0001) -- pure aggregation helper for the
Geographic Observation Intelligence section (dashboard/sections/
geo_intelligence.py). No Streamlit import, no database import -- takes
the DataFrame dashboard/db.py::get_geo_summary() already returns (from
Task 11's `geo.resolved_observation_counts` view) and reshapes it for
display. Directly unit-tested by tests/dashboard/test_geo_helpers.py
with small in-memory DataFrames, no live DB required.
"""

from __future__ import annotations

import pandas as pd


def summarize_geo_observations(geo_summary: pd.DataFrame) -> dict:
    """
    `geo_summary` has one row per (admin_unit, source, domain), columns
    admin_unit_id, level, admin_unit_name, source, domain,
    observation_count -- exactly geo.resolved_observation_counts's
    shape.

    Returns:
        {
            "total_observations": int,
            "admin_unit_count": int,
            "by_admin_unit": DataFrame [admin_unit_name, level,
                observation_count], one row per admin unit (summed
                across source/domain), sorted descending,
            "by_source_domain": DataFrame [source, domain,
                observation_count], one row per (source, domain)
                (summed across admin units), sorted descending,
        }

    Never fabricates a count -- this only sums what get_geo_summary()
    already returned; an empty input returns empty outputs, not a
    default/placeholder value (CLAUDE.md rule 7).
    """

    if geo_summary.empty:
        return {
            "total_observations": 0,
            "admin_unit_count": 0,
            "by_admin_unit": pd.DataFrame(
                columns=["admin_unit_name", "level", "observation_count"]
            ),
            "by_source_domain": pd.DataFrame(
                columns=["source", "domain", "observation_count"]
            ),
        }

    total_observations = int(geo_summary["observation_count"].sum())
    admin_unit_count = int(geo_summary["admin_unit_id"].nunique())

    by_admin_unit = (
        geo_summary.groupby(["admin_unit_name", "level"], as_index=False)[
            "observation_count"
        ]
        .sum()
        .sort_values("observation_count", ascending=False)
        .reset_index(drop=True)
    )

    by_source_domain = (
        geo_summary.groupby(["source", "domain"], as_index=False)[
            "observation_count"
        ]
        .sum()
        .sort_values("observation_count", ascending=False)
        .reset_index(drop=True)
    )

    return {
        "total_observations": total_observations,
        "admin_unit_count": admin_unit_count,
        "by_admin_unit": by_admin_unit,
        "by_source_domain": by_source_domain,
    }
