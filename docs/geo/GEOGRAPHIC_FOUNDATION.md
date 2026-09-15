# Task 10 — Geographic Foundation

**Status:** Code implemented and unit-tested 2026-09-11 (Phase 1 / Task 10, ADR-0001). The database step (schema creation + seeding + observation resolution) is **not yet run** — it requires a fresh, restore-verified backup per `CLAUDE.md` rule 2, and is pending separate explicit approval before execution, matching the precedent set by Task 5's `dq.quarantine` creation.

## What this is

A minimal, honest canonical geographic hierarchy (province → district) plus a source-specific name-resolution mechanism (`geo.name_alias`), replacing the ad-hoc job six independent, disagreeing hardcoded city/province/district maps were doing across the codebase — without inventing precision the project doesn't actually have.

## Why not an authoritative boundary dataset (HDX/GADM)

Confirmed by a repo-wide search during planning: **no HDX/OCHA COD-AB, GADM, or P-code file exists anywhere in this repository.** Per explicit instruction, Task 10 does not download one. Instead it reconciles the two datasets that were *already present* and locally authored:

1. `scripts/database/create_geo_tables.py`'s `LOCATIONS` seed list (41 Punjab-block district rows — 2 of which are actually tagged AJK within that same block — plus 5 rivers, 39 PMD cities, 9 province rows).
2. `data/master/district_master.csv` (38 districts, national coverage, lat/lon) — previously **unreferenced by any code in the repository** (a genuinely orphaned dataset, found during Task 10 exploration).

Stable IDs are this repo's own surrogate integer keys (`geo.admin_unit.id`) — no real P-codes exist locally to preserve, so `pcode` is left `NULL` everywhere in this MVP. Adopting real P-codes via a future HDX/GADM download is named as explicit future work, not attempted here.

## The canonical hierarchy

Two real levels below country: **province/region (level 1)** and **district (level 2)**. No tehsil/taluka data exists anywhere in the repo, and none is added — level 3+ is simply not populated, honestly, rather than faked.

- **7 canonical provinces**: Punjab, Sindh, Khyber Pakhtunkhwa, Balochistan, Gilgit-Baltistan, Azad Jammu & Kashmir, Islamabad Capital Territory — each seeded with every real abbreviation/spelling variant actually observed live in this project's own data (e.g. `AJ&K` from NDMA, `AJK` from PMD, `ICT` vs `Islamabad`).
- **69 canonical districts** — the deduplicated union of the two source lists above (11 names overlap between them, e.g. `Lahore`, `Faisalabad`, `Dera Ghazi Khan`/`D.G. Khan`). Exact breakdown: Punjab 40, Sindh 10, Khyber Pakhtunkhwa 8, Balochistan 5, Azad Jammu & Kashmir 3, Gilgit-Baltistan 2, Islamabad Capital Territory 1.

