# Data Quality Baseline

| | |
|---|---|
| **Status** | Frozen baseline of record (Phase 0) |
| **Measured on** | 2026-09-01 |
| **Branch** | `project-redesign-baseline` @ `d452c3b` |
| **Source of measurement** | Read-only `SELECT` queries against the running `airflow_postgres` container; aggregation of 4,771 Airflow task log files; filesystem counts under `data/` |
| **Related** | [`assessment/ARCHITECTURE_ASSESSMENT.md`](assessment/ARCHITECTURE_ASSESSMENT.md) · [`decisions/ADR-0001-baseline-and-recovery.md`](decisions/ADR-0001-baseline-and-recovery.md) |

## Purpose

This document freezes the measured state of the platform **before** any Phase 1 change. Its only job is to make improvement provable. Every Phase 1 exit criterion is expressed as a delta against a number on this page.

**These numbers must not be edited.** When Phase 1 completes, re-run the queries in the appendix and record the results in a new `DATA_QUALITY_PHASE1.md`, side by side with these. A baseline that gets quietly updated is not a baseline.

**Nothing here is estimated or inferred.** Every figure is a query result, a log count, or a file count. Where a number is derived (a percentage), the numerator and denominator are both shown.

---

## 1. Pipeline execution — DAG run failures

All seven DAGs are unpaused and scheduled. **38 of 39 DAG runs have failed. There has been exactly one success in the platform's history.**

```
dag_id                 state     count   last_run
──────────────────────────────────────────────────
backfill_pipeline      failed        1   2026-08-31
disaster_pipeline      failed        5   2026-09-01
manual_pipeline        failed        2   2026-08-31
ndma_pipeline          failed       17   2026-09-01
pdma_pipeline          failed        7   2026-09-01
pmd_pipeline           failed        5   2026-09-01
pmd_pipeline          success        1   2026-09-01
weekly_full_pipeline   failed        1   2026-08-31
──────────────────────────────────────────────────
TOTAL FAILED                        38
TOTAL SUCCESS                        1
SUCCESS RATE                      2.6%
```

| Metric | Baseline |
|---|---:|
| Total DAG runs recorded | 39 |
| Failed | **38** |
| Succeeded | **1** |
| Success rate | **2.6%** |
| DAGs with zero successful runs | **6 of 7** |
| DAG-level import errors currently registered | 0 |

> `import_error` is empty, so these are **runtime** failures, not parse failures. The DAGs load correctly and then fail when executed.

---

## 2. NDMA parse failures

`extract_ndma` succeeds every time. `parse_ndma` fails every time. Everything downstream is `upstream_failed`.

| Task | State | Count |
|---|---|---:|
| `extract_ndma` | success | **17 / 17** |
| `parse_ndma` | **failed** | **17 / 17** |
| `build_ndma_dataset` | upstream_failed | 17 |
| `load_postgres` | upstream_failed | 17 |
| `upload_raw_s3` | upstream_failed | 17 |

**Root cause (from live log, `run_id=manual__2026-09-01T12:42:10`, attempt 4):**

```
File "/opt/project/scripts/parsing/parse_ndma.py", line 107, in parse_pdf
    copy2(
File "/usr/local/lib/python3.11/shutil.py", line 449, in copy2
    copystat(src, dst, follow_symlinks=follow_symlinks)
File "/usr/local/lib/python3.11/shutil.py", line 380, in copystat
    lookup("utime")(dst, ns=(st.st_atime_ns, st.st_mtime_ns),
PermissionError: [Errno 1] Operation not permitted
```

`shutil.copy2()` calls `copystat` → `utime()`, which the Windows bind mount denies to uid 50000. The first PDF processed is a rejected one, so **the run dies on file 1 of 70** — on every attempt, for five weeks.

**Secondary finding from the same log:** the PDF table extractor finds almost nothing.

```
========== PAGE 1 ==========   Tables Found: 1     (a contents/annexure listing)
========== PAGE 2 ==========   Tables Found: 0
========== PAGE 3 ==========   Tables Found: 0
  … pages 4–11 …               Tables Found: 0
NDMA VALIDATION FAILED
- Empty table : casualties
- Empty table : damage
- Empty table : relief
- Empty table : rescue
```

