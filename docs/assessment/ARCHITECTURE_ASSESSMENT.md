# Architecture Assessment — Pakistan Operational Risk Intelligence Platform

| | |
|---|---|
| **Status** | Baseline of record (Phase 0) |
| **Assessment date** | 2026-09-01 |
| **Branch inspected** | `project-redesign-baseline` @ `d452c3b` |
| **Scope** | Read-only technical assessment. No files modified, no database writes, no Docker/AWS/Git changes. |
| **Supersedes** | Nothing. This is the first formal assessment. |
| **Related** | [`../DATA_QUALITY_BASELINE.md`](../DATA_QUALITY_BASELINE.md) · [`../decisions/ADR-0001-baseline-and-recovery.md`](../decisions/ADR-0001-baseline-and-recovery.md) |

## Method

Every claim in this document is traceable to one of five evidence sources:

1. **Source code** — all 168 tracked non-data files read in full.
2. **Live database** — read-only `SELECT` queries against the running `airflow_postgres` container (row counts, null ratios, distinct values, DAG and task states).
3. **Airflow task logs** — 4,771 log files aggregated for error signatures; recent failures read line by line.
4. **Filesystem** — file and directory counts under `data/`.
5. **Git** — history, branches, tracked-file inventory.

Where a claim rests on inference rather than direct evidence, it is marked as such.

---

# PART A — CURRENT STATE

## A.1 Executive verdict

| Dimension | Status |
|---|---|
| Code volume | ~21,000 lines of Python across 168 tracked files |
| Pipeline health | **Red.** 38 of 39 DAG runs failed. One success, ever. |
| Data freshness | NDMA stale 35 days · PDMA stale 32 days · PMD stale 20 days |
| Data correctness | 46% of gauge water levels NULL · 51% of danger levels NULL · 93% of daily reports have no date · river dimension corrupted |
| Geographic coverage | Punjab only for hydrology/rainfall; province-only for disasters. No division/tehsil hierarchy, no geometry. |
| Real-time capability | None. All batch, all full-refresh, all polling. |
| Cloud | S3 upload active. Glue/Redshift/Lambda written but never wired in — and the PDMA Glue script is a byte-identical copy of the PMD one. |
| Tests | **Zero.** No test file, no CI, no pre-commit, no `pyproject.toml`. |
| Security | DB password printed to logs in two places · SMTP app-password in `.env` · application data inside the Airflow metadata DB |

**The platform is currently non-functional in production.** This is not a subjective judgement — it is what the Airflow metadata database reports.

## A.2 Live runtime evidence

Every DAG is unpaused and scheduled. Every scheduled run fails.

```
dag_id                 state     count   last_run
backfill_pipeline      failed        1   2026-08-31
disaster_pipeline      failed        5   2026-09-01
manual_pipeline        failed        2   2026-08-31
ndma_pipeline          failed       17   2026-09-01
pdma_pipeline          failed        7   2026-09-01
pmd_pipeline           failed        5   2026-09-01
pmd_pipeline           success       1   2026-09-01
weekly_full_pipeline   failed        1   2026-08-31
```

Task-level pattern:

- `ndma_pipeline` — `extract_ndma` succeeds **17/17**; `parse_ndma` fails **17/17**; everything downstream `upstream_failed`.
- `pdma_pipeline` — `extract_pdma` fails **7/7** on the first page of the first report.
- `pmd_pipeline` — extract and validate succeed; `load_postgres` fails 5 of 6.
- `disaster_pipeline` triggers NDMA first with `wait_for_completion=True`. NDMA fails, so PDMA and PMD **never run at all**. The master DAG actively blocks the two pipelines it was built to orchestrate.

### The three live root causes

**1. `parse_ndma` — `PermissionError: [Errno 1] Operation not permitted`**

`scripts/parsing/parse_ndma.py:107` calls `shutil.copy2()` to quarantine a rejected PDF. `copy2` calls `copystat` → `utime()`, which the Windows bind mount denies to uid 50000. The *first* PDF processed (`6a3e702a90f23.pdf`) is rejected, so the run dies on file 1 of 70 — every time, on every retry, for five weeks.

**2. `extract_pdma` — `PermissionError: [Errno 13] Permission denied: 'debug_pdma.html'`**

`scripts/extraction/extract_pdma.py:91` writes a leftover debug file into the project root on every page fetch. It kills the crawl before a single PDF is downloaded. The site returned HTTP 200 — the source is fine, the code is not.

**3. Every task callback throws `SMTPAuthenticationError (535 BadCredentials)`**

`pipeline/utils/task_callbacks.py` sends an email on **every task success and every task failure**. The Gmail app password is dead. This fires on all ~40 task instances per pipeline cycle, adds latency to every task, and buries the real error under an SMTP stack trace — which is why the actual failure reason was invisible.

### Historical failure signatures across 4,771 task logs

| Count | Error | Meaning |
|---:|---|---|
| 4,271 | `TypeError: not all arguments converted during string formatting` | `extract_ndma.py:77` passes 3 args for 2 format placeholders. Fires on every page of every crawl. |
| 2,016 | `psycopg2.errors.InFailedSqlTransaction` | One bad row aborts the whole `engine.begin()` block; every subsequent insert in that load fails. **The mechanism by which entire loads silently vanish.** |
| 1,237 | `ModuleNotFoundError: No module named 'airflow.utils.task_callbacks'` | Local module paths collided with the installed `airflow` package namespace. |
| 804 | `ImportError: cannot import name 'DAG' from 'pipeline'` | Local package names shadowing framework names. |
| ~500 | `NameError: 'upload_folder' / 'timedelta' / 'Path' / 'start_glue_job' / 'verify_tables' … not defined` | Imports commented out while the function bodies using them were left behind. Systemic. |
| 82 | `UndefinedTable: relation "ndma_casualties" / "pmd_daily_forecast" / "pdma_*" does not exist` | **DDL is never run by any DAG.** Table creation is a manual, undocumented, out-of-band step. |
| 25 | `UndefinedColumn: column "district" of relation "pmd_daily_forecast" does not exist` | Schema drift — see A.5. |
| 9 | `UniqueViolation on ndma_casualties_..._province_key` | Duplicate loads. |

## A.3 Current architecture

