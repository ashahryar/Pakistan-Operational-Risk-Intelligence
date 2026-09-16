# Silver layer schema contracts

**Status: documented contract, no table implemented.**

## Design rules every silver table must follow

1. **Geography is resolved, never free text.** Every silver table with
   a location carries `admin_unit_id` (a foreign key into the existing
   `geo.admin_unit` table — reused, not reimplemented) instead of a
   raw city/district/province string. Rows whose raw geography string
   could not be resolved (`geo.name_alias.status != 'resolved'`) are
   excluded from silver and remain queryable only in bronze — this
   mirrors CLAUDE.md rule 7 (never fabricate a value) applied to
   geography specifically.
2. **Timestamps are UTC, with a parallel PKT column.** `observed_at`
   (UTC, `TIMESTAMPTZ`-equivalent) plus `observed_at_local` (PKT,
   naive) — the same pattern already used by the project's Postgres
   schema design discussions (`docs/architecture/CODEBASE_AUDIT.md`
   flags naive-timestamp handling as a known gap; silver is where that
   gets fixed for the lakehouse path specifically).
3. **Units are normalized once.** Temperature in Celsius, rainfall in
   millimeters, discharge in cusecs — matching what the existing
   Postgres columns already use, so a future silver-to-Postgres sync
   needs no unit conversion.
4. **No fabricated values.** A missing measurement is `NULL`, never a
   default, an interpolation, or `0`. An estimated/interpolated value
   (if ever introduced) carries an explicit `quality_flag = 'estimated'`
   column, never silently blended with directly-observed values.

## Example: `silver_gauge_observations`

| Column | Type | Notes |
|---|---|---|
| `station_id` | string | station name, unresolved-name policy TBD (no station registry exists yet — see `docs/architecture/CODEBASE_AUDIT.md`'s geography findings) |
| `admin_unit_id` | long | FK into `geo.admin_unit`, nullable if unresolved |
| `river` | string | |
| `observed_at` | timestamp (UTC) | |
| `observed_at_local` | timestamp (naive, PKT) | |
| `level_ft` | double | nullable |
| `danger_level_ft` | double | nullable |
| `discharge_cusecs` | double | nullable |
| `quality_flag` | string | `'valid'` \| `'estimated'` \| `'suspect'` |
| `_source_bronze_table` | string | lineage back to the bronze table this row was built from |

The remaining planned silver tables (`silver_weather_observations`,
`silver_rainfall_observations`, `silver_air_quality_observations`,
`silver_hazard_events`) follow the same four design rules above; their
column-level contracts will be documented here as each is actually
implemented, not speculatively in advance.