`scripts/parsing/common/pdf_table_reader.py` uses `pdfplumber`'s default line-based strategy only. No `camelot`, no text-alignment fallback, no `table_settings` tuning. NDMA sitreps are largely borderless.

---

## 3. NDMA parsing rejection rate

`validation/ndma/schema.py` rejects a report if **any one** of casualties / damage / relief / rescue is empty. A sitrep with perfect casualty data is discarded whole because its relief table was invisible to the extractor.

| Metric | Baseline |
|---|---:|
| Raw NDMA sitrep PDFs on disk | **70** |
| Parsed sitrep JSON files produced | **33** |
| **Rejection rate** | **52.9% (37 of 70)** |
| PDFs present in `data/rejected/ndma/` | **2** |
| **Rejected reports with no audit trail** | **35** |

> The quarantine folder holds 2 files where 37 were rejected. There is no queryable record of why the other 35 were discarded, or that they were discarded at all.

### NDMA raw corpus, by category

| Category | PDFs on disk | Parser exists | Parsed output |
|---|---:|---|---:|
| `sitreps` | 70 | yes | 33 |
| `advisories` | 220 | **no** | 0 |
| `guidelines` | 23 | **no** | 0 |
| **Total** | **313** | | **33 (10.5%)** |

Plus 1 `.jpeg` and 1 `.png` downloaded into `pdfs/` folders, which `glob("*.pdf")` skips permanently.

---

## 4. PDMA extraction failures

`extract_pdma` fails before a single PDF is downloaded.

| Task | State | Count |
|---|---|---:|
| `extract_pdma` | **failed** | **7 / 7** |
| `parse_pdma` | upstream_failed | 7 |
| `load_postgres` | upstream_failed | 7 |
| `upload_raw_s3` | upstream_failed | 7 |
| `upload_parsed_s3` | upstream_failed | 7 |

**Root cause (live log, `run_id=scheduled__2026-09-01T06:00:00`, attempt 4):**

```
URL: https://pdma.punjab.gov.pk/daily-situation-reports-2026?page=0
STATUS: 200
FINAL URL: https://pdma.punjab.gov.pk/daily-situation-reports-2026?page=0

File "/opt/project/scripts/extraction/extract_pdma.py", line 91, in scrape_report_year
    with open("debug_pdma.html", "w", encoding="utf-8") as f:
PermissionError: [Errno 13] Permission denied: 'debug_pdma.html'
```

**The source returned HTTP 200.** A leftover debug-file write into the project root kills the crawl on page 1 of the first report type.

### PDMA parse yield (from the last successful extraction, before the crash)

| Report type | Year | Raw PDFs | Parsed JSON | Lost | Loss rate |
|---|---|---:|---:|---:|---:|
| daily | 2025 | 7 | 7 | 0 | 0% |
| daily | 2026 | 73 | 73 | 0 | 0% |
| rainfall | 2025 | 54 | 52 | 2 | 3.7% |
| **rainfall** | **2026** | **88** | **27** | **61** | **69.3%** |
| gauge | 2025 | 69 | 69 | 0 | 0% |
| gauge | 2026 | 175 | 174 | 1 | 0.6% |
| earthquake | 2026 | 3 | **0** | 3 | **100%** (no parser wired) |
| **Total** | | **469** | **402** | **67** | **14.3%** |

> **61 rainfall reports for 2026 were silently dropped and the Airflow task still reported SUCCESS.** `parse_pdma.py:170-176` catches each per-file exception, prints, and continues; the script exits 0 regardless. This is the single clearest example of silent data loss in the platform.

Plus 60 `.jpeg`, 1 `.jpg` and 6 `.png` files downloaded into `pdfs/` folders and permanently skipped.

---

## 5. PMD load failures

| Task | State | Count |
|---|---|---:|
| `extract_pmd` | success | 6 |
| `validate_pmd` | success | 6 |
| `load_postgres` | **failed** | **5** |
| `load_postgres` | success | **1** |
| `upload_raw_s3` | upstream_failed | 5 |
| `upload_raw_s3` | success | 1 |