City-level names (PMD's 54 forecast cities) are resolved as references to their *district* — via the existing, already-in-production `scripts/parsing/pmd/utils.py::CITY_PROVINCE` mapping where it applies, falling back to a direct district-name match otherwise — not modeled as a separate hierarchy level, since no city-boundary data exists.

### Known caveat, inherited and documented, not corrected

Four entries in `geo_locations`'s own existing seed data are not actually districts — pre-existing inaccuracies in the repo's own data, not introduced by Task 10:

| Entry | What it actually is |
|---|---|
| `Mangla` | A reservoir/dam town in Mirpur (AJK) district |
| `Fort Munro` | A hill station within Dera Ghazi Khan district |
| `Kamra` | An air-base town within Attock district |
| `Joharabad` | A town within Khushab district |

Each is carried through as-is (tagged `source='geo_locations'`, with an explicit `caveat` field in `scripts/geo/canonical_data.py`) rather than "corrected" by original administrative research — which would mean fabricating authoritative knowledge this task is explicitly told not to invent.

## Resolution mechanism

`scripts/geo/resolver.py::resolve(raw_name, candidates)` — pure function, no DB, no I/O. Resolution order (first match wins): **exact → alias → normalized (case/whitespace/punctuation) → fuzzy (stdlib `difflib`, ≥0.85 ratio, no library added — none is installed anywhere in this repo, confirmed during planning) → structural ambiguity (comma/slash-separated strings, never split or guessed) → unresolved**.

Every resolution is recorded in `geo.name_alias` with: `raw_name`, `normalized_name`, `source`, `domain`, `admin_unit_id` (nullable), `match_method`, `confidence` (fuzzy only), `status` (`resolved`/`ambiguous`/`unresolved`), and `notes` — full provenance, nothing silently dropped.

**Never assigns a lower level than the source supports**, structurally, not just by convention: `resolve()` only ever sees the single candidate pool it's given for that domain (provinces-only or districts-only) — there is no code path that widens the pool. Tested directly (`tests/geo/test_resolver.py::test_province_name_does_not_resolve_against_district_pool` and its mirror).

## Two data-quality issues found during Task 10 profiling — flagged, not fixed

- **`ndma_relief.province`** actually holds relief-item names ("Tents", "Ration Bags"), not provinces — a pre-existing loader/parser column-mapping bug, unrelated to geographic modeling. `ndma_relief` is excluded from Task 10's resolution scope entirely.
- **`pdma_gauge_readings.river`** is not resolved against the province/district hierarchy at all — a river is not an administrative unit, and forcing it into one would misrepresent what it is. Out of scope for this MVP.

## Expected, honest outcome for gauge stations

`pdma_gauge_readings.station` (42 real station names like `Tarbela`, `Chashma`, `Marala`) will mostly resolve as **`unresolved`** — no station→district mapping exists anywhere in this repository. This is the correct, non-fabricated outcome, not a resolver defect, and is stated here so it isn't mistaken for one later.

## Database footprint

One new schema, `geo`, two tables (`geo.admin_unit`, `geo.name_alias`) — see `scripts/database/create_geo_schema_tables.py` for exact DDL. Zero changes to any existing table's schema or data. Fully reversible: `DROP SCHEMA geo CASCADE` removes 100% of this task's database footprint with no effect on any other table.

## Files

```
scripts/database/create_geo_schema_tables.py   # DDL only, hand-run
scripts/geo/canonical_data.py                  # pure data: 7 provinces, 69 districts
scripts/geo/resolver.py                        # pure resolution logic
scripts/geo/seed_admin_units.py                # idempotent seed script
scripts/geo/resolve_observations.py            # idempotent resolution script
tests/geo/test_canonical_data.py               # static structural tests
tests/geo/test_resolver.py                     # resolver logic tests (34 tests total)
docs/geo/GEOGRAPHIC_FOUNDATION.md              # this file
```

No existing file is modified. `dashboard/db.py`'s existing `geo_locations` join is untouched and keeps working exactly as before — `geo_locations` itself is not migrated, deprecated, or dropped; it stays as the dashboard's data source, with `geo.admin_unit`/`geo.name_alias` positioned as the new canonical layer for anything going forward. The six existing hardcoded maps (`pmd_parser.URDU_CITY_MAP`, `pmd/utils.CITY_PROVINCE`/`CITY_DISTRICT`, `translator.CITY_TRANSLATIONS`/`CITY_INFO`, `mappings.CITY_MAPPING`, `alerts_parser.REGIONS`) are read (as an alias-seeding *source* and, for PMD cities, reused directly) but not edited, deleted, or rewired — consolidating live parsers onto the new resolver is explicitly deferred future work, not attempted here (touching live, Task-8-tested parsing code paths under time pressure is a real risk this task avoids).

## Tests

34 deterministic tests (`tests/geo/`), no live DB, no internet: exact match, alias match (real NDMA/PMD abbreviations), case/spacing normalization, known spelling variation (real, live-confirmed misspellings — `"Mandi Bahaddin"`/`"Mandi Bahauddin"`, `"Noorpurthal"`/`"Noorpur Thal"` — forced through the genuine fuzzy path, not alias-shortcut), ambiguous multi-value strings (real `pdma_rainfall_readings.station` shape), unresolved (a real gauge-station name, a nonsense string, empty/`None`), parent-child validation (every district's declared province exists), and level-boundary prevention (a province name never resolves against the district pool or vice versa, both empirically and via a signature-inspection structural test).

Fault-injection proof run during implementation: temporarily set `FUZZY_THRESHOLD = 0.0`, confirmed 4 tests went meaningfully red (nonsense/wrong-level strings started "resolving"), reverted, confirmed 34/34 green again.

## Live resolution results

**Pending** — `scripts/geo/resolve_observations.py` has not yet been run against the live database (awaiting the backup + separate-approval gate described above). This section will be updated with real resolved/ambiguous/unresolved counts per `(source, domain)` once it runs — no number is estimated or promised here in advance.

## Explicit confirmation

No AWS work. No PostGIS (justified: this MVP is a name-matching hierarchy, not spatial containment — no polygon data exists locally to justify it). No new Airflow DAG (the two scripts are standalone, hand-run, exactly like Task 9's forecasting script). No dashboard changes. No Task 9 forecasting files touched. No unrelated refactoring of the six existing hardcoded maps.
