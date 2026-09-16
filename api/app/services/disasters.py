from __future__ import annotations

from api.app.db import fetch_all


def list_casualties(province: str | None = None, limit: int = 200) -> list[dict]:
    """
    Returns rows from ndma_casualties -- the real, DAG-populated,
    Task-6-hardened table. Excludes the same null/blank/"Grand Total"
    summary rows dashboard/db.py already filters
    (`_clean_province_filter()`), reused here for consistency rather
    than reinvented.
    """
    base_filter = "province IS NOT NULL AND TRIM(province) <> '' AND province NOT ILIKE 'grand total'"

    if province:
        query = f"""
            SELECT report_date, province, deaths, injured
            FROM ndma_casualties
            WHERE {base_filter} AND LOWER(province) = LOWER(:province)
            ORDER BY report_date DESC
            LIMIT :limit
        """
        return fetch_all(query, {"province": province, "limit": limit})

    query = f"""
        SELECT report_date, province, deaths, injured
        FROM ndma_casualties
        WHERE {base_filter}
        ORDER BY report_date DESC
        LIMIT :limit
    """
    return fetch_all(query, {"limit": limit})