Extraction and parsing work. The load fails 5 times out of 6, which is why `pmd_daily_forecast` contains exactly one snapshot.

**Compounding defect — PMD has no historical archive at any layer.** Both the raw extractor (`extract_pmd.py:83`) and the parser (`pmd/pipeline.py`) write to a fixed `latest.json` and overwrite it on every run.

| Layer | Files retained per category | History |
|---|---:|---|
| `data/raw/pmd/reports/*/all/` | **1** (`latest.json`) | None |
| `data/parsed/pmd/*/` | **1** (`latest.json`) | None |

Every PMD observation that failed to load is permanently unrecoverable. **This loss is ongoing and irreversible while the overwrite persists.**

---

## 6. River gauge NULL rates

`pdma_gauge_readings` is the largest table in the platform and roughly half of its measurements are missing.

| Metric | Count | Share of table |
|---|---:|---:|
| Total rows | **9,517** | 100% |
| NULL `report_datetime` | **2,691** | **28.3%** |
| NULL `current_level_ft` | **4,393** | **46.2%** |
| NULL `danger_level_ft` | **4,858** | **51.0%** |
| NULL `river` | 0 | 0% |
| Distinct stations | 42 | — |
| Distinct `river` values | 12 | — |

**Operational consequence:** the dashboard's Danger / Watch / Normal classification (`current_level_ft` vs `danger_level_ft`) is computable for **less than half the network**. The remainder silently falls through to `"Unknown"` and is then `dropna`'d out of the charts, so the UI presents a partial picture as if it were complete.

**Root cause:** `scripts/parsing/parse_gauge.py` requires `len(row) >= 12` and reads hardcoded column positions `row[3]`, `row[6]`, `row[9]`, `row[11]`. When `pdfplumber` merges or splits a cell — routine on these layouts — rows are either dropped without a counter or shifted, writing wrong numbers into the right columns.

---

## 7. River dimension corruption

The `river` column has zero NULLs, which conceals the real problem: it contains PDF artefacts as first-class entities.

```
river                            rows   distinct_stations
────────────────────────────────────────────────────────
RAJANPUR HILL TORRENTS           1864          8
DG KHAN HILL TORRENTS            1617          7
NULLAHS                          1492          7
CHENAB                           1215          5
RAVI                              972          4
INDUS                             972          4
SUTLEJ                            729          4
JHELUM                            486          2
RAJANPU R HILL TORRENT S           80          8   ← letter-spacing artefact
DG KHAN HILL TORRENT S             70          7   ← letter-spacing artefact
1230DG KHAN 1230HILL TORRENTS      14          7   ← report time "1230" bled into the name
NULLAHS DATA SOURCE: F              6          6   ← PDF footer text ingested as a river
```

| Metric | Baseline |
|---|---:|
| Distinct `river` values stored | **12** |
| Genuine hydrological entities | **~8** |
| **Corrupted / duplicate variants** | **4 (33% of the dimension)** |
| Rows attached to a corrupted river value | **170** |

**Station-level corruption in the same table:**

| Observed value | Problem |
|---|---|
| `SITE` | A table header row that became a station |
| `G.S. Wala` / `G.S.Wala` | One physical gauge, two identities |
| `Lai` / `Lai FD and DEO` | One physical gauge, two identities |

There is no station or river reference table, so nothing can reject these.

---

## 8. Rainfall junk-station rate

| Metric | Baseline |
|---|---:|
| Total rows | **869** |
| Distinct `station` values | **161** |
| Districts in Punjab (the actual coverage area) | **36** |
| **Excess / unverified station identities** | **~125 (78%)** |
| NULL `report_date` | 0 |

**The most frequent "station" in the table is the literal word `Stations`.**

```
station            rows
───────────────────────
Stations             74   ← the table header, ingested as a station
Rawalpindi           47
Murree               43
Lahore               38
Sialkot              35
Narowal              33
Gujranwala           29
Chakwal              27
Faisalabad           26
Mangla               26
…
```