```
┌─────────────────────── SOURCES (all scraped; none offer an API) ───────────────────────┐
│  ndma.gov.pk          pdma.punjab.gov.pk        nwfc.pmd.gov.pk  +  pmd.gov.pk         │
│  sitreps/advisories/  daily / rainfall /        daily-forecast / weekly-outlook /       │
│  guidelines (PDF)     gauge / earthquake (PDF)  latest-weather-alerts (HTML)            │
└────────┬────────────────────────┬──────────────────────────────┬───────────────────────┘
         │                        │                              │
    ┌────▼─────┐            ┌─────▼──────┐                 ┌─────▼──────┐
    │ extract_ │            │ extract_   │                 │ extract_   │
    │ ndma.py  │            │ pdma.py    │                 │ pmd.py     │
    │ ✔ runs   │            │ ✘ CRASHES  │                 │ ✔ runs     │
    └────┬─────┘            └─────┬──────┘                 └─────┬──────┘
         │ PDFs + metadata.json   │ PDFs + metadata.json         │ latest.json (OVERWRITES)
         ▼                        ▼                              ▼
   data/raw/ndma/…          data/raw/pdma/…              data/raw/pmd/…/latest.json
   311 pdf, 2 images        420 pdf, 67 images           3 files, no history
         │                        │                              │
    ┌────▼─────┐            ┌─────▼──────┐                 ┌─────▼──────┐
    │parse_ndma│            │ parse_pdma │                 │ pmd/       │
    │ ✘ CRASHES│            │ (3 parsers)│                 │ pipeline.py│
    │ on file 1│            │ silent drop│                 │ ✔ runs     │
    └────┬─────┘            └─────┬──────┘                 └─────┬──────┘
         │ 33/70 (47%)            │ 61 of 88 rainfall reports    │ latest.json
         │                        │   silently dropped            │  (OVERWRITES)
         ▼                        ▼                              ▼
  data/parsed/ndma/       data/parsed/pdma/{daily,       data/parsed/pmd/*/latest.json
  sitreps/*.json           rainfall,gauge}/{2025,2026}/
         │                        │                              │
    ┌────┴──────┐                 │                              │
    ▼           ▼                 │                              │
build_ndma_  load_ndma.py    load_pdma.py                  load_pmd.py
dataset.py   ✘ TRUNCATEs      2 divergent copies           ✔ works
✘ relief=0     all 4 tables    exist in repo
✘ houses=null  every run
    │           │                 │                              │
    ▼           └────────┬────────┴──────────────────────────────┘
data/analytics/          ▼
ndma/*.json      ╔═══════════════════════════════════════════════════════╗
    │            ║  PostgreSQL 15 — database "airflow", schema "public"  ║
    │            ║  ⚠ SAME DATABASE AS AIRFLOW'S OWN METADATA (54 tables)║
    │            ║  ndma_casualties 224 · ndma_damage 132                ║
    │            ║  ndma_relief 1686 · ndma_rescue 89                    ║
    │            ║  pdma_daily_reports 80 · pdma_rainfall_readings 869   ║
    │            ║  pdma_gauge_readings 9517 · pmd_daily_forecast 108    ║
    │            ║  pmd_weekly_outlook 7 · pmd_weather_alerts 1          ║
    │            ║  geo_locations 95 · operational_risk 0 (never ran)    ║
    │            ║  pipeline_logs — DOES NOT EXIST (dashboard queries it)║
    │            ╚═══════════════════════┬═══════════════════════════════╝
    │                                    │
    ▼                                    ▼
 aws/s3/upload.py               dashboard/ (Streamlit, 12,398 lines)
 (HEAD-check skip)              Home + 5 pages, 60s autorefresh
    │                           ✘ queries table "pmd_weather" (Redshift name,
    ▼                              does not exist in Postgres) → silent empty
 s3://<bucket>/{raw,parsed,     ✘ queries "pipeline_logs" → "Last Update" always blank
   analytics}/…                 ✘ prints DB password to stdout
    │
    ╎ ─────────── EVERYTHING BELOW IS WRITTEN BUT COMMENTED OUT OF EVERY DAG ───────────
    ╎
    ▼
 AWS Lambda s3_trigger.py  →  AWS Glue (etl_ndma / etl_pdma / etl_pmd)  →  Redshift
                               ⚠ etl_pdma.py is byte-identical to etl_pmd.py
                               ⚠ preactions: DELETE FROM <table> — full wipe every run
                               ⚠ reads only latest.json — one snapshot, no history

 ╎ scripts/warehouse/ — star schema (dim_date/province/river/station, 4 facts)
 ╎   Never called by any DAG. 3 of 17 files are empty. dim_*/fact_* tables absent from the DB.
 ╎ scripts/risk_engine/ — operational_risk table exists, 0 rows, never run.
 ╎ pipeline/sensors/ — 3 sensors, imported by no DAG.
 ╎ pipeline/utils/metadata_logger.py, duplicate_checker.py — EMPTY FILES.
```

## A.4 Component inventory

### Working

| Component | Evidence |
|---|---|
| NDMA extraction | `extract_ndma` succeeded 17/17 runs; 311 PDFs on disk |
| PMD extraction and parsing | 6/6 successes; produces valid JSON |
| `load_pmd.py` | Succeeded once; 108 rows landed with correct types |
| `load_pdma.py` (the newer copy) | Uses `ON CONFLICT DO NOTHING` and a real `parse_date()`; 9,517 gauge + 869 rainfall rows landed |
| NDMA → Postgres relief path | 1,686 rows — the only NDMA path working end to end |
| S3 idempotent upload | Skips existing keys via HEAD; DAG task wired and live |
| Docker Compose | 3 containers up; Postgres healthy |
| Dashboard rendering | Loads, charts render, CSV/Excel export works |
| `geo_locations` seed | 95 rows with real coordinates |
| README | Unusually honest — already flags Glue/Redshift/warehouse as unscheduled |

### Broken or incomplete

| Component | Defect | Evidence |
|---|---|---|
| `parse_ndma.py` | `copy2()` PermissionError kills run on file 1 | live log, attempt 4 |
| `extract_pdma.py` | `debug_pdma.html` write kills crawl on page 1 | live log, attempt 4 |
| `extract_pdma.py:86` | `response.status_code` read **before** the `if response is None` guard at line 95 — dead check | code |
| `build_ndma_dataset.py` relief | Treats dict rows as lists → `len(row)=3 < 8` → **every row dropped** | `relief.json` = 0 rows |
| `build_ndma_dataset.py` damage | Reads `houses_total`; parser emits `houses_damaged` | every `houses_total` null in `damage.json` |
| `aws/s3/upload.py:88` | `print(f"…{s3_key}…")` outside the loop → `NameError` on an empty folder | code |
| `aws/s3/upload.py:32` | Bare `...` (Ellipsis) statement | code |
| `create_pmd_tables.py` | `MIGRATIONS` (ALTER TABLE) run **before** `TABLES` (CREATE) → fails on a fresh DB | code |
| `create_pdma_tables.py` | **Contains the old PDMA loader, not DDL.** Mislabelled; the README instructs you to run it | `diff` vs `load_pdma.py` |
| `etl_pdma.py` | Byte-identical to `etl_pmd.py` — PDMA has no Glue job | `diff` returns identical |
| `validation/translator.py` | `normalize_city` defined **twice**; the second (string-returning) silently wins | code |
| `validation/rules.py` | All four rule functions defined **twice**; `import pandas` used only by the dead copy | code |
| `parse_pdma_daily.py` | `extract_temperature` / `extract_rainfall` each defined twice | code |
| `load_ndma_v2.py` | Inserts `source_file`, `district` — columns that do not exist | code + DDL |
| `metadata_logger.py`, `duplicate_checker.py`, `load_dimensions.py`, `load_facts.py`, `warehouse_models.py` | **Empty files** | 0 lines |
| `pipeline_logs` table | Queried by the dashboard, written by `pipeline_logger.py`, **created by nothing** | absent from `\dt` |
| `pipeline/sensors/*` | Never imported by a DAG | grep |
| `scripts/warehouse/*` | 1,648 lines, never invoked; tables absent from the DB | `\dt` |
| `risk_engine.py` | `operational_risk` = 0 rows | live query |
| `setup_airflow.py` | Points `dags_folder` at `airflow/dags`, a directory that does not exist (only `airflow/logs`). Docker mounts `pipeline/dags`. Local Airflow finds zero DAGs. | filesystem |
| `requirements.txt` | **UTF-16 encoded** (PowerShell `pip freeze >`). `pip install -r` fails on Linux. | hexdump |
| `airflow_requirements.txt` | Fully unpinned → non-reproducible image builds | file |
| `.env.docker` | Tracked in git despite `.env.*` in `.gitignore` (added before the rule) | `git ls-files` |
| 67 image files | `.jpg`/`.png` downloaded into `pdfs/` folders; `glob("*.pdf")` skips them forever | file counts |
| `earthquake_reports` | Downloaded (3 PDFs) but absent from `parse_pdma.REPORTS` — never parsed | code |
| NDMA advisories + guidelines | 243 PDFs downloaded, no parser exists | file counts |

## A.5 Data quality risks

Measured, not estimated. Full figures and reproduction queries: [`../DATA_QUALITY_BASELINE.md`](../DATA_QUALITY_BASELINE.md).

Summary of the most serious findings:

- **River gauges** — 28% NULL timestamps, 46% NULL water levels, 51% NULL danger levels. The river dimension contains corrupted entities: `1230DG KHAN 1230HILL TORRENTS` (a report time bled into the name), `NULLAHS DATA SOURCE: F` (PDF footer text), and letter-spaced duplicates of real rivers. A station named `SITE` exists — a table header that became data.
- **Rainfall** — the most frequent "station" is the literal word `Stations` (74 rows). 161 distinct station names for a province with 36 districts.
- **PDMA daily reports** — 93% have `report_date = NULL`.
- **NDMA** — 53% of sitreps rejected; 56% of damage rows have NULL `roads_km`; 15% of casualty rows have NULL `injured`.
- **PMD** — 108 rows sharing one timestamp; 28% have `province = 'Unknown'`. No historical archive at any layer.

Root causes, in order of impact:

