"""
scripts/database/create_geo_views.py

Phase 1 / Task 11 (ADR-0001) -- DDL only. Creates one read-only view,
`geo.resolved_observation_counts`, that connects Task 10's canonical
geography (`geo.admin_unit`, `geo.name_alias`) back to the real
observation tables it was resolved from -- turning "this raw string
resolves to Punjab" (one row per distinct string, in `geo.name_alias`)
into "312 casualty reports resolved to Punjab" (one row per canonical
admin unit per domain, counted from the real, live observation rows).

This is the first real consumer of Task 10's geographic foundation:
it answers "how much of our actual data do we have real geography
for, broken out by canonical province/district" -- a question nothing
in the codebase could answer before, since `geo.name_alias` alone only
counts distinct raw strings, not observation volume.

Only observations with `geo.name_alias.status = 'resolved'` are
counted -- ambiguous/unresolved observations are correctly excluded,
never guessed into a bucket, per CLAUDE.md rule 7.

Zero existing table's schema or data changes. A VIEW has no storage
of its own -- nothing is duplicated, nothing can drift from source.
Fully reversible: `DROP VIEW geo.resolved_observation_counts` removes
100% of this task's database footprint with no effect on any other
object (the view reads from existing tables; nothing references into
it).

Per CLAUDE.md rule 2, this must NOT be run against the live database
without a fresh, restore-verified pg_dump taken first (done for this
task -- see pori-backups/2026-09-15_task11-pre-geo-views/). One-off,
hand-run script (not wired into any DAG), same pattern as Task 5's
create_dq_tables.py and Task 10's create_geo_schema_tables.py.

Run manually:
    python scripts/database/create_geo_views.py
"""

from sqlalchemy import text

from config.database import engine


# Eight UNION ALL branches, one per (source, domain) pair already
# populated by scripts/geo/resolve_observations.py (Task 10) -- exact
# same eight combinations, same raw-column mapping, nothing new
# invented here.
CREATE_VIEW_SQL = """
CREATE OR REPLACE VIEW geo.resolved_observation_counts AS

SELECT au.id AS admin_unit_id, au.level, au.name AS admin_unit_name,
       'ndma' AS source, 'casualties' AS domain, count(*) AS observation_count
FROM ndma_casualties o
JOIN geo.name_alias na ON na.raw_name = o.province AND na.source = 'ndma'
    AND na.domain = 'casualties' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
GROUP BY au.id, au.level, au.name

UNION ALL
SELECT au.id, au.level, au.name, 'ndma', 'damage', count(*)
FROM ndma_damage o
JOIN geo.name_alias na ON na.raw_name = o.province AND na.source = 'ndma'
    AND na.domain = 'damage' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
GROUP BY au.id, au.level, au.name

UNION ALL
SELECT au.id, au.level, au.name, 'ndma', 'rescue', count(*)
FROM ndma_rescue o
JOIN geo.name_alias na ON na.raw_name = o.province AND na.source = 'ndma'
    AND na.domain = 'rescue' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
GROUP BY au.id, au.level, au.name

UNION ALL
SELECT au.id, au.level, au.name, 'pdma', 'gauge_station', count(*)
FROM pdma_gauge_readings o
JOIN geo.name_alias na ON na.raw_name = o.station AND na.source = 'pdma'
    AND na.domain = 'gauge_station' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
GROUP BY au.id, au.level, au.name

UNION ALL
SELECT au.id, au.level, au.name, 'pdma', 'rainfall_station', count(*)
FROM pdma_rainfall_readings o
JOIN geo.name_alias na ON na.raw_name = o.station AND na.source = 'pdma'
    AND na.domain = 'rainfall_station' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
GROUP BY au.id, au.level, au.name

UNION ALL
SELECT au.id, au.level, au.name, 'pmd', 'pmd_city', count(*)
FROM pmd_daily_forecast o
JOIN geo.name_alias na ON na.raw_name = o.city AND na.source = 'pmd'
    AND na.domain = 'pmd_city' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
GROUP BY au.id, au.level, au.name

UNION ALL
SELECT au.id, au.level, au.name, 'pmd', 'pmd_weekly_region', count(*)
FROM pmd_weekly_outlook o
CROSS JOIN LATERAL jsonb_array_elements_text(o.regions) AS region
JOIN geo.name_alias na ON na.raw_name = region AND na.source = 'pmd'
    AND na.domain = 'pmd_weekly_region' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
WHERE o.regions IS NOT NULL
GROUP BY au.id, au.level, au.name

UNION ALL
SELECT au.id, au.level, au.name, 'pmd', 'pmd_alert_region', count(*)
FROM pmd_weather_alerts o
CROSS JOIN LATERAL jsonb_array_elements_text(o.regions) AS region
JOIN geo.name_alias na ON na.raw_name = region AND na.source = 'pmd'
    AND na.domain = 'pmd_alert_region' AND na.status = 'resolved'
JOIN geo.admin_unit au ON au.id = na.admin_unit_id
WHERE o.regions IS NOT NULL
GROUP BY au.id, au.level, au.name;
"""


def main():
    print("=" * 60)
    print("CREATE GEO VIEWS")
    print("=" * 60)

    with engine.begin() as conn:
        conn.execute(text(CREATE_VIEW_SQL))

    print("geo.resolved_observation_counts ready.")
    print("=" * 60)


if __name__ == "__main__":
    main()