| Metric | Baseline |
|---|---:|
| Rows attributed to the header word `Stations` | **74 (8.5% of the table)** |
| Readings for the top genuine station (Rawalpindi) | 47 |
| Parsed rainfall files that should have contributed | 79 |
| **Coverage for the best-covered real station** | **59% (47 of 79)** |

**Root cause:** `scripts/parsing/parse_rainfall.py` takes `row[0]` as the station name and `parse_numeric(row[1])` as millimetres, with no header detection, no station allow-list, and no reference data. Trace values (`"T"`) and negatives coerce to `None` and are dropped without a counter.

---

## 9. PDMA daily report NULL dates

| Metric | Count | Share |
|---|---:|---:|
| Total rows | **80** | 100% |
| **NULL `report_date`** | **74** | **92.5%** |
| Rows with any date at all | 6 | 7.5% |

**Consequence:** `MIN(report_date)` = 2025-06-02 and `MAX(report_date)` = 2025-11-01, **despite 73 parsed daily reports existing for 2026**. The table's apparent date range is an artefact of the six rows that happen to have a date. Any time-series query over `pdma_daily_reports` is meaningless at this baseline.

**Root cause:** `parse_pdma_daily.extract_date()` regexes the entire document text against three narrow patterns and returns the first match, uppercased, as a string (`"12TH JULY 2026"`). Anything not matching yields `None`. Nothing downstream validates that a date was found.

**Related latent defect (not yet visible in this table because so few rows have dates):** raw date strings are passed to `DATE` columns. Under Postgres `DateStyle = MDY`, `"12.07.2026"` parses as **7 December**, not 12 July. Values with day > 12 raise instead — and because each loader wraps its whole loop in a single `engine.begin()`, that one error aborts every remaining insert.

---

## 10. Missing `pipeline_logs` table

| Check | Result |
|---|---|
| `pipeline_logs` present in `\dt` | **NO — the table does not exist** |
| Written by | `pipeline/utils/pipeline_logger.py` (`INSERT INTO pipeline_logs …`) |
| Read by | `dashboard/db.py::get_dashboard_summary()` (`SELECT MAX(finished_at) … WHERE status='success'`) |
| Created by | **nothing** — no DDL script, no migration, no DAG |

**Consequences:**

1. Every `log_pipeline()` call fails.
2. The dashboard's **"Last Update" indicator is permanently blank** — and because `_read_sql` catches every exception and returns an empty DataFrame, no error is ever surfaced.
3. There is **no record anywhere of pipeline run history, rows processed, or rows rejected.**

### Related empty or missing observability components

| Component | State |
|---|---|
| `pipeline/utils/metadata_logger.py` | **Empty file (0 lines)** |
| `pipeline/utils/duplicate_checker.py` | **Empty file (0 lines)** |
| `scripts/warehouse/load_dimensions.py` | **Empty file (0 lines)** |
| `scripts/warehouse/load_facts.py` | **Empty file (0 lines)** |
| `scripts/warehouse/warehouse_models.py` | **Empty file (0 lines)** |
| `pipeline/utils/data_quality.py` | Implemented, **called by no DAG** |
| `pipeline/utils/sns_alert.py` | Implemented, **wired to nothing** |
| `pipeline/sensors/*.py` (3 files) | Implemented, **imported by no DAG** |

### Dashboard queries against non-existent tables

| Query in `dashboard/db.py` | Target | Exists in Postgres? | Failure mode |
|---|---|---|---|
| `get_latest_weather()` | `pmd_weather` | **No** (it is a *Redshift* table name) | Silent empty DataFrame |
| `get_weather_summary()` | `pmd_weather` | **No** | Silent empty DataFrame |
| `get_dashboard_summary()` | `pipeline_logs` | **No** | "Last Update" blank |

---

## 11. `operational_risk` row count

| Metric | Baseline |
|---|---:|
| `operational_risk` rows | **0** |
| Table exists | Yes (`scripts/database/create_risk_tables.py`) |
| Written by | `scripts/risk_engine/risk_engine.py` (301 lines) |
| Invoked by | **No DAG** |

**The risk engine — the component that gives the platform its name — has never produced a single row.**

---

## 12. Data freshness

Measured against **2026-09-01**.

