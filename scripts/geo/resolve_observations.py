"""
scripts/geo/resolve_observations.py

Phase 1 / Task 10 (ADR-0001) -- read-only analysis + idempotent write:
resolves every real, live, distinct raw geographic value across the
project's existing tables into geo.name_alias, using
scripts/geo/resolver.py against the canonical hierarchy seeded by
seed_admin_units.py.

NO existing table (ndma_*/pdma_*/pmd_*) is written to or schema-
changed -- every SELECT here is read-only. Every raw value that exists
gets exactly one geo.name_alias row (resolved, ambiguous, or
unresolved) -- nothing is silently dropped, matching the
write_quarantine/dq.quarantine "nothing simply disappears" discipline
already established in Tasks 5-6, applied to geography instead of
parse/load rejections.

Target (source, domain, table, column) combinations -- 8 real ones,
covering every geography-bearing column that fits the province/
district model. `pdma_gauge_readings.river` is deliberately NOT
resolved here: a river is not an administrative unit, and forcing it
into a province/district hierarchy would misrepresent what it is --
out of scope for this MVP, noted in docs/geo/GEOGRAPHIC_FOUNDATION.md.
`ndma_relief.province` is deliberately excluded: live profiling found
this column actually holds relief-item names, not provinces (a
pre-existing loader/parser bug, not fixed here -- see the module
docstring in docs/geo/GEOGRAPHIC_FOUNDATION.md).

  1. ndma      / casualties        / ndma_casualties.province         -> PROVINCES
  2. ndma      / damage            / ndma_damage.province             -> PROVINCES
  3. ndma      / rescue            / ndma_rescue.province             -> PROVINCES
  4. pdma      / gauge_station     / pdma_gauge_readings.station      -> DISTRICTS
  5. pdma      / rainfall_station  / pdma_rainfall_readings.station   -> DISTRICTS
  6. pmd       / pmd_city          / pmd_daily_forecast.city          -> PROVINCES,
                                                                          via the
                                                                          existing,
                                                                          already-
                                                                          in-production
                                                                          CITY_PROVINCE
                                                                          map, falling
                                                                          back to a
                                                                          direct DISTRICTS
                                                                          match for
                                                                          cities CITY_PROVINCE
                                                                          doesn't cover
  7. pmd       / pmd_weekly_region / pmd_weekly_outlook.regions (JSONB array) -> PROVINCES
  8. pmd       / pmd_alert_region  / pmd_weather_alerts.regions (JSONB array) -> PROVINCES

Run manually, after seed_admin_units.py:
    python scripts/geo/resolve_observations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from config.database import engine  # noqa: E402
from scripts.geo.canonical_data import DISTRICTS, PROVINCES  # noqa: E402
from scripts.geo.resolver import resolve  # noqa: E402
from scripts.parsing.pmd.utils import CITY_PROVINCE  # noqa: E402


def _query_to_rows(conn, query, params=None):
    result = conn.execute(text(query), params or {})
    return result.fetchall()


def _admin_unit_id(conn, name: str | None):
    if name is None:
        return None
    row = conn.execute(
        text("SELECT id FROM geo.admin_unit WHERE name = :name"), {"name": name}
    ).fetchone()
    return row[0] if row else None


def _upsert_alias(conn, raw_name, normalized_name, source, domain, admin_unit_id, match_method, confidence, status, notes):
    conn.execute(
        text("""
            INSERT INTO geo.name_alias
                (raw_name, normalized_name, source, domain, admin_unit_id, match_method, confidence, status, notes)
            VALUES
                (:raw_name, :normalized_name, :source, :domain, :admin_unit_id, :match_method, :confidence, :status, :notes)
            ON CONFLICT (raw_name, source, domain) DO UPDATE SET
                normalized_name = EXCLUDED.normalized_name,
                admin_unit_id   = EXCLUDED.admin_unit_id,
                match_method    = EXCLUDED.match_method,
                confidence      = EXCLUDED.confidence,
                status          = EXCLUDED.status,
                notes           = EXCLUDED.notes,
                resolved_at     = CURRENT_TIMESTAMP
        """),
        {
            "raw_name": raw_name, "normalized_name": normalized_name,
            "source": source, "domain": domain, "admin_unit_id": admin_unit_id,
            "match_method": match_method, "confidence": confidence,
            "status": status, "notes": notes,
        },
    )


def _resolve_and_store(conn, raw_name, source, domain, candidates, counts):
    from scripts.geo.resolver import normalize_name

    resolution = resolve(raw_name, candidates)
    admin_unit_id = _admin_unit_id(conn, resolution.admin_unit_key)
    _upsert_alias(
        conn, raw_name, normalize_name(raw_name), source, domain,
        admin_unit_id, resolution.match_method, resolution.confidence,
        resolution.status, resolution.notes,
    )
    counts[resolution.status] = counts.get(resolution.status, 0) + 1


def _resolve_pmd_city(conn, raw_city, counts):
    """
    Two-step: prefer the existing, already-in-production
    scripts.parsing.pmd.utils.CITY_PROVINCE mapping (reused, not
    re-derived); fall back to a direct DISTRICTS match for cities that
    mapping doesn't cover -- some of those (e.g. "Dera Ismail Khan")
    ARE in the canonical district list even though CITY_PROVINCE
    doesn't know them, a real (small) improvement over today's
    production "Unknown" outcome. Cities matching neither (e.g.
    Indian-administered-Kashmir towns like Srinagar/Jammu/Anantnag)
    correctly stay unresolved -- not fabricated.
    """
    province_raw = CITY_PROVINCE.get(raw_city)
    if province_raw is not None:
        resolution = resolve(province_raw, PROVINCES)
        if resolution.status == "resolved":
            from scripts.geo.resolver import normalize_name

            admin_unit_id = _admin_unit_id(conn, resolution.admin_unit_key)
            _upsert_alias(
                conn, raw_city, normalize_name(raw_city), "pmd", "pmd_city",
                admin_unit_id, "alias", None, "resolved",
                f"resolved via existing scripts.parsing.pmd.utils.CITY_PROVINCE mapping to {province_raw!r}",
            )
            counts["resolved"] = counts.get("resolved", 0) + 1
            return

    # Fall back: try the raw city name directly against DISTRICTS.
    _resolve_and_store(conn, raw_city, "pmd", "pmd_city", DISTRICTS, counts)


def main():
    print("=" * 60)
    print("RESOLVE OBSERVATIONS -> geo.name_alias")
    print("=" * 60)

    summary = {}

    with engine.begin() as conn:
        # ---- NDMA provinces (casualties/damage/rescue -- relief excluded, see module docstring) ----
        for table, domain in (
            ("ndma_casualties", "casualties"),
            ("ndma_damage", "damage"),
            ("ndma_rescue", "rescue"),
        ):
            counts = {}
            rows = _query_to_rows(conn, f"SELECT DISTINCT province FROM {table} WHERE province IS NOT NULL")
            for (raw,) in rows:
                _resolve_and_store(conn, raw, "ndma", domain, PROVINCES, counts)
            summary[f"ndma/{domain}"] = counts
            print(f"ndma/{domain:12s} ({table}.province): {counts}")

        # ---- PDMA gauge stations ----
        counts = {}
        rows = _query_to_rows(conn, "SELECT DISTINCT station FROM pdma_gauge_readings WHERE station IS NOT NULL")
        for (raw,) in rows:
            _resolve_and_store(conn, raw, "pdma", "gauge_station", DISTRICTS, counts)
        summary["pdma/gauge_station"] = counts
        print(f"pdma/gauge_station  (pdma_gauge_readings.station): {counts}")

        # ---- PDMA rainfall stations (often comma-separated multi-district strings) ----
        counts = {}
        rows = _query_to_rows(conn, "SELECT DISTINCT station FROM pdma_rainfall_readings WHERE station IS NOT NULL")
        for (raw,) in rows:
            _resolve_and_store(conn, raw, "pdma", "rainfall_station", DISTRICTS, counts)
        summary["pdma/rainfall_station"] = counts
        print(f"pdma/rainfall_station (pdma_rainfall_readings.station): {counts}")

        # ---- PMD cities ----
        counts = {}
        rows = _query_to_rows(conn, "SELECT DISTINCT city FROM pmd_daily_forecast WHERE city IS NOT NULL")
        for (raw,) in rows:
            _resolve_pmd_city(conn, raw, counts)
        summary["pmd/pmd_city"] = counts
        print(f"pmd/pmd_city        (pmd_daily_forecast.city): {counts}")

        # ---- PMD weekly outlook / weather alert regions (JSONB arrays of province names) ----
        for table, domain in (
            ("pmd_weekly_outlook", "pmd_weekly_region"),
            ("pmd_weather_alerts", "pmd_alert_region"),
        ):
            counts = {}
            rows = _query_to_rows(conn, f"SELECT regions FROM {table} WHERE regions IS NOT NULL")
            seen = set()
            for (regions,) in rows:
                for raw in (regions or []):
                    if raw in seen:
                        continue
                    seen.add(raw)
                    _resolve_and_store(conn, raw, "pmd", domain, PROVINCES, counts)
            summary[f"pmd/{domain}"] = counts
            print(f"pmd/{domain:17s} ({table}.regions): {counts}")

    print("=" * 60)
    print("SUMMARY")
    total_resolved = sum(c.get("resolved", 0) for c in summary.values())
    total_ambiguous = sum(c.get("ambiguous", 0) for c in summary.values())
    total_unresolved = sum(c.get("unresolved", 0) for c in summary.values())
    print(f"  resolved   : {total_resolved}")
    print(f"  ambiguous  : {total_ambiguous}")
    print(f"  unresolved : {total_unresolved}")
    print("=" * 60)


if __name__ == "__main__":
    main()
