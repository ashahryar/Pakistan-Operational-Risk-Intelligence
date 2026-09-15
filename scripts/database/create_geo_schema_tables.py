"""
scripts/database/create_geo_schema_tables.py

Phase 1 / Task 10 (ADR-0001) — DDL only. Creates the `geo` schema and
its two tables: `geo.admin_unit` (canonical province/district
hierarchy) and `geo.name_alias` (source-specific name -> canonical
unit resolution, with provenance/status).

NOT an authoritative government boundary dataset -- see
scripts/geo/canonical_data.py's module docstring and
docs/geo/GEOGRAPHIC_FOUNDATION.md for exactly what these tables are
seeded from (the repo's own existing geo_locations seed list +
data/master/district_master.csv) and what they are not (no HDX/GADM/
P-code data, no PostGIS, no tehsil level).

Zero existing table's schema changes. Fully reversible: `DROP SCHEMA
geo CASCADE` removes 100% of this task's database footprint with no
effect on any other table (nothing outside `geo.*` references into
it).

Per CLAUDE.md rule 2, this must NOT be run against the live database
without a fresh, restore-verified pg_dump taken first. It is a one-off,
hand-run script (not wired into any DAG) — Alembic becomes the only
schema-change mechanism once Phase 1 lands (CLAUDE.md rule 4); Phase 1
itself is still in progress, so a single hand-run DDL script is
consistent with the current rules (same pattern as Task 5's
create_dq_tables.py).

Run manually:
    python scripts/database/create_geo_schema_tables.py
"""

from sqlalchemy import text

from config.database import engine


DDL_STATEMENTS = [

    "CREATE SCHEMA IF NOT EXISTS geo;",

    """
    CREATE TABLE IF NOT EXISTS geo.admin_unit (
        id          SERIAL PRIMARY KEY,
        level       SMALLINT NOT NULL,
        name        TEXT NOT NULL,
        parent_id   INTEGER REFERENCES geo.admin_unit(id),
        pcode       TEXT,
        country     TEXT NOT NULL DEFAULT 'Pakistan',
        latitude    DOUBLE PRECISION,
        longitude   DOUBLE PRECISION,
        source      TEXT NOT NULL,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(level, name, parent_id)
    );
    """,

    """
    CREATE TABLE IF NOT EXISTS geo.name_alias (
        id               SERIAL PRIMARY KEY,
        raw_name         TEXT NOT NULL,
        normalized_name  TEXT NOT NULL,
        source           TEXT NOT NULL,
        domain           TEXT NOT NULL,
        admin_unit_id    INTEGER REFERENCES geo.admin_unit(id),
        match_method     TEXT NOT NULL,
        confidence       NUMERIC,
        status           TEXT NOT NULL,
        notes            TEXT,
        resolved_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(raw_name, source, domain)
    );
    """,

    "CREATE INDEX IF NOT EXISTS ix_admin_unit_level ON geo.admin_unit (level);",
    "CREATE INDEX IF NOT EXISTS ix_admin_unit_parent ON geo.admin_unit (parent_id);",
    "CREATE INDEX IF NOT EXISTS ix_name_alias_status ON geo.name_alias (status);",
    "CREATE INDEX IF NOT EXISTS ix_name_alias_admin_unit ON geo.name_alias (admin_unit_id);",

]


def main():

    print("=" * 60)
    print("CREATE GEO SCHEMA TABLES")
    print("=" * 60)

    with engine.begin() as conn:

        for stmt in DDL_STATEMENTS:
            conn.execute(text(stmt))

    print("geo.admin_unit and geo.name_alias ready.")
    print("=" * 60)


if __name__ == "__main__":

    main()