| Table | Rows | Newest record | Age |
|---|---:|---|---:|
| `ndma_casualties` | 224 | 2026-07-28 | **35 days** |
| `ndma_damage` | 132 | 2026-07-28 | **35 days** |
| `ndma_relief` | 1,686 | 2026-07-28 | **35 days** |
| `ndma_rescue` | 89 | 2026-07-28 | **35 days** |
| `pdma_gauge_readings` | 9,517 | 2026-07-31 12:00 | **32 days** |
| `pdma_rainfall_readings` | 869 | 2026-07-14 | **49 days** |
| `pdma_daily_reports` | 80 | 2025-11-01 * | **304 days** * |
| `pmd_daily_forecast` | 108 | 2026-08-12 00:00:16 | **20 days** |
| `pmd_weekly_outlook` | 7 | 2026-08-12 00:00:16 | **20 days** |
| `pmd_weather_alerts` | 1 | 2026-08-13 20:00:20 | **19 days** |
| `geo_locations` | 95 | — (static seed) | — |
| `operational_risk` | **0** | — | — |

\* `pdma_daily_reports` freshness is not meaningful — 92.5% of rows have no date (see §9).

| Domain | Freshness SLA implied by DAG schedule | Actual | Breach factor |
|---|---|---:|---:|
| NDMA | daily (`0 5 * * *`) | 35 days | **35×** |
| PDMA | 6-hourly (`0 */6 * * *`) | 32 days | **128×** |
| PMD | 6-hourly (`0 */6 * * *`) | 20 days | **80×** |

**Meanwhile the dashboard displays a pulsing "Live Monitoring Active" badge and auto-refreshes every 60 seconds.** Nothing in the UI indicates the data is five weeks old.

---

## 13. Additional measured NULL and correctness rates

| Table | Column | NULL count | Share | Cause |
|---|---|---:|---:|---|
| `ndma_damage` | `roads_km` | **74 / 132** | **56.1%** | `"-"` sentinel → `None`; `to_int()` also fails on comma-separated numbers |
| `ndma_casualties` | `injured` | **34 / 224** | **15.2%** | Hardcoded `value(row, 8)` runs off the end of shorter rows |
| `ndma_damage` | `houses_total` | 0 / 132 | 0% | Loader path correct — see divergence below |
| `pmd_daily_forecast` | `province = 'Unknown'` | **30 / 108** | **27.8%** | City absent from `CITY_PROVINCE` map |
| `pmd_daily_forecast` | `district` | **30 / 108** | **27.8%** | Same |

### Divergent NDMA pipelines — one works, one does not

Two independent paths consume the same parsed NDMA JSON and disagree.

| Path | Destination | Relief rows | `houses_total` |
|---|---|---:|---|
| `load_ndma.py` → PostgreSQL | `ndma_relief`, `ndma_damage` | **1,686** | populated |
| `build_ndma_dataset.py` → `data/analytics/` → S3 → Glue | `relief.json`, `damage.json` | **0** | **null in every row** |

- **Relief:** `build_ndma_dataset.py` treats relief rows as lists (`row[0]`, `row[i+1]`, `len(row)`), but the parser emits dicts. `len(dict) == 3 < len(provinces)+1 == 8`, so **every row is dropped by the guard**. `data/analytics/ndma/relief.json` contains 0 records.
- **Damage:** it reads `row.get("houses_total")`; the parser emits `houses_damaged`. Every `houses_total` in `damage.json` is `null`.
- Sample record from `damage.json` showing both defects plus the unconverted sentinel:
  ```json
  {"report_number":"02","report_date":"27 June 2026","province":"GB",
   "roads_km":"-","bridges":"-","houses_total":null,"livestock":"0"}
  ```

**Anything consuming the S3 / Glue path receives corrupted data. Anything consuming PostgreSQL does not.**

### Province label inconsistency

Values actually present in the database versus values in the code's mapping tables:

| In `ndma_*` tables | In `validation/` + `pmd/utils` mappings |
|---|---|
| `AJ&K` | `AJK` |
| `GB` | `Gilgit Baltistan` |
| `KP` | `Khyber Pakhtunkhwa` |
| `ICT` | `Islamabad Capital Territory` |
| `Punjab`, `Sindh`, `Balochistan` | (match) |

