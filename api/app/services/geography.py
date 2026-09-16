from __future__ import annotations

from api.app.db import fetch_all


def list_admin_units(level: int | None = None, limit: int = 500) -> list[dict]:
    """
    Returns rows from geo.admin_unit (Task 10/11, ADR-0001) -- the
    project's real, canonical geography table, not a hardcoded
    province list. `level` optionally filters to one admin level
    (0=country, 1=province, 2=district).
    """
    if level is not None:
        query = (
            "SELECT id, level, name, parent_id, pcode, country, latitude, longitude, source "
            "FROM geo.admin_unit WHERE level = :level ORDER BY name LIMIT :limit"
        )
        return fetch_all(query, {"level": level, "limit": limit})

    query = (
        "SELECT id, level, name, parent_id, pcode, country, latitude, longitude, source "
        "FROM geo.admin_unit ORDER BY level, name LIMIT :limit"
    )
    return fetch_all(query, {"limit": limit})
