"""
scripts/geo/seed_admin_units.py

Phase 1 / Task 10 (ADR-0001) -- idempotent seed script: loads the
canonical province/district hierarchy from scripts/geo/canonical_data.py
into geo.admin_unit (created by
scripts/database/create_geo_schema_tables.py -- run that first).

Idempotent: every INSERT uses ON CONFLICT (level, name, parent_id) DO
NOTHING, so re-running this script after new data lands is always safe
and never duplicates rows. No existing table (outside geo.*) is read
or written.

Run manually, after create_geo_schema_tables.py and after a verified
backup (CLAUDE.md rule 2):
    python scripts/geo/seed_admin_units.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from config.database import engine  # noqa: E402
from scripts.geo.canonical_data import DISTRICTS, PROVINCES  # noqa: E402

COUNTRY_LEVEL = 0
PROVINCE_LEVEL = 1
DISTRICT_LEVEL = 2


def _upsert_and_get_id(conn, level: int, name: str, parent_id, pcode, lat, lon, source) -> int:
    conn.execute(
        text("""
            INSERT INTO geo.admin_unit (level, name, parent_id, pcode, latitude, longitude, source)
            VALUES (:level, :name, :parent_id, :pcode, :lat, :lon, :source)
            ON CONFLICT (level, name, parent_id) DO NOTHING
        """),
        {
            "level": level, "name": name, "parent_id": parent_id,
            "pcode": pcode, "lat": lat, "lon": lon, "source": source,
        },
    )
    row = conn.execute(
        text("""
            SELECT id FROM geo.admin_unit
            WHERE level = :level AND name = :name
              AND (parent_id = :parent_id OR (:parent_id IS NULL AND parent_id IS NULL))
        """),
        {"level": level, "name": name, "parent_id": parent_id},
    ).fetchone()
    return row[0]


def main():
    print("=" * 60)
    print("SEED GEO.ADMIN_UNIT")
    print("=" * 60)

    province_ids: dict[str, int] = {}
    province_inserted = 0
    district_inserted = 0

    with engine.begin() as conn:
        # Country row (level 0), parent of every province.
        country_id = _upsert_and_get_id(
            conn, COUNTRY_LEVEL, "Pakistan", None, None, None, None, "manual"
        )

        for p in PROVINCES:
            before = conn.execute(text("SELECT count(*) FROM geo.admin_unit")).scalar()
            pid = _upsert_and_get_id(
                conn, PROVINCE_LEVEL, p["name"], country_id, None, None, None, p["source"]
            )
            after = conn.execute(text("SELECT count(*) FROM geo.admin_unit")).scalar()
            if after > before:
                province_inserted += 1
            province_ids[p["name"]] = pid

        for d in DISTRICTS:
            parent_id = province_ids[d["province"]]
            before = conn.execute(text("SELECT count(*) FROM geo.admin_unit")).scalar()
            _upsert_and_get_id(
                conn, DISTRICT_LEVEL, d["name"], parent_id, None, d["lat"], d["lon"], d["source"]
            )
            after = conn.execute(text("SELECT count(*) FROM geo.admin_unit")).scalar()
            if after > before:
                district_inserted += 1

    print(f"Provinces inserted : {province_inserted} / {len(PROVINCES)} (rest already existed)")
    print(f"Districts inserted : {district_inserted} / {len(DISTRICTS)} (rest already existed)")
    print("=" * 60)


if __name__ == "__main__":
    main()