Five separate, mutually inconsistent city→province mappings exist in the codebase. There is no canonical province dimension and no P-codes.

---

## 14. Airflow log error signatures

Aggregated across **4,771** task log files.

| Count | Error signature | Meaning |
|---:|---|---|
| **4,271** | `TypeError: not all arguments converted during string formatting` | `extract_ndma.py:77` passes 3 args for 2 placeholders — fires on every page of every crawl |
| **2,016** | `psycopg2.errors.InFailedSqlTransaction` | One bad row aborts the whole `engine.begin()` block; every later insert in that load fails |
| **1,237** | `ModuleNotFoundError: No module named 'airflow.utils.task_callbacks'` | Local module path collided with the installed `airflow` package namespace |
| **804** | `ImportError: cannot import name 'DAG' from 'pipeline'` | Local package name shadowing a framework name |
| **801** | `ImportError: cannot import name 'check_for_new_files' from 'pipeline.sensors.ndma_sensor'` | Sensor API drift |
| 255 | `NameError: name 'upload_folder' is not defined` | Import commented out, call site left behind |
| 156 | `ImportError: cannot import name 'upload_all_to_s3'` | Function never existed |
| 102 | `ImportError: cannot import name 'task_failure_callback'` | Renamed without updating callers |
| 75 | `ImportError: cannot import name 'task_success'` | Same |
| 69 | `NameError: name 'timedelta' is not defined` | Import removed |
| **43** | `UndefinedTable: relation "ndma_casualties" does not exist` | **DDL is never run by any DAG** |
| 36 | `ModuleNotFoundError: No module named 'validation'` | `sys.path` hack fragility |
| 33 | `NameError: name 'upload_analytics' is not defined` | Import commented out |
| 31 | `NameError: name 'start_glue_job' is not defined` | Import commented out |
| 30 | `NameError: name 'Path' is not defined` | Import removed |
| 24 | `NameError: name 'verify_backfill' is not defined` | Function never existed |
| **20** | `UndefinedColumn: column "district" of relation "pmd_daily_forecast" does not exist` | **Schema drift between two competing DDL scripts** |
| 18 | `UndefinedTable: relation "pmd_daily_forecast" does not exist` | DDL not run |
| 17 | `TypeError: 'bool' object is not subscriptable` | Return-contract mismatch |
| 15 | `NameError: name 'verify_tables' is not defined` | Import commented out |
| 9 | `ImportError: cannot import name 'parse_pdf' from 'parse_pdma_daily'` | `sys.path` fragility |
| 7 each | `UndefinedTable`: `pdma_daily_reports`, `pdma_rainfall_readings`, `pdma_gauge_readings` | DDL not run |
| **6** | `UniqueViolation on ndma_casualties_report_number_report_date_province_key` | Duplicate loads |
| 4 | `ImportError: cannot import name 'calculate_completeness'` | API drift |
| 3 | `UndefinedColumn: column "category" of relation "pmd_weekly_outlook"` | Schema drift |
| 2 | `UndefinedColumn: column "category" of relation "pmd_weather_alerts"` | Schema drift |
| 2 | `psycopg2.OperationalError: connection …` | DB unreachable |

**Currently, on every single task instance:**

```
smtplib.SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted.')
```

`pipeline/utils/task_callbacks.py` sends an email on **every task success and every task failure**. The Gmail app password is dead. This fires on all ~40 task instances per pipeline cycle, adds latency to every task, and buries the real error under an SMTP stack trace — which is why the actual failure reasons above were not visible.

### Aggregate error classes

| Class | Total occurrences | Preventable by |
|---|---:|---|
| Logging format-string bug | 4,271 | One-line fix + a unit test |
| Transaction abort cascade | 2,016 | Per-record error isolation |
| Import / NameError (all variants) | **~3,400** | **A 15-line `DagBag` import test** |
| Missing table / column | **107** | Alembic + orchestrated DDL |
| Unique violation | 6 | `ON CONFLICT` |

---

## 15. Storage and schema inventory

### Application tables — **inside the Airflow metadata database**