1. **Hardcoded column indices in PDF parsers.** `parse_gauge.py` requires `len(row) >= 12` and reads `row[3]`, `row[6]`, `row[9]`, `row[11]`. When `pdfplumber` merges or splits a cell — which it does constantly on these layouts — rows are either dropped without a counter or shifted, writing *wrong numbers into the right columns*.
2. **No station or river reference data.** Every name is free text, so header rows, footers and OCR artefacts become first-class entities.
3. **Whole-load transactions.** One bad value rolls back thousands of good rows (2,016 logged occurrences).
4. **Date strings passed to `DATE` columns.** Under Postgres `DateStyle = MDY`, `"12.07.2026"` becomes 7 December, not 12 July. Values with day > 12 raise instead — aborting the transaction.
5. **Naive timestamps throughout.** Pakistan is UTC+5 with no DST; containers run UTC. Every "0800–0800 hrs" observation window is off by five hours with nothing recording that.
6. **Divergent numeric coercion.** `load_ndma.to_int()` does not strip commas (`"1,234"` → `None`); `load_pdma.to_int()` does. Two behaviours in one codebase.
7. **`load_ndma.py` TRUNCATEs all four NDMA tables on every run**, then reloads only what survived parsing that day. A parser regression does not degrade the data — it erases it.
8. **Wrong dedup keys.** `load_ndma` matches on `(report_number, province)` with no date, so sitrep "02" from 2025 and "02" from 2026 collide. `pdma_*` dedups on `(source_file, station)` where the natural key is `(station, observed_at)`.

### Duplication and staleness mechanics

Seven DAGs invoke the *same* scripts against the *same* full data directory. Nothing is incremental; every run reprocesses everything from the beginning of time. `disaster_pipeline` re-triggers the three domain DAGs with `reset_dag_run=True` while those DAGs are *also* on their own schedules — so the same work is queued twice, and with `max_active_runs=1` plus `wait_for_completion=True` on a LocalExecutor, the master DAG occupies a worker slot while waiting for a DAG that cannot start.

S3 idempotency is HEAD-based: if a source *revises* a report under the same filename, it is skipped forever. `object_exists()` also creates a new boto3 client per file (800+ per run) and swallows `403` as "does not exist".

## A.6 Geographic coverage gaps

| Target level | Present today |
|---|---|
| Country | Implicit only |
| Province / Region | Free-text strings. `'AJ&K'`, `'GB'`, `'KP'`, `'ICT'` in NDMA data vs `'AJK'`, `'Gilgit Baltistan'`, `'Khyber Pakhtunkhwa'`, `'Islamabad Capital Territory'` in the mappings. No canonical codes. |
| Division | **Absent entirely** |
| District | Punjab only, in a hardcoded 40-name Python list containing both `"DG Khan"` and `"D.G. Khan"` |
| Tehsil / Taluka | **Absent entirely** |
| Town / City | ~40 PMD cities, hardcoded |
| Locality | **Absent entirely** |
| Station / gauge / sensor | Free-text names only. No registry, no IDs, no coordinates, no elevation, no operating agency, no datum. |

`geo_locations` (95 rows) is the only spatial artefact. It has no `parent_id`, so no hierarchy. It stores **rivers as single points** — the Indus is one lat/lon. It contains duplicate province rows (`"KP"` *and* `"Khyber Pakhtunkhwa"` as separate records), and `UNIQUE(name, location_type)` lets `Lahore` exist as both a district and a city with identical coordinates. There is no PostGIS, no geometry column, no P-code, no GADM/HDX linkage.

**Five independent, mutually inconsistent city→province mappings exist:**

1. `scripts/extraction/common/pmd_parser.URDU_CITY_MAP` (59 entries)
2. `scripts/parsing/pmd/utils.CITY_PROVINCE` + `CITY_DISTRICT` (~40)
3. `validation/translator.CITY_TRANSLATIONS` + `CITY_INFO` (~45)
4. `validation/mappings.CITY_MAPPING` (9)
5. `scripts/parsing/pmd/alerts_parser.REGIONS` (~50)

They disagree: `utils` maps Chitral → `Chitral`, `translator` maps Chitral → `Upper Chitral`. `utils` uses province `"Islamabad"`, `translator` uses `"Islamabad Capital Territory"`.

