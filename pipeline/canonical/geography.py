"""
pipeline/canonical/geography.py

Task 18 (Phase 1 / ADR-0001) -- DB-backed geography enrichment boundary
for the Task 17 canonical layer.

Reuses the Task 10 geographic foundation exactly as-is:
  - scripts/geo/resolver.py::resolve() for exact/alias/normalized/
    fuzzy/ambiguous/unresolved matching (no second resolver).
  - geo.admin_unit for the real database ID (read-only SELECT, the
    same query scripts/geo/resolve_observations.py::_admin_unit_id
    already uses -- not reinvented).

This module never writes to geo.admin_unit or geo.name_alias. It is a
pure, deterministic, idempotent enrichment step: calling it twice with
the same raw value and the same admin_unit_lookup always returns the
same result, and no database row is ever created, updated, or deleted
as a side effect of calling it.
"""

from __future__ import annotations

from typing import Any, Callable

from scripts.geo.resolver import resolve

from pipeline.canonical.normalization import normalize_string

# A lookup callable: canonical admin-unit name -> real geo.admin_unit.id
# (or None if not found / not yet seeded). Injected so this module is
# testable with a plain dict, with no live database required.
AdminUnitLookup = Callable[[str], "int | None"]


def enrich_location(
    raw_value: Any,
    candidates: list[dict],
    *,
    hierarchy_field: str | None = None,
    admin_unit_lookup: AdminUnitLookup | None = None,
) -> dict[str, Any]:
    """
    Resolve one location field against ONE geography level's candidate
    pool (e.g. PROVINCES or DISTRICTS from scripts.geo.canonical_data
    -- callers choose the pool, exactly as
    scripts/geo/resolve_observations.py already does, so this can
    never resolve a province-level value against districts or vice
    versa -- CLAUDE.md rule 7 / Task 10's "never infer a lower
    geographic level" requirement, reused unchanged).

    Returns:
      location_original    -- the trimmed/whitespace-collapsed source
                               text (never destroyed, never guessed).
      admin_unit_id         -- the real geo.admin_unit.id, populated
                               ONLY when resolved AND admin_unit_lookup
                               is supplied and finds a row. Always None
                               for ambiguous/unresolved values, and
                               always None when no lookup is supplied
                               (preserves Task 17's original, DB-free
                               behavior exactly for existing callers).
      admin_unit_key         -- the resolver's matched canonical name
                               (a string), independent of whether a DB
                               lookup was performed -- useful for
                               callers/tests that don't have a database.
      resolution_status      -- 'resolved' | 'ambiguous' | 'unresolved'
      resolution_method      -- 'exact' | 'alias' | 'normalized' |
                               'fuzzy' | 'unresolved'
      resolution_notes       -- resolver's human-readable detail.

    If `hierarchy_field` is given (e.g. "province" or "district"), the
    resolved canonical name is also written under that key (None when
    not resolved) -- purely additive, never fabricated: it is the same
    value already computed by the resolver, just exposed under a
    hierarchy-appropriate field name for records that don't already
    set one from the raw source text.
    """
    original = normalize_string(raw_value)
    resolution = resolve(original, candidates)

    admin_unit_id = None
    if resolution.status == "resolved" and admin_unit_lookup is not None:
        admin_unit_id = admin_unit_lookup(resolution.admin_unit_key)

    result: dict[str, Any] = {
        "location_original": original,
        "admin_unit_id": admin_unit_id,
        "admin_unit_key": resolution.admin_unit_key,
        "resolution_status": resolution.status,
        "resolution_method": resolution.match_method,
        "resolution_notes": resolution.notes,
    }
    if hierarchy_field:
        result[hierarchy_field] = resolution.admin_unit_key if resolution.status == "resolved" else None
    return result


def build_db_admin_unit_lookup(engine) -> AdminUnitLookup:
    """
    Real, read-only geo.admin_unit-backed lookup, for production use.

    Executes exactly the query
    scripts/geo/resolve_observations.py::_admin_unit_id already uses
    (`SELECT id FROM geo.admin_unit WHERE name = :name`) -- not a
    second geography query pattern. Never INSERTs, UPDATEs, or DELETEs
    anything. Results are cached for the lifetime of the returned
    callable (the admin_unit table has ~77 rows and changes rarely;
    this avoids one round-trip per canonical record for a repeated
    location name within a single run).

    `engine` is any SQLAlchemy engine/connectable (typically
    `config.database.engine`) -- not imported here at module level, so
    this module has no import-time database dependency and can be
    unit-tested without one.
    """
    from sqlalchemy import text

    cache: dict[str, int | None] = {}

    def _lookup(name: str) -> int | None:
        if name in cache:
            return cache[name]
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM geo.admin_unit WHERE name = :name"), {"name": name}
            ).fetchone()
        result = row[0] if row else None
        cache[name] = result
        return result

    return _lookup


def build_dict_admin_unit_lookup(mapping: dict[str, int]) -> AdminUnitLookup:
    """
    Test/offline lookup backed by a plain in-memory dict -- no database
    connection of any kind. Used by tests/canonical/test_geography.py
    so geography enrichment is fully testable without touching
    Postgres (Task 18 Part 5's explicit database-safety requirement).
    """

    def _lookup(name: str) -> int | None:
        return mapping.get(name)

    return _lookup