`\dt` on database `airflow` returns **54 tables**: 42 Airflow internal tables and 12 application tables sharing the same `public` schema and the same superuser.

| Table | Rows | Date range |
|---|---:|---|
| `ndma_casualties` | 224 | 2026-06-27 → 2026-07-28 |
| `ndma_damage` | 132 | 2026-06-27 → 2026-07-28 |
| `ndma_relief` | 1,686 | 2026-06-27 → 2026-07-28 |
| `ndma_rescue` | 89 | 2026-06-27 → 2026-07-28 |
| `pdma_daily_reports` | 80 | 2025-06-02 → 2025-11-01 (92.5% NULL) |
| `pdma_rainfall_readings` | 869 | 2025-03-03 → 2026-07-14 |
| `pdma_gauge_readings` | 9,517 | 2026-06-15 → 2026-07-31 |
| `pmd_daily_forecast` | 108 | 2026-08-12 (single timestamp) |
| `pmd_weekly_outlook` | 7 | 2026-08-12 (single timestamp) |
| `pmd_weather_alerts` | 1 | 2026-08-13 |
| `geo_locations` | 95 | static seed |
| `operational_risk` | **0** | — |
| **TOTAL APPLICATION ROWS** | **12,808** | |

**Absent from the database entirely:** `pipeline_logs`, and every `dim_*` / `fact_*` table defined by the 1,648 lines in `scripts/warehouse/`.

> **12,808 rows representing months of collection sit in a database that `airflow db reset` would destroy.** This is the primary justification for the Phase 0 backup requirement.

### Raw corpus on disk

| Source | PDFs | Images | JSON | Total files |
|---|---:|---:|---:|---:|
| NDMA | 313 | 2 | 3 | 318 |
| PDMA | 420 | 67 | 10 | 497 |
| PMD | 0 | 0 | 3 | 3 |
| **Total** | **733** | **69** | **16** | **818** |

733 source PDFs, several from sites with shallow public archives. **Irreplaceable if lost.**

### Airflow logs

| Metric | Baseline |
|---|---:|
| Log files under `airflow/logs/` | **4,771** |
| Files containing `ERROR` / `Traceback` / `Exception` | **4,019 (84.2%)** |
| Orphaned DAG log directories | 1 (`dag_id=pakistan_disaster_pipeline`, DAG deleted from repo) |

Volume driven by debug prints left in production code: `pdf_table_reader.py` prints 10 rows of every table on every page; `parse_rainfall.py` prints 1,500 characters of every page of every PDF.

---

## 16. Baseline summary — the numbers Phase 1 must move

| # | Metric | Baseline | Phase 1 target |
|---|---|---:|---|
| 1 | DAG success rate | **2.6%** | 100% for 7 consecutive days (3 domain DAGs) |
| 2 | `parse_ndma` success | **0 / 17** | 17 / 17 |
| 3 | `extract_pdma` success | **0 / 7** | 7 / 7 |
| 4 | `load_postgres` (PMD) success | 1 / 6 | 6 / 6 |
| 5 | NDMA data age | **35 days** | < 48 hours |
| 6 | PDMA data age | **32 days** | < 12 hours |
| 7 | PMD data age | **20 days** | < 12 hours |
| 8 | `InFailedSqlTransaction` occurrences | **2,016** | 0 |
| 9 | Silently dropped records | **unbounded / uncounted** | 0 — every rejection in `dq.quarantine` with a reason |
| 10 | NDMA rejections with no audit trail | **35** | 0 |
| 11 | Gauge rows with NULL `report_datetime` | **28.3%** | measured and *counted*; reduction is Phase 2 work |
| 12 | Gauge rows with NULL `current_level_ft` | **46.2%** | measured and *counted*; reduction is Phase 2 work |
| 13 | Gauge rows with NULL `danger_level_ft` | **51.0%** | measured and *counted*; reduction is Phase 2 work |
| 14 | Corrupted river dimension values | **4 of 12 (33%)** | Phase 2 (requires reference data) |
| 15 | Rainfall rows attributed to header word `Stations` | **74 (8.5%)** | Phase 2 (requires station registry) |
| 16 | `pdma_daily_reports` NULL `report_date` | **92.5%** | < 5% |
| 17 | `pipeline_logs` exists | **No** | Yes, as `ops.pipeline_run`, populated on every run |
| 18 | `operational_risk` rows | **0** | Out of Phase 1 scope — do not chase |
| 19 | Application tables in the Airflow metadata DB | **12** | 0 — migrated to database `pori` |
| 20 | Automated tests | **0** | DAG integrity + parser golden files + type coercion, green in CI |
| 21 | Secrets printed to logs | **2 call sites** | 0 |