**A modelling decision that must be made deliberately:** the PMD scraper's Urdu map and `parse_pdma_daily.KNOWN_DAMS` both ingest entities outside Pakistan's administrative control — Srinagar, Jammu, Anantnag, Pulwama, Shopian, Baramulla, Leh (from PMD's Kashmir forecast page) and Bhakra, Pong, Thein (Indian dams referenced in Punjab flood reports). These currently land in the same tables with no country or control-status attribute.

Coverage today: **Punjab hydrology + national-but-province-only disaster counts + ~40 weather cities.** Sindh, KP, Balochistan, GB, ICT and AJK have no dedicated ingestion.

## A.7 Real-time and live data gaps

There is nothing live. `st_autorefresh(60s)` over a table whose newest row is five weeks old is cosmetic — and the pulsing "Live Monitoring Active" badge on the rivers page is actively misleading.

Missing: event-driven ingestion, change-data capture, push/webhook sources, message bus, streaming state, alert evaluation engine, notification delivery, incident lifecycle, subscription management. PMD publishes several times daily; the platform polls every 6 hours and overwrites. The Lambda → Glue trigger exists in code but is not deployed.

## A.8 Airflow reliability risks

| Risk | Detail |
|---|---|
| `days_ago(1)` as `start_date` | Deprecated, and **evaluated at every DAG-file parse** — the start date walks forward, making scheduling non-deterministic. All 7 DAGs. |
| No `execution_timeout` anywhere | A hung PDF parse or HTTP call blocks a LocalExecutor slot indefinitely. |
| Master-DAG deadlock | `disaster_pipeline` + individual schedules + `max_active_runs=1` + `wait_for_completion=True` + `reset_dag_run=True` = self-blocking. |
| `retries=3` on non-idempotent tasks | Failed loads retry against partially written state. |
| Callbacks perform network I/O | Every task success sends an email. Every send currently fails. |
| `AIRFLOW__CORE__FERNET_KEY: ""` | Connection and Variable encryption effectively disabled. |
| Subprocess-per-task | `run_script()` shells out with `capture_output=True` — no streaming logs, no XCom, no partial progress, no structured result. Airflow is being used as cron. |
| No sensors, datasets or partitioning | Nothing is data-aware; nothing is incremental. |
| No DAG-level SLA or freshness check | A DAG that "succeeds" while writing zero rows is indistinguishable from a healthy one. |
| Orphaned DAG history | `airflow/logs/dag_id=pakistan_disaster_pipeline/` — a DAG deleted from the repo but still in metadata. |
| 4,771 log files on disk | `pdf_table_reader.py` prints 10 rows of every table on every page; `parse_rainfall.py` prints 1,500 characters of every page. |
| No DAG integrity test | A `DagBag` import test would have caught the 804 `ImportError`s and ~500 `NameError`s before they ever ran. |

## A.9 Database risks

**The most serious structural issue: application data lives inside the Airflow metadata database.**

`.env.docker` sets `DB_NAME=airflow`, `DB_USER=airflow` — the same database and superuser as `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`. `\dt` confirms `ndma_casualties`, `pdma_gauge_readings`, `geo_locations` and `operational_risk` sitting in `public` next to `dag`, `task_instance`, `xcom` and `ab_user`.

Consequences: `airflow db reset` or an Airflow upgrade can destroy the data; neither can be backed up or restored independently; the dashboard connects as the Airflow admin; there is no least-privilege boundary anywhere.

Additional risks:

- **No migration tool.** No Alembic. Schema evolves via ad-hoc `CREATE TABLE IF NOT EXISTS` across five scripts plus inline `ALTER TABLE`. `create_tables.py` and `create_pmd_tables.py` define the *same tables with different constraints* — whichever runs first wins. This is the direct cause of the 25 logged `UndefinedColumn` errors.
- **DDL is not orchestrated.** No DAG creates tables; the 82 `UndefinedTable` errors follow.
- **N+1 query pattern.** Every loader issues `SELECT 1 … LIMIT 1` per row before inserting. ~7,000 round-trips per PDMA run, and it is racy — `ON CONFLICT` exists and should be used.
- **Whole-load transactions.** One bad value rolls back thousands of good rows.
- **`raw_text` of every sitrep stored in Postgres**, plus full report JSON in `pdma_daily_reports.raw_data` — no size limit, no archival tier.
- **No `updated_at`, no soft delete, no bitemporality, no source-lineage columns.** The question "which file produced this row, and when did we learn it?" cannot be answered.
- **`config/database.py` builds a module-level engine at import and prints the full `DATABASE_URL` including the password.**
- **No partitioning, retention policy, or vacuum/analyze strategy.**

## A.10 Cloud and AWS gaps

- Glue, Redshift and Lambda are commented out of every DAG. Confirmed: no warehouse is running; spend is S3-only.
- `etl_pdma.py` ≡ `etl_pmd.py`. Enabling the "PDMA" job would load PMD data into PMD tables and report success.
- Glue writes use `preactions: DELETE FROM <table>` — full wipe and replace, so Redshift could never hold history.
- Glue reads only `latest.json` — a single snapshot.
- Redshift DDL defines a `pmd_weather` table that the **Streamlit dashboard queries against Postgres**, where it does not exist. The dashboard's SQL was written for the wrong engine.
- No IaC. No Terraform, CDK or CloudFormation. Everything is boto3 scripts run by hand.
- Long-lived IAM access keys in `.env`; no roles, no least privilege, no rotation, no KMS.
- No S3 lifecycle policy, versioning, Glacier tiering, bucket policy or encryption config.
- No CloudWatch alarms, no cost budget or alert.
- No partitioned S3 layout (`source=/domain=/dt=`) — it mirrors the local folder tree, so partition pruning is impossible.

## A.11 Dashboard gaps

- **Password leak.** `dashboard/db.py:52` — `print("PASS =", password)`.
- **`_read_sql` swallows every exception and returns an empty DataFrame.** The UI cannot distinguish "no data" from "the query is broken". This is why nobody noticed that:
  - `get_latest_weather()` and `get_weather_summary()` query `FROM pmd_weather` — **a table that does not exist in Postgres**. The "hottest city" KPI and the entire weather summary have silently returned nothing since they were written.
  - `get_dashboard_summary()` queries `pipeline_logs` — **also non-existent**. "Last Update" is permanently blank.
  - `get_weather_summary` casts `max_temperature::numeric` from text, while the column is `REAL`.
- **12,398 lines with ~2,250 lines of near-identical inline CSS duplicated across five pages**, despite `styles/style.css` and `theme.py` existing.
- **No map.** `pydeck` is installed and unused. `geo_locations` has coordinates and nothing joins to them. For a geospatial risk platform this is the largest product gap.
- No public or citizen view. No "select your district → see your risk" flow. No mobile layout, no Urdu, no accessibility pass.
- No authentication, roles or audit. `execute_query()` accepts arbitrary SQL including DDL.
- Unbounded queries: `get_pdma_rivers()` pulls every row with no date filter, re-executed every 60 seconds per browser session, followed by heavy pandas groupbys per rerun.
- Misleading UI: a pulsing "Live Monitoring Active" badge over five-week-old data.
- Dead code: `components/filters.py::render_global_filters` is never imported (Home uses `components/sidebar.py`).
- Not a service in `docker-compose.yml` — run separately by hand.

## A.12 Observability gaps

- `pipeline_logs` is written by `pipeline_logger.py` and read by the dashboard, but **created by nothing**. Every call fails.
- `metadata_logger.py` and `duplicate_checker.py` are **empty files**.
- No metrics, no StatsD/Prometheus, no dashboards, no tracing, no structured logging (everything is `print()`).
- **No data-quality gates in the pipeline.** `parse_pdma.py` catches per-file exceptions, prints, and continues — so a run in which 61 of 88 reports fail exits 0 and Airflow shows green. `pipeline/utils/data_quality.py` contains real checks; no DAG calls it.
- No freshness monitoring, volume anomaly detection, schema-drift detection or lineage.
- Alerting is a dead Gmail app password. `sns_alert.py` exists and is wired to nothing.
- Rejected records: NDMA quarantines PDFs but records no queryable reason; PDMA and PMD drop invalid records with no trace at all.

## A.13 Security gaps

| Severity | Issue |
|---|---|
| **High** | DB password printed to stdout in `config/database.py:39` and `dashboard/db.py:52` — captured in every Airflow task log |
| **High** | Application data in the Airflow metadata DB, accessed as the Airflow superuser |
| **High** | Long-lived AWS access keys in `.env`; no rotation, no role assumption |
| **High** | `AIRFLOW__CORE__FERNET_KEY: ""` |
| Medium | Gmail SMTP app password stored in plaintext `.env` |
| Medium | Hardcoded `admin/admin` (Docker) and `admin/admin123` (`setup_airflow.py`) |
| Medium | `.env.docker` tracked in git (contains only non-secret values today, but the pattern is wrong) |
| Medium | `execute_query()` in the dashboard runs arbitrary SQL/DDL |
| Medium | Spoofed browser User-Agent in `fetcher.py`; no robots.txt check, no rate limit, no attribution on scraped government sources |
| Low | No dependency scanning, SBOM, `pip-audit` or Dependabot |
| Low | No TLS anywhere; no secrets manager; no network segmentation |

**Verified good:** `.env` is untracked and has never been committed (`git log --all -- .env` is empty).

## A.14 Testing gaps

**There are no tests.** No `tests/`, no `test_*.py`, no `conftest.py`, no `pytest.ini`, no `pyproject.toml`, no `tox.ini`, no `Makefile`, no `.pre-commit-config.yaml`, no `.github/`.

`scripts/parsing/test_cleaner.py`, `test_pdf.py` and `test_tables.py` are manual print-scripts, not tests.

Every one of the ~500 `NameError` and ~900 `ImportError` failures in the logs would have been caught by a single 15-line `DagBag` import test.

---

# PART B — TARGET STATE

## B.1 Target architecture

```
╔═══════════════════════════════ SOURCE LAYER ═══════════════════════════════╗
║ APIs/feeds:  Open-Meteo · OpenWeather · WAQI/OpenAQ · USGS + EMSC quakes   ║
║              GDACS · Copernicus EMS · GloFAS · CHIRPS · IMERG · Sentinel   ║
║ Scraped:     NDMA · PDMA Punjab/Sindh/KP/Balochistan/GB/AJK · PMD · FFD    ║
║ Reference:   HDX/OCHA P-codes · GADM · PBS census · OSM · SRTM/Copernicus  ║
╚════════════════════════════════════╤═══════════════════════════════════════╝
                                     │
┌────────────────────────────────────▼───────────────────────────────────────┐
│ INGESTION — one connector interface, many implementations                  │
│ BaseConnector: discover() → fetch() → checksum() → persist_raw() → emit()  │
│ Immutable raw landing, content-addressed, timestamped, never overwritten    │
│ raw/source=<s>/domain=<d>/dt=<YYYY-MM-DD>/ingested_at=<ts>/<sha256>.<ext>  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼───────────────────────────────────────┐
│ PARSE & NORMALISE — pure functions, versioned, contract-tested              │
│  · parser_version stamped on every record                                   │
│  · Pydantic schemas as the single source of truth                           │
│  · Failures → quarantine WITH reason, never dropped                         │
│  · Canonical geo resolution + unit/timezone normalisation (UTC + PKT)       │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼───────────────────────────────────────┐
│ VALIDATE — Pandera / Great Expectations, blocking gates                     │
│  Row counts · null ratios · ranges · referential integrity to geo & station │
│  · freshness · schema drift · unit sanity. FAIL = task fails, loudly.       │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
        ┌────────────────────────────┴────────────────────────────┐
        ▼                                                          ▼
╔════════════════════════════════╗              ╔══════════════════════════════════╗
║ OPERATIONAL STORE              ║              ║ LAKEHOUSE                        ║
║ PostgreSQL 16 + PostGIS 3.4    ║              ║ MinIO (local) → S3 (cloud)       ║
║ DB: pori (NOT airflow)         ║              ║ Delta Lake or Apache Iceberg     ║
║                                ║              ║                                  ║
║ geo.*    admin hierarchy       ║              ║ bronze/ raw as-landed            ║
║ ref.*    stations, rivers,     ║              ║ silver/ parsed + conformed       ║
║          dams, road segments   ║              ║ gold/   analytics-ready facts    ║
║ obs.*    observations (hyper-  ║              ║                                  ║
║          table, partitioned)   ║              ║ PySpark transforms               ║
║ evt.*    incidents, alerts     ║              ║ (local Spark → Databricks Free)  ║
║ dq.*     quality + lineage     ║              ╚═══════════════╤══════════════════╝
║ ops.*    pipeline runs, audit  ║                              │
╚═══════════╤════════════════════╝                              ▼
            │                                         ╔══════════════════════════╗
            │◄────────────────────────────────────────║ dbt-core                 ║
            │                                         ║ staging → marts          ║
            │                                         ║ tests · docs · lineage   ║
            │                                         ╚══════════════════════════╝
┌───────────▼─────────────────────────────────────────────────────────────────┐
│ SERVING                                                                      │
│  FastAPI  — REST + OpenAPI, JWT/RBAC, rate limits, GeoJSON & vector tiles    │
│  Redis    — cache, rate limiting, Celery broker                              │
│  pgvector — embeddings for RAG (Postgres extension, no new datastore)        │
└───────────┬──────────────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────────────────┐
│ INTELLIGENCE                                                                  │
│  Rules      deterministic thresholds (danger level, rainfall, AQI, heat)      │
│  Anomaly    STL/seasonal decomposition, IsolationForest, CUSUM                │
│  Forecast   Prophet / LightGBM / (later) LSTM — river stage, rainfall         │
│  Risk score composite, explainable, versioned, per admin unit                 │
│  MLflow     experiments, model registry, reproducibility                      │
│  RAG        chunk sitreps/advisories → pgvector → grounded, cited answers     │
│  Agents     tool-using review loop over the same API — human-in-the-loop      │
└───────────┬──────────────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                                  │
│  Public app     React/Next + MapLibre GL — "pick your district" risk view     │
│  Ops console    Streamlit (internal analysts, keeps existing investment)      │
│  Executive BI   Superset (or Power BI) over the gold marts                    │
│  Platform ops   Grafana — pipeline health, freshness, DQ trends               │
└───────────┬──────────────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────────────────┐
│ CROSS-CUTTING                                                                 │
│  Airflow 2.10+ (data-aware, incremental) · Redpanda/Kafka (Phase 7)           │
│  OpenTelemetry · Prometheus · Grafana · structlog                             │
│  GitHub Actions CI · Terraform IaC · SOPS/age or AWS Secrets Manager          │
│  pytest + Pandera + dbt tests · pre-commit (ruff, mypy, black)                │
└──────────────────────────────────────────────────────────────────────────────┘
```

## B.2 Technology decision matrix

| Technology | Verdict | Reasoning |
|---|---|---|
| **PostgreSQL** | **Keep — promote to system of record** | Already central, already known, handles this volume for years. Move to its own DB `pori` on Postgres 16. |
| **PostGIS** | **Adopt — Phase 2, non-negotiable** | Every stated requirement ("select your tehsil", "which districts are at risk", river/road segments, catchments) is a spatial join. `ST_Contains`, `ST_DWithin` and GiST indexes replace all five broken string-matching city maps. |
| **TimescaleDB** | **Adopt — Phase 2, optional but high value** | A Postgres extension, not a new system. Hypertables, continuous aggregates and compression fit station observations exactly. Zero migration cost if declined. |
| **Apache Airflow** | **Keep — but use it properly** | Upgrade to 2.10+/3.x. Replace `subprocess` shell-outs with real callables; adopt Datasets, `@task`, dynamic task mapping, `execution_timeout` and a static `start_date`. Airflow is not the problem; using it as cron is. |
| **Kafka / Redpanda** | **Defer to Phase 7. Then Redpanda.** | Nothing is streaming today. Redpanda is Kafka-API-compatible, a single binary, no ZooKeeper — same learning at a fraction of the operational cost. |
| **AWS S3** | **Keep, but MinIO first** | Develop against MinIO locally (S3 API, free, offline), promote to S3 with a config change. Restructure to Hive-style partitions; enable versioning and lifecycle. |
| **AWS Glue** | **Drop** | Expensive per-DPU-hour, slow iteration, hard to test, awkward to debug — and the two existing job scripts are duplicates of each other. Local PySpark gives identical learning at zero cost. |
| **PySpark** | **Adopt — Phase 5, locally** | Genuinely valuable and in demand. Run locally in Docker over MinIO. More is learned from a local cluster that can be broken than a managed one that cannot be afforded. |
| **Amazon Redshift** | **Drop** | Nothing is running (confirmed). Weak geospatial support, awkward streaming, thin ML story, continuous billing. Remove the code path rather than leave a broken half-integration. |
| **Databricks** | **Adopt — Free Edition, Phase 6** | Free Edition provides real Spark + Delta + Unity Catalog + MLflow + notebooks at no cost. Strongest geospatial (Mosaic/Sedona) and ML story of the three; Delta Lake keeps the data portable. **Recommended.** |
| **Snowflake** | **Skip for now** | Excellent product, but the trial expires, geospatial is good-not-great, and it teaches SQL-on-a-warehouse rather than distributed processing. Revisit only if a target role demands it. |
| **dbt-core** | **Adopt — Phase 6, high priority** | Free, transformative for SQL discipline, provides tests/docs/lineage almost free, and is close to a hiring prerequisite. Start against Postgres; retarget to the lakehouse later. |
| **Redis** | **Adopt — Phase 12** | API cache, rate limiting, Celery broker, alert dedup. Small, cheap, useful — but not before there is an API. |
| **OpenSearch** | **Skip** | Postgres full-text plus pgvector covers document search and RAG retrieval. A second search cluster adds operational cost with no unique benefit here. |
| **pgvector** | **Adopt — Phase 10** | Vectors live beside the data they describe; one database to run, back up and secure. Reach for a dedicated vector DB only past ~5M vectors. |
| **FastAPI** | **Adopt — Phase 12** | The contract decoupling every consumer (public app, BI, agents, partners) from the schema. Async, typed, auto-OpenAPI. |
| **Streamlit** | **Keep — repositioned** | Excellent internal analyst console. Wrong tool for a national public product. Retire the duplicated CSS; keep the analytics. |
| **MapLibre GL** | **Adopt — Phase 8/12, primary map** | Open source, no token, no vendor account, vector tiles, strong performance. Mapbox is the same API with a bill. |
| **Kepler.gl** | **Adopt for exploration only** | Strong for ad-hoc spatial analysis. Not a product surface. |
| **Apache Superset** | **Adopt — Phase 12, executive BI** | Open source, self-hostable, dashboards + scheduled reports + row-level security. Fills the executive analytics slot without a licence. |
| **Power BI** | **Optional** | Choose only if target institutions already live in it — plausible for Pakistani government and NGO reporting. Desktop is free; Service is per-user. Keep as a consumer of the API/marts, never the modelling layer. |
| **Grafana** | **Adopt — Phase 13** | Platform observability: DAG health, freshness, DQ trends, API latency. Not the user-facing product. |
| **MLflow** | **Adopt — Phase 9** | Free, local, and the difference between "I trained a model" and "I can reproduce, compare and register models". |
| **ML tooling** | scikit-learn → statsmodels/Prophet → LightGBM → PyTorch last | Earn the deep-learning step. A well-tuned LightGBM on good features beats a rushed LSTM on bad ones. |
| **Pandera / Great Expectations** | **Adopt — Phase 1** | Pandera first (lighter, code-first, pairs with Pydantic); Great Expectations when a data-docs site is wanted. |
| **Terraform** | **Adopt — Phase 14** | IaC for whatever cloud footprint survives. Replaces hand-run boto3 provisioning scripts. |

## B.3 Geographic data model

Schema `geo` — one recursive administrative table plus typed feature tables. Nothing here invents data: every level is populated only where an authoritative boundary file exists (HDX/OCHA P-codes and GADM both publish Pakistan admin 0–3; tehsil is admin 3).

```sql
-- ═══════════ ADMINISTRATIVE HIERARCHY (recursive, self-referencing) ═══════════
geo.admin_unit
  admin_unit_id      BIGSERIAL PK
  pcode              TEXT UNIQUE        -- OCHA P-code: PK, PK1, PK101, PK10101…
  parent_id          BIGINT FK → admin_unit(admin_unit_id)
  level              SMALLINT           -- 0 country · 1 province/region
                                        -- 2 division · 3 district
                                        -- 4 tehsil/taluka/subdivision
                                        -- 5 town/city · 6 locality/union council
  name_en            TEXT NOT NULL
  name_ur            TEXT               -- Urdu, for the citizen-facing app
  name_alt           TEXT[]             -- every spelling variant seen in the wild
  iso_code           TEXT               -- ISO 3166-2 where one exists
  control_status     TEXT               -- 'administered' | 'disputed' | 'external'
  geom               geometry(MultiPolygon, 4326)  -- NULL until a boundary exists
  centroid           geometry(Point, 4326)
  area_sq_km         NUMERIC
  population         INTEGER            -- PBS census; NULL where unpublished
  population_year    SMALLINT
  source             TEXT NOT NULL      -- 'HDX-COD' | 'GADM' | 'PBS'
  valid_from         DATE               -- districts split; boundaries change
  valid_to           DATE
  UNIQUE (pcode, valid_from)
  -- GIST(geom), GIST(centroid), BTREE(parent_id), BTREE(level), GIN(name_alt)
```

`control_status` handles the Kashmir question explicitly rather than by accident: AJK and GB are `administered`; Indian-administered J&K localities appearing in PMD forecasts are `external`; the UI and API can then filter or label them deliberately.

```sql
-- ═══════════ NAME RESOLUTION (replaces all five hardcoded maps) ═══════════
geo.name_alias
  alias_id, raw_name TEXT, source TEXT, domain TEXT,
  admin_unit_id FK, station_id FK,
  match_method TEXT,     -- 'exact' | 'fuzzy' | 'manual' | 'unresolved'
  confidence NUMERIC,    -- 0..1
  reviewed_by TEXT, reviewed_at TIMESTAMPTZ
  UNIQUE (raw_name, source, domain)
```

Every unmatched name from every parser lands here as `unresolved` with confidence 0. That converts today's invisible data loss into a **reviewable work queue** — and provides the human-in-the-loop surface.

```sql
-- ═══════════ MONITORING ASSETS (schema ref) ═══════════
ref.station                         -- the generic monitoring point
  station_id, station_code TEXT UNIQUE, name_en, name_ur, name_alt TEXT[]
  station_type TEXT                 -- 'river_gauge' | 'rain_gauge' | 'weather'
                                    -- | 'aqi' | 'seismic' | 'dam' | 'barrage'
  operator TEXT                     -- PMD | WAPDA | FFD | PDMA-<province> | IRSA
  admin_unit_id FK                  -- resolved by ST_Contains, not string match
  geom geometry(Point,4326), elevation_m NUMERIC
  datum TEXT, timezone TEXT DEFAULT 'Asia/Karachi'
  active_from DATE, active_to DATE, status TEXT
  external_ids JSONB                -- {"wmo":"41640","usgs":null,...}

ref.river                           -- LINESTRING, not a point
  river_id, name_en, name_alt TEXT[], basin TEXT
  is_transboundary BOOLEAN, geom geometry(MultiLineString,4326)

ref.river_reach                     -- gauge-to-gauge segments
  reach_id, river_id FK, upstream_station_id FK, downstream_station_id FK
  geom geometry(LineString,4326), length_km NUMERIC

ref.gauge_threshold                 -- thresholds are time-varying; model them
  station_id FK, threshold_type TEXT,   -- 'low'|'medium'|'high'|'exceptional'|'danger'
  level_ft NUMERIC, discharge_cusecs NUMERIC,
  valid_from DATE, valid_to DATE, source TEXT

ref.dam                             -- reservoir, not a generic station
  dam_id, name_en, admin_unit_id FK, river_id FK, geom Point
  country TEXT DEFAULT 'PK',        -- Bhakra/Pong/Thein are NOT Pakistani
  operator, max_conservation_level_ft, dead_level_ft,
  live_capacity_maf, commissioned_year

ref.road_segment
  segment_id, road_name, road_class, admin_unit_id FK
  geom geometry(LineString,4326), osm_id BIGINT, length_km

ref.bridge
  bridge_id, name, road_segment_id FK, river_id FK
  geom Point, admin_unit_id FK, osm_id BIGINT

-- ═══════════ OBSERVATIONS (schema obs — one shape per measurement family) ═══════════
obs.river_gauge_reading
  reading_id BIGSERIAL, station_id FK NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,        -- ALWAYS tz-aware
  observed_at_local TIMESTAMP,             -- PKT, for report reconciliation
  level_ft NUMERIC, discharge_cusecs NUMERIC,
  flow_status TEXT, threshold_breached TEXT,
  quality_flag TEXT,                       -- 'valid'|'suspect'|'estimated'|'missing'
  source_document_id FK, parser_version TEXT, ingested_at TIMESTAMPTZ,
  UNIQUE (station_id, observed_at)         -- the real natural key
  -- hypertable partitioned on observed_at

obs.rainfall_reading      (station_id, observed_at, window_hours, rainfall_mm, …)
obs.weather_observation   (station_id, observed_at, temp_c, humidity_pct, wind, …)
obs.weather_forecast      (station_id, issued_at, valid_from, valid_to, horizon_h, …)
obs.air_quality_reading   (station_id, observed_at, pm25, pm10, aqi, dominant, …)
obs.seismic_event         (event_id, origin_time, geom Point, depth_km, magnitude, …)

-- ═══════════ EVENTS & IMPACTS (schema evt) ═══════════
evt.incident              -- a flood, quake, landslide: has a lifecycle
  incident_id, incident_type, severity, status,
  started_at, ended_at, geom geometry(Geometry,4326),
  admin_unit_ids BIGINT[], parent_incident_id FK,
  confidence, created_by, reviewed_by

evt.impact_report         -- replaces ndma_casualties/damage/relief/rescue
  report_id, incident_id FK, source_document_id FK,
  admin_unit_id FK,        -- province today, district when sources allow
  report_number, reported_at TIMESTAMPTZ, is_cumulative BOOLEAN,
  deaths, injured, missing,
  houses_fully_damaged, houses_partially_damaged,
  roads_km_damaged, bridges_damaged, livestock_lost,
  persons_rescued, rescue_operations,
  quality_flag, parser_version

evt.relief_distribution   (report_id FK, admin_unit_id FK, item, quantity, unit)
evt.alert                 (alert_id, alert_type, severity, issued_at, expires_at,
                           admin_unit_ids[], geom, source, headline, body_en, body_ur)

-- ═══════════ GOVERNANCE (schemas dq / ops) ═══════════
dq.source_document        -- the lineage anchor: every row traces to a file
  document_id, source, domain, source_url, s3_key,
  content_sha256 UNIQUE, published_at, fetched_at,
  file_type, page_count, parse_status, parse_error, parser_version
dq.check_result           (run_id, check_name, table_name, status, observed, expected)
dq.quarantine             (record_id, source_document_id, payload JSONB, reason, status)
ops.pipeline_run          (run_id, dag_id, task_id, status, started_at, finished_at,
                           rows_in, rows_out, rows_rejected, message)
ops.audit_log             (actor, action, entity, entity_id, at, detail JSONB)
```

### Design commitments

1. **Every observation references a `station_id`, never a free-text name.** Names are resolved once, at parse time, through `geo.name_alias`. `SITE`, `Stations` and `NULLAHS DATA SOURCE: F` cannot become entities.
2. **Every row carries `source_document_id` + `parser_version` + `ingested_at`.** Full lineage; one parser version's output can be reprocessed without touching another's.
3. **Every timestamp is `TIMESTAMPTZ`**, with `observed_at_local` kept alongside for reconciling "0800–0800 hrs PST" windows.
4. **Nothing is dropped.** Unparseable → `dq.quarantine` with a reason. Unresolvable name → `geo.name_alias` as `unresolved`.
5. **Levels populate only where authoritative boundaries exist.** Division and tehsil geometry come from HDX COD-AB; locality stays `NULL` until a source is found. The schema supports the depth; the data arrives when it arrives.
6. **`valid_from` / `valid_to` on admin units**, because Pakistani districts genuinely split (Kot Addu from Muzaffargarh, Talagang from Chakwal, Murree from Rawalpindi). Historical data must join to the boundary that existed then.

## B.4 Data source strategy

Ordered by (reliability × coverage) ÷ effort. Every source listed is real and currently published. Licences must be re-verified at implementation time — treat the licence column as "expected, to confirm".

### Tier 1 — official APIs, free, high reliability

| Source | Data | Geo resolution | Frequency | Access | Reliability | Licence (verify) | Fallback | History |
|---|---|---|---|---|---|---|---|---|
| **Open-Meteo** | Temp, precip, wind, humidity, forecast + reanalysis | Any lat/lon (~11 km) | Hourly | REST JSON, no key | High | CC-BY-4.0, free non-commercial | OpenWeather | 1940– (ERA5) |
| **USGS Earthquake** | Quakes M≥2.5 | Point + depth | Real-time | REST/GeoJSON/Atom | Very high | Public domain | EMSC | 1900– |
| **EMSC-CSEM** | Quakes, incl. felt reports | Point | Real-time | REST + WebSocket | High | Free w/ attribution | USGS | 1998– |
| **OpenAQ** | PM2.5, PM10, NO₂, O₃ | Station point | Hourly | REST, free key | Medium (sparse in PK) | CC-BY-4.0 | WAQI | 2016– |
| **WAQI** | AQI | City/station | Hourly | REST, free key (**token already held**) | Medium | Free non-commercial | OpenAQ | Limited |
| **GDACS** (UN/EC) | Multi-hazard alerts | Polygon + country | Event-driven | RSS/GeoRSS/REST | High | Free, attribution | Copernicus EMS | 2007– |
| **Copernicus EMS Rapid Mapping** | Flood extent, damage grading | 10 m raster/vector | Per activation | Web + WMS/download | Very high | Free, attribution | Sentinel Hub | 2012– |
| **GloFAS** (Copernicus) | River discharge forecast + reanalysis | 0.05° global grid | Daily | CDS API | High | Copernicus licence | — | 1979– |
| **CHIRPS** (UCSB) | Rainfall estimate | 0.05° (~5 km) | Daily, ~3-week lag | HTTP/THREDDS | Very high | Public domain | IMERG | 1981– |
| **NASA GPM IMERG** | Precipitation | 0.1° | 30 min (Early ~4 h) | Earthdata API, free reg. | Very high | Free | CHIRPS | 2000– |
| **Sentinel-1/2** (ESA) | SAR flood extent, optical | 10–20 m | 5–6 days | Copernicus Data Space | Very high | Free, open | Landsat | 2014– |
| **SRTM / Copernicus DEM** | Elevation | 30 m | Static | Direct download | Very high | Free | ALOS | Static |

### Tier 2 — official reference and boundary data

| Source | Data | Resolution | Frequency | Access | Reliability | Licence | Notes |
|---|---|---|---|---|---|---|---|
| **HDX / OCHA COD-AB Pakistan** | Admin 0–3 boundaries + **P-codes** | Country→tehsil | Annual-ish | HDX download (SHP/GeoJSON) | Very high | CC-BY-IGO | **The single most important dataset in this plan.** Authoritative P-codes end all name-matching ambiguity. |
| **GADM** | Admin 0–3 | Country→tehsil | Irregular | Direct download | High | Free non-commercial | Fallback / cross-check for HDX |
| **Pakistan Bureau of Statistics** | Census population | Admin 3–4 | Decennial | PDF/XLSX from pbs.gov.pk | High | Government open | Needed for per-capita exposure |
| **OpenStreetMap / Geofabrik** | Roads, bridges, rivers, buildings, POIs | Vector | Daily extracts | Geofabrik PBF | Medium-high (crowd) | ODbL — **share-alike, check obligations** | The only realistic source for road segments and bridges |
| **HydroSHEDS / HydroRIVERS** | River network, catchments | 15 arc-sec | Static | Download | Very high | Free research/edu | River geometry as LINESTRING |
| **WRI Aqueduct Floods** | Flood hazard/risk baselines | ~1 km | Periodic | Download | High | CC-BY-4.0 | Baseline risk layer |

### Tier 3 — Pakistani official, scraped (no API published)

| Source | Data | Resolution | Frequency | Access | Reliability | Licence | Fallback | History |
|---|---|---|---|---|---|---|---|---|
| **NDMA** ndma.gov.pk | Sitreps, casualties, damage, relief, rescue; advisories; guidelines | Province (district in annexures) | Daily in monsoon | HTML→PDF scrape | Medium (layout churn) | Gov't public, attribute | ReliefWeb, GDACS | Site archive depth varies |
| **PDMA Punjab** | Daily sitrep, rainfall, gauge, earthquake | District/station | Daily–6-hourly | HTML→PDF scrape | Medium | Gov't public | Punjab FFD | 2025– on site |
| **PDMA Sindh** | Sitreps, advisories | District | Event-driven | Scrape | Low-medium | Gov't public | NDMA | Shallow |
| **PDMA Khyber Pakhtunkhwa** | Sitreps, damage | District | Event-driven | Scrape | Low-medium | Gov't public | NDMA | Shallow |
| **PDMA Balochistan** | Sitreps | District | Irregular | Scrape | Low | Gov't public | NDMA | Very shallow |
| **GBDMA / SDMA AJK** | Sitreps | District | Irregular | Scrape | Low | Gov't public | NDMA | Very shallow |
| **PMD** pmd.gov.pk / nwfc.pmd.gov.pk | City forecast, alerts, weekly outlook, monsoon | City | 2–4×/day | HTML scrape | Medium | Gov't public, attribute | Open-Meteo | **No archive — must be built** |
| **PMD Flood Forecasting Division** | River flows, flood bulletins | Gauge | Daily in season | HTML/PDF | Medium | Gov't public | PDMA gauge | Seasonal |
| **WAPDA** | Tarbela/Mangla levels, inflow/outflow | Reservoir | Daily | HTML/PDF | Medium | Gov't public | IRSA | Multi-year |
| **IRSA** | Rim-station flows, canal withdrawals | Barrage | Daily | PDF | Medium | Gov't public | WAPDA | Multi-year |
| **NHA** | Road closures, National Highway status | Road segment | Event-driven | HTML/social | Low | Gov't public | OSM + news | None |

### Tier 4 — supplementary

| Source | Data | Access | Notes |
|---|---|---|---|
| **ReliefWeb API** (OCHA) | Situation reports, appeals, maps | Free REST | Excellent RAG corpus; cross-validates NDMA |
| **EM-DAT** (CRED) | Historical disaster impacts 1900– | Free registration | Ground truth for model validation |
| **IFRC GO** | DREF/appeal operations data | Free API | NGO-side operational view |
| **FIRMS** (NASA) | Active fire/thermal | Free API | Wildfire domain when reached |

### Cross-cutting source rules

1. **Archive raw, immutably, before parsing.** PMD's `latest.json` overwrite has already destroyed months of weather history that cannot be recovered. The cost of delay here is permanent.
2. **Prefer an API over a scrape** wherever both exist. Open-Meteo can backfill weather while the PMD scraper is rebuilt.
3. **Every source needs a declared fallback** and an automated freshness SLA.
4. **Respect robots.txt, rate-limit politely, identify honestly.** Replace the spoofed Chrome User-Agent with `PakistanOperationalRiskIntelligence/1.0 (+contact-url)`. These are public-service sites.
5. **Record licence and attribution per source in the database**, and surface attribution in the UI and API. ODbL (OSM) has share-alike obligations affecting what may be published — resolve before any geospatial launch.
6. **Government scraping is not the same as re-publication.** Before any public launch, obtain explicit written clarity on redistribution rights for NDMA/PDMA/PMD content.

---

# PART C — PHASED ROADMAP

Fourteen phases. Phases 0–4 are non-negotiable prerequisites. Phases 5–14 may be re-ordered once the foundation holds.

| Phase | Objective | Duration | Gate to exit |
|---|---|---|---|
| **0 — Audit & baseline** | Ground truth and a safety net before any change | 1 week | Verified restore from backup; baseline documented |
| **1 — Stabilise** | Green pipelines, honest failures, no silent loss | 2–3 weeks | 3 domain DAGs green 7 consecutive days; zero `InFailedSqlTransaction`; CI green |
| **2 — Geographic foundation** | One canonical geography; kill all five city maps | 3–4 weeks | ≥95% of observations resolve to a `station_id`; 100% of stations inside their claimed district |
| **3 — National source expansion** | Break out of Punjab; real national coverage and history | 4–6 weeks | ≥1 live source per province; ≥5 years national rainfall; PMD archive accumulating |
| **4 — Reliable ingestion & orchestration** | Airflow used as Airflow: incremental, data-aware | 3–4 weeks | Backfill and incremental produce identical results; broken source alerts within one interval |
| **5 — Data lake / lakehouse** | Distributed processing, at zero cost | 3–4 weeks | Full history in bronze; silver reconciles to Postgres; time travel demonstrated |
| **6 — Analytics warehouse** | Modelled, tested, documented analytics | 3–4 weeks | `dbt build` green; lineage graph renders; marts reconcile to source |
| **7 — Real-time / event-driven** | From "yesterday" to "now" | 3–4 weeks | Quake in DB within 60 s; one alert per breach, not N; consumer restart is lossless |
| **8 — Geospatial intelligence** | Geography as analysis, not lookup | 3–4 weeks | Tehsil risk surface renders <2 s; zonal stats reconcile to stations |
| **9 — ML forecasting & anomaly detection** | Prediction with honest error bars | 4–6 weeks | Every model beats its baseline; leakage-free backtests; calibrated intervals |
| **10 — RAG intelligence assistant** | Grounded, cited answers | 3–4 weeks | ≥90% citation accuracy; zero uncited factual claims; numeric questions route to SQL |
| **11 — Agentic operational intelligence** | Multi-step assistance, human always in the loop | 3–4 weeks | Full trace per action; no write access; approval enforced by the system |
| **12 — User-facing application** | Serve both audiences properly | 6–8 weeks | Any tehsil resolves to data or an honest "no coverage"; p95 <300 ms; mobile + Urdu |
| **13 — Observability & security** | Know it is healthy; prove it is safe | 3–4 weeks | Induced failure visible in <1 min; no secret anywhere; restore drill succeeds |
| **14 — CI/CD & production deployment** | Ship safely and repeatably | 3–4 weeks | Commit reaches staging with no manual step; failed migration rolls back cleanly |

Detailed per-phase deliverables, prerequisites, risks, validation criteria, learning goals and explicit "do NOT yet" boundaries are held in the working plan and will be expanded into per-phase ADRs as each phase begins.

### Phase-boundary principle

**Each phase has an explicit exit gate. No phase begins until the previous phase's gate is met.** The single most important gate is Phase 1's: three domain DAGs green for seven consecutive days. Everything downstream is built on data this pipeline produces, and is worthless if that data is wrong.

---

# PART D — CRITICAL ISSUES, RANKED

## P0 — data loss or platform down

| # | Issue | Location | Evidence |
|---|---|---|---|
| 1 | `parse_ndma` crashes on file 1 of 70 — NDMA dead 5 weeks | `parse_ndma.py:107` `copy2` | `PermissionError [Errno 1]`, 17/17 failures |
| 2 | `extract_pdma` crashes on page 1 — PDMA dead 5 weeks | `extract_pdma.py:91` debug write | `PermissionError [Errno 13]`, 7/7 failures |
| 3 | Application data lives in the Airflow metadata DB | `.env.docker`, `docker-compose.yml` | `\dt` shows app tables beside `dag`, `task_instance` |
| 4 | `load_ndma.py` TRUNCATEs all 4 NDMA tables every run | `load_ndma.py:453-469` | code |
| 5 | PMD overwrites `latest.json` at raw **and** parsed layers — history permanently destroyed | `extract_pmd.py:83`, `pmd/pipeline.py` | 1 file per category; 108 rows, one timestamp |
| 6 | One bad row aborts an entire load | all loaders, single `engine.begin()` | 2,016 `InFailedSqlTransaction` |
| 7 | Parsers drop records and still exit 0 → Airflow shows green | `parse_pdma.py:170-176` | 61 of 88 rainfall reports lost silently |
| 8 | DB password printed to stdout | `config/database.py:39`, `dashboard/db.py:52` | code; captured in task logs |
| 9 | Date strings passed to `DATE` columns | all loaders | 74/80 daily reports NULL date; `"12.07.2026"` → 7 Dec under MDY |

## P1 — correctness and trust

| # | Issue | Evidence |
|---|---|---|
| 10 | 46% of gauge water levels and 51% of danger levels are NULL | live query |
| 11 | River dimension corrupted — `1230DG KHAN 1230HILL TORRENTS`, `NULLAHS DATA SOURCE: F`, spaced duplicates | live query |
| 12 | `Stations` is the most frequent rainfall "station" (74 rows) | live query |
| 13 | 53% NDMA rejection because table extraction finds nothing on pages 2–11 | live log |
| 14 | Dashboard queries `pmd_weather` and `pipeline_logs` — neither exists; errors swallowed | code + `\dt` |
| 15 | `build_ndma_dataset` relief = 0 rows (dict-vs-list); `houses_total` always null | `relief.json` empty |
| 16 | Five conflicting city→province maps | code |
| 17 | Two competing DDL definitions for the same tables | 25 `UndefinedColumn` errors |
| 18 | `create_pdma_tables.py` is a mislabelled duplicate loader — and the README instructs running it | `diff` |
| 19 | `etl_pdma.py` ≡ `etl_pmd.py` | `diff` identical |
| 20 | No DDL orchestration | 82 `UndefinedTable` errors |
| 21 | `disaster_pipeline` blocks the DAGs it orchestrates | 5/5 failures |
| 22 | Zero tests, zero CI | filesystem |
| 23 | Every task success sends an email; SMTP is dead | `SMTPAuthenticationError` on every task |
| 24 | `requirements.txt` UTF-16 → `pip install -r` fails on Linux | hexdump |
| 25 | 67 downloaded images never parsed; 243 advisories/guidelines never parsed; earthquake reports never parsed | file counts |

## P2 — architecture and scale

26 No PostGIS · 27 No hierarchy below district, none at all for division/tehsil · 28 Rivers stored as points · 29 No station registry · 30 No Alembic · 31 N+1 query pattern in every loader · 32 Naive timestamps throughout · 33 No lineage columns · 34 Full reprocessing on every run · 35 Warehouse layer (1,648 lines) never executed, 3 files empty · 36 Glue/Redshift/Lambda inert and partly wrong · 37 12,398 dashboard lines with ~2,250 lines of duplicated CSS · 38 No map anywhere · 39 Unbounded dashboard queries on a 60 s refresh · 40 `days_ago()` start dates · 41 No `execution_timeout` · 42 Empty `metadata_logger.py` / `duplicate_checker.py`

## P3 — hygiene and debt

43 Duplicate function definitions in 3 files (last-wins) · 44 Debug prints producing 4,771 log files · 45 4,271 logging format-string errors · 46 `sensors/` dead code · 47 `setup_airflow.py` points at a non-existent DAG folder · 48 `.env.docker` tracked · 49 Unpinned `airflow_requirements.txt` · 50 Spoofed User-Agent, no robots.txt check · 51 README inaccuracies (claims idempotent loads, a pipeline logger, and camelot usage — none true) · 52 Orphaned `pakistan_disaster_pipeline` in Airflow metadata · 53 `docs/architecture.png` no longer matches reality

---

# PART E — OPEN QUESTIONS

Resolve before the phase named.

**Before Phase 1**

1. Is anything currently depending on the running Postgres container (a bookmarked dashboard, a shared link)? Affects how disruptive the database split can be.
2. Is `data/` (866 tracked files, growing) intended to stay in Git? Decide before it becomes unmanageable — Git LFS, exclusion, or deliberate acceptance.

**Before Phase 2**

3. Which admin-boundary source is authoritative — HDX COD-AB (P-codes, humanitarian standard) or GADM? Recommendation: HDX primary, GADM cross-check.
4. Are real coordinates obtainable for the 42 gauge and 161 rainfall stations? Without them, spatial analysis stays at district level. Is there a published or obtainable WAPDA/FFD/PMD station list?
5. **How should Indian-administered Kashmir localities in PMD data be modelled?** Recommendation: `control_status = 'external'`, retained but explicitly labelled. This requires an owner decision.
6. Do reliable division and tehsil boundaries exist for all provinces, or only some? Determines how deep the hierarchy can actually go.

**Before Phase 3**

7. Do PDMA Sindh/KP/Balochistan/GB/AJK publish machine-retrievable reports at all? Requires manual reconnaissance before connector work is scoped.
8. What is the monthly budget ceiling? The roadmap assumes near-zero; a €5–20/month VPS in Phase 14 is the only assumed spend.

**Before Phase 9**

9. How far back do NDMA/PDMA archives actually go? Determines whether ML is viable in Phase 9 or must wait for accumulated history.
10. What accuracy would make forecasts genuinely useful rather than merely present? Define the bar before building.

**Before Phase 12**

11. **Is there a right to republish scraped NDMA/PDMA/PMD content publicly?** Government publication is not automatically an open licence. Resolve in writing before any public launch.
12. Who are the first real institutional users, and what do they actually need?
13. Is Urdu localisation in scope for v1? Recommendation: yes — close to a requirement for genuine public reach in Pakistan.

**Cross-cutting**

14. What sustained weekly effort is realistic? The roadmap is ~50 weeks at a steady pace. Phases 0–4 are the mandatory foundation; 5–14 can be re-ordered or paused.
15. **Portfolio versus product.** If the primary goal is employment, prioritise Phases 5, 6, 9, 14 (Spark, dbt, ML, CI/CD). If it is a working public service, prioritise 2, 3, 8, 12 (geography, sources, maps, application). The roadmap serves both; the order should reflect which matters more.

---

## Reproducing the headline findings

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT dag_id, state, count(*) FROM dag_run GROUP BY 1,2 ORDER BY 1;"
```

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT count(*) total, count(*) FILTER (WHERE current_level_ft IS NULL) null_level, count(*) FILTER (WHERE report_datetime IS NULL) null_time FROM pdma_gauge_readings;"
```

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT river, count(*) FROM pdma_gauge_readings GROUP BY 1 ORDER BY 2 DESC;"
```
