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


def list_admin_unit_summaries(level: int | None = None, province: str | None = None, limit: int = 500) -> list[dict]:
    """Canonical admin units with geometry availability (Task 26). Reads geo.admin_unit + geo.current_boundary only."""
    query = """
        SELECT u.id, u.name, u.level,
               CASE WHEN u.level = 1 THEN u.name ELSE p.name END AS province,
               (cb.pori_admin_unit_id IS NOT NULL) AS has_geometry, cb.boundary_source
        FROM geo.admin_unit u
        LEFT JOIN geo.admin_unit p ON p.id = u.parent_id AND p.level = 1
        LEFT JOIN geo.current_boundary cb ON cb.pori_admin_unit_id = u.id
        WHERE (CAST(:level AS int) IS NULL OR u.level = :level)
          AND (CAST(:province AS text) IS NULL OR lower(CASE WHEN u.level = 1 THEN u.name ELSE p.name END) = lower(:province))
        ORDER BY u.level, u.name LIMIT :limit
    """
    return fetch_all(query, {"level": level, "province": province, "limit": limit})


def admin_unit_exists(admin_unit_id: int) -> bool:
    return bool(fetch_all("SELECT 1 AS ok FROM geo.admin_unit WHERE id = :id", {"id": admin_unit_id}))


def list_boundaries(level: int | None = None, province: str | None = None, source: str | None = None,
                    limit: int = 500) -> list[dict]:
    """Boundary units (no geometry) with their crosswalk result. Unmatched boundaries are included, never hidden."""
    query = """
        SELECT b.boundary_id, b.source_feature_id, b.name, b.level,
               CASE WHEN b.level = 1 THEN b.name ELSE pb.name END AS province,
               s.source_key AS source, s.dataset_version AS source_version, b.geometry_valid,
               cw.match_status, cw.pori_admin_unit_id, u.name AS pori_admin_unit_name
        FROM geo.boundary_admin_unit b
        JOIN geo.boundary_source s ON s.source_id = b.source_id
        LEFT JOIN geo.boundary_admin_unit pb ON pb.boundary_id = b.parent_boundary_id
        LEFT JOIN geo.boundary_crosswalk cw ON cw.boundary_id = b.boundary_id
        LEFT JOIN geo.admin_unit u ON u.id = cw.pori_admin_unit_id
        WHERE (CAST(:level AS int) IS NULL OR b.level = :level)
          AND (CAST(:source AS text) IS NULL OR s.source_key = :source)
          AND (CAST(:province AS text) IS NULL OR lower(CASE WHEN b.level = 1 THEN b.name ELSE pb.name END) = lower(:province))
        ORDER BY b.level, b.name LIMIT :limit
    """
    return fetch_all(query, {"level": level, "province": province, "source": source, "limit": limit})