> **Honest scoping note.** Items 11–15 are *measurement* targets in Phase 1, not *reduction* targets. Cutting gauge NULL rates and cleaning the river/station dimensions requires the reference data and canonical geography built in Phase 2. What Phase 1 must deliver is that these rates are **counted, recorded per run, and cause a task to fail when they regress** — rather than being invisible as they are today.

---

## Appendix — reproduction queries

Read-only. Safe to run at any time. Re-run these at each phase boundary and record the results in a new dated file rather than editing this one.

**DAG run outcomes (§1)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT dag_id, state, count(*), max(start_date)::date AS last_run FROM dag_run GROUP BY 1,2 ORDER BY 1,2;"
```

**Task-level outcomes (§2, §4, §5)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT dag_id, task_id, state, count(*) FROM task_instance GROUP BY 1,2,3 ORDER BY 1,2,3;"
```

**Table row counts and freshness (§12, §15)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT 'ndma_casualties' t, count(*) rows, max(report_date)::text newest FROM ndma_casualties UNION ALL SELECT 'ndma_damage', count(*), max(report_date)::text FROM ndma_damage UNION ALL SELECT 'ndma_relief', count(*), max(report_date)::text FROM ndma_relief UNION ALL SELECT 'ndma_rescue', count(*), max(report_date)::text FROM ndma_rescue UNION ALL SELECT 'pdma_daily_reports', count(*), max(report_date)::text FROM pdma_daily_reports UNION ALL SELECT 'pdma_rainfall_readings', count(*), max(report_date)::text FROM pdma_rainfall_readings UNION ALL SELECT 'pdma_gauge_readings', count(*), max(report_datetime)::text FROM pdma_gauge_readings UNION ALL SELECT 'pmd_daily_forecast', count(*), max(scraped_at)::text FROM pmd_daily_forecast UNION ALL SELECT 'operational_risk', count(*), null FROM operational_risk;"
```

**Gauge NULL rates (§6)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT count(*) total, count(*) FILTER (WHERE report_datetime IS NULL) null_datetime, count(*) FILTER (WHERE current_level_ft IS NULL) null_level, count(*) FILTER (WHERE danger_level_ft IS NULL) null_danger, count(DISTINCT station) stations, count(DISTINCT river) rivers FROM pdma_gauge_readings;"
```

**River dimension corruption (§7)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT river, count(*), count(DISTINCT station) FROM pdma_gauge_readings GROUP BY 1 ORDER BY 2 DESC;"
```

**Rainfall junk stations (§8)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT station, count(*) FROM pdma_rainfall_readings GROUP BY 1 ORDER BY 2 DESC LIMIT 20;"
```

**PDMA daily NULL dates (§9)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT count(*) total, count(*) FILTER (WHERE report_date IS NULL) null_date FROM pdma_daily_reports;"
```

**Missing tables (§10, §15)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "\dt"
```

**Other NULL rates (§13)**

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT (SELECT count(*) FROM ndma_damage WHERE roads_km IS NULL) damage_null_roads, (SELECT count(*) FROM ndma_casualties WHERE injured IS NULL) cas_null_injured, (SELECT count(*) FROM pmd_daily_forecast WHERE province='Unknown') pmd_unknown_province, (SELECT count(*) FROM pmd_daily_forecast WHERE district IS NULL) pmd_null_district;"
```

**Raw corpus counts (§3, §4, §15)**

```bash
find data/raw -type f | sed -n 's/.*\.//p' | sort | uniq -c
```

**Airflow log error density (§14)**

```bash
grep -rlE "ERROR|Traceback|Exception" airflow/logs | wc -l
```
