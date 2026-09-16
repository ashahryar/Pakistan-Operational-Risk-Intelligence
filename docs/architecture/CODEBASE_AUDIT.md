# Codebase Audit — Pakistan Operational Risk Intelligence

**Task 16 (Phase 1 / ADR-0001). Audit only — no code was fixed, no files were rewritten, no database or AWS changes were made.**
Checkpoint audited: `2f7b217` (Task 15 complete). All 7 Airflow DAGs remain paused; none were unpaused or triggered during this audit.

Method: full read of every `.py` file in the repository (232 files inventoried), cross-referenced with `grep`/`Glob` to verify every claim of "used by X" or "file exists," real `pytest` runs (not assumed) for every test suite, a real `diff` for the suspected `etl_pdma.py`/`etl_pmd.py` duplicate, and direct inspection of DDL vs. loader column lists for every schema-mismatch claim. Five parallel research passes covered extraction/AWS, parsing/validation, database/loaders/warehouse, DAGs/pipeline utilities, and dashboard/tests/geo/forecasting/config respectively; several of their most load-bearing claims (password prints, the Glue duplicate, empty files, `TRUNCATE` removal, `DEFAULT_ARGS` non-use) were independently re-verified in this session before being written up here.

---

## Executive Summary

The picture Tasks 1–15 built is uneven but not surprising for a project this size: **the code paths that are actually wired into the three active DAGs (`ndma_dag`, `pdma_dag`, `pmd_dag`) and their three loaders are, on inspection, genuinely correct** — Task 6's five loader guarantees (no `TRUNCATE`, per-row transaction isolation, accurate insert/skip counts, `write_quarantine` on failure, rejection-ratio gate) are confirmed present in `load_ndma.py`, `load_pdma.py`, and `load_pmd.py`, and nowhere else. Task 5's parser-level quarantine/rejection-ratio gate is confirmed present in `parse_ndma.py`, `parse_pdma.py`, and (partially — see PMD findings) `pmd/pipeline.py`. The Task 8 golden-file test suite (112 tests) was independently checked against the parser source it targets and found to genuinely reflect current behavior, not stale or tautological assertions.

Outside that live path, the repository carries a large amount of **dead, duplicate, or actively broken code that no DAG ever touches**: two conflicting DDL definitions for the same warehouse table (`dim_station`), a byte-identical AWS Glue script masquerading as a separate PDMA job, two loaders (`load_ndma_v2.py`, `load_pdma_gauge_json.py`) that still `TRUNCATE` unconditionally and would in one case (`load_ndma_v2.py`) fail outright against the current schema, an entire `scripts/risk_engine/` and nine-file `scripts/warehouse/` package that has never been executed and whose column lists don't match its own DDL, and a mislabeled file (`create_pdma_tables.py`) that is actually an inferior duplicate loader, not DDL — exactly the kind of trap CLAUDE.md's own gotcha table warns about. None of this dead code is reachable from a paused-but-otherwise-normal DAG run, so it poses no live risk today, but it is a real hazard for whoever next tries to "clean up" or "consolidate" the warehouse/risk-engine layer without first reading this audit.

Two **credential-hygiene issues are real and live** (not hypothetical): `config/database.py:39` prints the full `DATABASE_URL` — including the plaintext database password — on every import, and `dashboard/db.py:52` does the same via `print("PASS =", password)`. Both fire on every DAG task run and every dashboard load respectively, meaning the password has been landing in Airflow task logs and Streamlit console output continuously. `aws/redshift/setup.py` additionally has a hardcoded plaintext admin password in source, though that script itself is confirmed dead code.

The dashboard has two live query bugs inherited from the original architecture assessment that are only **partially** fixed: `get_pmd_weather()` was fixed to query the real `pmd_daily_forecast` table, but `get_latest_weather()`/`get_weather_summary()` still query a `pmd_weather` table that exists nowhere in any DDL, and `get_dashboard_summary()` still queries a `pipeline_logs` table that is created by nothing. Both fail silently (`_read_sql()`'s blanket exception swallow, confirmed still present) rather than visibly — so the "Last Update" field and part of the weather KPI have been silently blank since before this audit, and will remain so after it, since no DAG or script writes to `pipeline_logs` anywhere in the current codebase.

The new Task 15 `scripts/acquisition/` code was **not** re-audited in depth here (already tested and verified end-to-end in Task 15's own report); this audit only confirms it is not wired into any DAG and does not duplicate the older `scripts/extraction/` code's source coverage (the closest overlap is PMD: `extract_pmd.py` hits `nwfc.pmd.gov.pk` while `acquire_ndmc_bulletins.py` hits `weather.gov.pk/ndmc` — different endpoints under the same parent organization).

**Coverage claim vs. reality**, traced end-to-end per source (full table in §9 below): only **NDMA, PDMA Punjab, and PMD** have a working (if imperfect) `EXTRACTION → RAW → PARSING → DQ → DB → DASHBOARD` path. **PDMA Sindh, PDMA KP, and PDMA Balochistan have no extraction, parsing, or loading code anywhere in the repository** — they are `NOT_IMPLEMENTED`, not partially built. SUPARCO/AQI Punjab/FFC have a working `EXTRACTION → RAW` path only (Task 15), with everything downstream of raw acquisition explicitly out of scope per Task 15's own instructions.

### Headline counts (from `docs/architecture/codebase_audit.csv`, 232 files inventoried)

| Status | Count |
|---|---:|
| CORRECT | 90 |
| CORRECT_WITH_MINOR_ISSUE | 30 |
| NEEDS_FIX | 19 |
| BROKEN | 7 |
| DEAD_UNUSED | 37 |
| DUPLICATE | 8 |
| NOT_IMPLEMENTED | 8 |
| (of which are `__init__.py`/package markers, correctly trivial) | 33 |

| Severity | Count |
|---|---:|
| CRITICAL | 3 |
| HIGH | 21 |
| MEDIUM | 30 |
| LOW | 59 |
| INFO | 86 |

---

## Folder-by-folder Audit

| Folder | Scripts | Correct | Minor Issue | Needs Fix | Broken | Dead/Duplicate |
|---|---:|---:|---:|---:|---:|---:|
| `scripts/extraction/` (+ `common/`) | 12 | 4 | 5 | 3 | 0 | 1 |
| `common/` | 1 | 0 | 0 | 0 | 0 | 1 |
| `aws/` | 13 | 1 | 0 | 0 | 1 | 11 |
| `scripts/parsing/` (+ `common/`, `pmd/`) | 23 | 9 | 11 | 0 | 0 | 3 |
| `validation/` | 17 | 10 | 4 | 0 | 0 | 3 |
| `scripts/database/` | 15 | 8 | 0 | 1 | 3 | 1 |
| `scripts/risk_engine/` | 2 | 0 | 0 | 0 | 1 | 1 |
| `scripts/warehouse/` | 17 | 3 | 0 | 6 | 1 | 6 (+1 not_impl overlaps) |
| `pipeline/dags/` | 8 | 4 | 3 | 0 | 1 | 0 |
| `pipeline/config/` | 3 | 2 | 1 | 0 | 0 | 1 (overlap) |
| `pipeline/helpers/` | 6 | 4 | 0 | 0 | 0 | 2 |
| `pipeline/sensors/` | 4 | 1 | 0 | 0 | 0 | 3 |
| `pipeline/utils/` | 13 | 3 | 1 | 2 | 0 | 7 |
| `dashboard/` | 31 | 20 | 10 | 0 | 1 | 1 |
| `scripts/geo/`, `scripts/forecasting/`, `scripts/audit/` | 10 | 8 | 1 | 0 | 0 | 1 |
| `config/` | 8 | 6 | 1 | 0 | 0 | 1 |
| `scripts/acquisition/` (Task 15) | 11 | 11 | 0 | 0 | 0 | 0 |
| `tests/` (all suites incl. `tests/architecture/`) | 33 | 32 | 1 | 0 | 0 | 0 |

(Row totals in this table are counted per the CSV's `status` column and will not sum exactly to folder file counts where a folder mixes package-marker `__init__.py` files, which are always `CORRECT`/`INFO` and are folded into the "Correct" column above.)

---

## Script-level Findings

The full, file-by-file inventory (232 files) with `used_by`/`input`/`output`/`database_dependency`/`test_coverage`/`recommended_action` for every single file is the machine-readable `docs/architecture/codebase_audit.csv` — this is the authoritative source the section tables below are drawn from and condensed for readability. A representative excerpt (the highest-severity rows across the whole repository, not filtered to any one subsystem):

| File | Purpose | Used By | Status | Severity | Finding |
|---|---|---|---|---|---|
| `dashboard/db.py` | All dashboard SQL access + `_read_sql` wrapper | every dashboard page/section | NEEDS_FIX | CRITICAL | Password printed at line 52; swallow-all-exceptions in `_read_sql`; two queries reference tables (`pmd_weather`, `pipeline_logs`) that exist in no DDL |
| `scripts/database/load_ndma_v2.py` | Alternate NDMA loader | not referenced by any DAG | BROKEN | CRITICAL | Unconditional `TRUNCATE`; single whole-load transaction; INSERT columns don't match current DDL at all |
| `scripts/database/load_pdma_gauge_json.py` | Alternate PDMA gauge loader | not referenced by any DAG | BROKEN | CRITICAL | Same `TRUNCATE` + single-transaction anti-pattern, no quarantine, no gate |
| `config/database.py` | Builds DB engine from env | nearly every DB-touching script | NEEDS_FIX | HIGH | `print(DATABASE_URL)` leaks the DB password on every import |
| `scripts/database/create_pdma_tables.py` | Mislabeled — actually an old PDMA loader, not DDL | not DAG-referenced | BROKEN | HIGH | Inferior dead duplicate of `load_pdma.py` under a misleading DDL filename |
| `scripts/database/create_risk_tables.py` | DDL for `operational_risk` | hand-run only | NEEDS_FIX | HIGH | Column list doesn't match what `risk_engine.py` actually inserts |
| `scripts/risk_engine/risk_engine.py` | Computes per-city operational risk | confirmed never executed | BROKEN | HIGH | Schema mismatch vs. its own DDL; per-city queries have no WHERE clause (every city gets identical values) |
| `scripts/warehouse/create_dim_station.py` / `create_station_dimension.py` | Conflicting `dim_station` DDL | not DAG-invoked | DUPLICATE | HIGH | Two scripts define incompatible schemas for the same table name |
| `aws/glue/scripts/etl_pdma.py` | Nominally PDMA Glue ETL | unreferenced (Glue commented out) | DUPLICATE | HIGH | Byte-identical to `etl_pmd.py` (confirmed via `diff`) — no real PDMA logic exists |
| `aws/redshift/setup.py` | Provisions Redshift Serverless | unreferenced | BROKEN | HIGH | Hardcoded plaintext admin password in committed source |
| `pipeline/dags/disaster_pipeline.py` | Triggers ndma/pdma/pmd with `wait_for_completion=True` | Airflow scheduler (paused) | NEEDS_FIX | HIGH | Collides with those DAGs' own independent overlapping schedules — deadlock/stall risk once unpaused |
| `validation/rules.py` | Shared field validators | `validation/validator.py` | NEEDS_FIX | HIGH | `valid_temperature`/`valid_humidity`/`valid_city`/`valid_forecast` each defined twice; first silently dead |
| `validation/translator.py` | Urdu→English city translation | `pmd/daily_parser.py` (`normalize_city` only) | NEEDS_FIX | HIGH | `normalize_city` defined twice; live version is not None-safe |
| `validation/pmd/{schema,completeness,score}.py` | PMD schema/completeness/quality gates | never imported by production code | DEAD_UNUSED | HIGH | Fully written but never wired into `pmd/pipeline.py` — PMD has no DQ gate unlike NDMA/PDMA |
| `pipeline/utils/duplicate_checker.py`, `metadata_logger.py` | (presumed dedup/metadata logging) | n/a | NOT_IMPLEMENTED | HIGH | Still empty files (0 bytes), unchanged from the original architecture assessment |
| `scripts/warehouse/load_dim_station.py` | Loads `dim_station` | not DAG-invoked | BROKEN | HIGH | `TRUNCATE`; hardcodes `province_key=1` for every station with no existence check |

The remaining 216 rows, spanning every folder listed in Task 16's scope, are in the CSV with the same column shape.

## Extraction Audit

| File | Purpose | Used By | Status | Severity | Finding |
|---|---|---|---|---|---|
| `scripts/extraction/extract_ndma.py` | Scrapes NDMA sitreps/advisories/guidelines PDFs | `ndma_dag.py`, `weekly_dag.py`, `manual_dag.py` | NEEDS_FIX | HIGH | No HTTP status check before parsing `response.text`; no checksum; non-atomic PDF writes |
| `scripts/extraction/extract_pdma.py` | Scrapes PDMA Punjab daily/rainfall/gauge/earthquake reports | `pdma_dag.py`, `weekly_dag.py`, `manual_dag.py` | NEEDS_FIX | HIGH | Same gaps as `extract_ndma.py`; hardcoded `YEARS=[2026,2025]` goes stale after 2026 |
| `scripts/extraction/extract_pmd.py` | Scrapes PMD daily/weekly/alerts | `pmd_dag.py`, `weekly_dag.py`, `manual_dag.py` | CORRECT_WITH_MINOR_ISSUE | MEDIUM | Only extractor with a real status-code check; overwrites `latest.json` unconditionally, no checksum |
| `scripts/extraction/common/downloader.py` | Generic file downloader | `extract_ndma.py`, `extract_pdma.py` | NEEDS_FIX | HIGH | No size/checksum verification; non-atomic write can leave a truncated PDF marked successful |
| `scripts/extraction/common/fetcher.py` | Shared HTTP client + retry | `downloader.py`, all 3 extractors | NEEDS_FIX | MEDIUM | 3 retries, flat 2s sleep, no backoff; no HTML-error-page detection |
| `scripts/extraction/common/filesystem.py` | Raw storage path builder | all 3 extractors | CORRECT_WITH_MINOR_ISSUE | LOW | Older convention (`data/raw/<source>/reports/<type>/<year>/`) now coexists with Task 15's `data/raw/<org>/<dataset>/<date>/` |
| `scripts/extraction/common/pmd_parser.py` | PMD forecast text/table extraction | `extract_pmd.py` | CORRECT | INFO | `extract_structured_weather()` defined but never called (dead function) |
| `scripts/extraction/common/utils.py` | (empty) | none | DEAD_UNUSED | LOW | Empty file, unreferenced |
| `common/logger.py` | Project-wide logger | not imported by anything in scope | DEAD_UNUSED | LOW | Duplicate/overlapping with `scripts/extraction/common/logger.py`, which is the one actually used |
| `aws/glue/scripts/etl_pdma.py` | Nominally PDMA Glue ETL | unreferenced (Glue commented out of every DAG) | DUPLICATE | HIGH | **Confirmed via real `diff`: byte-identical to `etl_pmd.py`.** No PDMA Glue logic exists anywhere in the repo |
| `aws/redshift/setup.py` | Provisions Redshift Serverless | unreferenced | BROKEN | HIGH | Hardcoded plaintext password `ADMIN_PASS = "Admin1234!"` in source |

Full 26-file table (including `aws/s3/`, `aws/lambda/`) is in `codebase_audit.csv`. **Every AWS Glue/Redshift/Lambda task instantiation is confirmed commented out of all 7 DAGs** — matches CLAUDE.md rule 11 exactly, confirmed by grep, not assumed.

---

## Parser Audit

Every parser's declared input path was checked against real files on disk — **none reads a nonexistent input.** `pytest tests/parsers/` was actually run: **112 passed, 0 failed** (71.97s), and the assertions were traced back to parser source to confirm they reflect current, not stale, behavior.

| Parser | Source | Input | Output | Tests | Status | Findings |
|---|---|---|---|---|---|---|
| `parse_ndma.py` | NDMA | `data/raw/ndma/reports/sitreps/all/pdfs/*.pdf` (85 files, exists) | `data/parsed/ndma/sitreps/*.json` | 5/5 golden | CORRECT | Fully Task-5-compliant: quarantine + rejection-ratio gate + per-file exception isolation |
| `parse_pdma_daily.py` | PDMA daily | `daily_reports/<year>/pdfs/*.pdf` | dict (report_date/temperature/rainfall/dams) | 5/5 golden | CORRECT_WITH_MINOR_ISSUE | `report_date` stays a raw string; `KNOWN_DAMS` is a fixed 7-item list; unmapped dam status defaults to the string `"Unknown"` |
| `parse_rainfall.py` | PDMA rainfall | `rainfall_reports/<year>/pdfs/*.pdf` | dict (stations: [{station, rainfall_mm}]) | 5/5 golden | NEEDS_FIX | Production `print()` debug dumps; `parse_numeric()` not None-safe (raises `TypeError`); no "T"/trace handling — silently dropped, uncounted; dedup by station name is last-wins |
| `parse_gauge.py` | PDMA gauge | `gauge_reports/<year>/pdfs/*.pdf` | dict (gauges: [{station, river, current_level_ft, ...}]) | 5/5 golden + type-coercion (`dayfirst=True` confirmed) | CORRECT_WITH_MINOR_ISSUE | Hardcoded column indices `row[3]/row[6]/row[9]/row[11]` with only a `len(row)>=12` guard, no header verification |
| `pmd/daily_parser.py`, `weekly_parser.py`, `alerts_parser.py` | PMD | `data/raw/pmd/reports/{daily_forecast,weekly_outlook,weather_alerts}/all/latest.json` (all exist) | dicts per PMD domain | 6/6 golden combined | CORRECT_WITH_MINOR_ISSUE | daily/weekly correctly quarantine `row_too_short`/`failed_weather_validation`; all three do bare `raw["category"]`/`raw["scraped_at"]` indexing (`KeyError` crash risk on malformed input) |
| `pmd/pipeline.py` | PMD orchestrator | delegates | `data/parsed/pmd/*/latest.json` | via above | CORRECT_WITH_MINOR_ISSUE | **Never calls `validation.pmd.*`** — PMD has no pipeline-level schema/quality gate, unlike NDMA/PDMA (see `validation/pmd/*` below) |
| `scripts/parsing/common/ndma_parser.py` | NDMA | — | — | none | **DUPLICATE** | Byte-for-byte duplicate of functions already in `ndma_information_extractor.py` (which is the one actually imported by `parse_ndma.py`); dead |
| `validation/rules.py` | shared | field value | bool | type-coercion (live def only) | **NEEDS_FIX** | `valid_temperature`/`valid_humidity`/`valid_city`/`valid_forecast` each **defined twice** in the same file — first (pandas-based) definition is silently shadowed and dead |
| `validation/translator.py` | shared | raw city text | normalized city | type-coercion (live def only) | **NEEDS_FIX** | `normalize_city` **defined twice** — a dict-returning, None-safe version is shadowed by a str-returning, non-None-safe version; several literal duplicate keys in `CITY_TRANSLATIONS` |
| `validation/pmd/{schema,completeness,score}.py` | PMD | — | — | none — never imported by production code | **DEAD_UNUSED** | Fully written but never wired into `pmd/pipeline.py`; confirms PMD's DQ-gate gap above |

Full 66-file table (including `scripts/parsing/common/`, all of `validation/`) is in `codebase_audit.csv`.

---

## Database/Loader Audit

Task 6's five guarantees (no `TRUNCATE`, per-row `engine.begin()` isolation, accurate `rowcount`-based counts, `write_quarantine` on failure, `sys.exit(1)` rejection-ratio gate) were checked against actual code, not assumed — **confirmed fully present, and only present, in the three loaders the DAGs actually run**: `load_ndma.py`, `load_pdma.py`, `load_pmd.py`. (The one `TRUNCATE` grep hit in `load_ndma.py` is a documenting *comment* about its removal, not a live SQL statement — verified directly.)

| File | Source Input | Target Table | Status | Severity | Finding |
|---|---|---|---|---|---|
| `load_ndma.py` | `data/parsed/ndma/sitreps/*.json` | `ndma_casualties/damage/relief/rescue` | CORRECT | INFO | All 5 Task-6 guarantees verified present |
| `load_pdma.py` | `data/parsed/pdma/{daily,rainfall,gauge}/*.json` | `pdma_daily_reports`/`rainfall_readings`/`gauge_readings` | CORRECT | INFO | All 5 guarantees present; `ON CONFLICT DO NOTHING` + real `rowcount` counts |
| `load_pmd.py` | `data/parsed/pmd/*/latest.json` | `pmd_daily_forecast`/`weekly_outlook`/`weather_alerts` | CORRECT | INFO | All 5 guarantees present |
| `create_pdma_tables.py` | (mislabeled) | `pdma_*` | **BROKEN** | HIGH | **Verified by reading the file: it is actually an old PDMA JSON *loader*, not DDL**, not DAG-referenced, one big transaction per file, no quarantine, no rejection gate — an inferior, dead duplicate of `load_pdma.py` sitting under a misleading DDL-sounding filename |
| `load_ndma_v2.py` | `data/parsed/ndma/sitreps/*.json` | `ndma_casualties/damage/relief/rescue` | **BROKEN** | CRITICAL | Unconditional `TRUNCATE ... CASCADE`; one transaction for the whole load; **INSERT column lists (`source_file`, `district`, ...) do not match `create_tables.py`'s actual DDL at all — cannot run successfully against the current schema.** Not DAG-referenced |
| `load_pdma_gauge_json.py` | `data/parsed/pdma/gauge/**/*.json` | `pdma_gauge_readings` | **BROKEN** | CRITICAL | Same unconditional-`TRUNCATE` + single-transaction anti-pattern; no quarantine, no gate. Not DAG-referenced |
| `create_risk_tables.py` | — | `operational_risk` | NEEDS_FIX | HIGH | DDL column list does not match what `risk_engine.py`'s INSERT actually writes — verified by direct comparison |
| `scripts/risk_engine/risk_engine.py` | 5 source tables | `operational_risk` | **BROKEN** | HIGH | Confirmed still never executed (original baseline claim still holds); `TRUNCATE` in one transaction; column mismatch vs. its own DDL; per-city queries have no `WHERE` clause so every city gets identical computed values |
| `create_dim_station.py` / `create_station_dimension.py` | — | `dim_station` | **DUPLICATE** | HIGH | **Two DDL scripts define conflicting schemas for the same table name** (`province TEXT` vs. `province_key INTEGER FK`) — whichever runs first on a fresh DB silently wins |
| `config/database.py` | — | — | NEEDS_FIX | **HIGH** | `print(DATABASE_URL)` at line 39 leaks the DB password in plaintext on every import — confirmed live via grep |
| `pipeline/utils/quarantine.py` | — | `dq.quarantine` | CORRECT | INFO | Non-raising, correctly isolated per-call transaction — the mechanism the 3 live loaders correctly call |

Nine of `scripts/warehouse/`'s 17 files still `TRUNCATE`/`DELETE`-then-reload in a single transaction with silent `INNER JOIN` row drops — confirmed still never invoked by any DAG (matches the "never executed" original baseline). Full 40-file table in `codebase_audit.csv`.

---

## DAG Audit

**No DAG references a script that doesn't exist on disk** — every `run_script(...)` target across all 7 DAGs was verified present. This is the specific historical failure class Task 16 asked to re-check for, and it does **not** currently reproduce.

| DAG | Tasks | Status | Severity | Finding |
|---|---|---|---|---|
| `backfill_dag.py` | reparse→reload→upload (×3 domains) | CORRECT_WITH_MINOR_ISSUE | MEDIUM | `s3` task calls `aws_helper.upload_all` directly, bypassing its own dead local wrapper `upload_all_s3()`; no `execution_timeout`; deprecated `days_ago(1)` |
| `disaster_pipeline.py` | triggers ndma/pdma/pmd DAGs, `wait_for_completion=True` | **NEEDS_FIX** | **HIGH** | Confirms the historically-dangerous pattern is still present: `pdma_pipeline`/`pmd_pipeline` retain independent overlapping `0 */6 * * *` schedules with `max_active_runs=1` while also being triggered-and-waited-on by this DAG — real deadlock/stall risk once unpaused. No `execution_timeout` anywhere in the chain |
| `manual_dag.py` | source-conditional extract/parse/load/upload | CORRECT | LOW | Linear, all 10 referenced scripts verified present, no `scripts/acquisition/` reference |
| `ndma_dag.py` | extract→parse→build→load→upload | CORRECT | LOW | Clean linear chain, all scripts verified present |
| `pdma_dag.py` | extract→parse→load→upload | **BROKEN** (latent) | MEDIUM | `glue_etl()` calls `start_glue_job`/`GLUE_JOB`, both of which are **commented-out imports/constants** — would raise `NameError` the moment anyone uncomments the Glue `PythonOperator` without also fixing the imports. Currently unreachable/harmless only because the task itself is never instantiated |
| `pmd_dag.py` | extract→validate→load→upload | CORRECT | LOW | Linear, sane, all scripts verified present |
| `weekly_dag.py` | extract-all→parse-all→load→upload | CORRECT_WITH_MINOR_ISSUE | MEDIUM | Wires in **no** `on_success_callback`/`on_failure_callback` at all — the only DAG of the 7 that doesn't — so failures here get no email/Slack notification |

**All 7 DAGs use the deprecated `airflow.utils.dates.days_ago(1)` for `start_date`.** **None reference `scripts/acquisition/`** — Task 15 is confirmed not wired into any DAG, as intended. `pipeline/config/default_args.py` (which defines a shared `DEFAULT_ARGS` including `execution_timeout=2h`) is imported by **zero** of the 7 DAGs — confirmed by grep — which is the direct reason none of them has a task timeout today, despite the file existing specifically to provide one.

`pipeline/utils/task_callbacks.py`: the Task 3 "remove email-on-success" fix is **confirmed present at the per-task level** (`task_success()` no longer emails) but **not at the DAG level** — `dag_success()` (used by `backfill_dag.py` and `disaster_pipeline.py`) still calls `send_email(...)`, so a full-run success still emails once per run.

Full DAG + pipeline-utilities tables (39 files) are in `codebase_audit.csv`.

---

## Dashboard Audit

`pytest tests/dashboard/` actually run: **5/5 pass**, genuinely exercising real (non-mocked) `geo_helpers.py` logic — this is the **only** dashboard file with any test coverage; `db.py`, despite carrying this audit's most severe findings, has zero test coverage.

| File | Purpose | Status | Severity | Finding |
|---|---|---|---|---|
| `dashboard/db.py` | All SQL access + `_read_sql` wrapper | **NEEDS_FIX** | **CRITICAL** | (1) `print("PASS =", password)` at line 52 — confirmed live. (2) `_read_sql()` swallows *all* exceptions and returns an empty DataFrame — confirmed still present, so a broken query and "no data" remain indistinguishable everywhere. (3) `get_latest_weather()`/`get_weather_summary()` still query `pmd_weather`, which is defined in **no** DDL script anywhere in the repo. (4) `get_dashboard_summary()` still queries `pipeline_logs`, created by nothing |
| `dashboard/components/alerts.py` | Platform-health banner | CORRECT_WITH_MINOR_ISSUE | MEDIUM | Health score is a hardcoded binary 100/60 keyed only on `last_update is None` — since `pipeline_logs` doesn't exist, `last_update` is *always* `None`, so this banner permanently shows "degraded" regardless of true pipeline state |
| `dashboard/pages/{1..5}_*.py` (5 files) | Standalone per-domain pages | CORRECT_WITH_MINOR_ISSUE | MEDIUM | Each carries its **own, independent, non-shared CSS design-token block** (`--cs-*`, `--im-*`, `--ob-*`, ...) — the 5 pages alone total 9,762 lines, none of them importing `dashboard/styles/theme.py`, which only `Home.py` actually uses |
| `dashboard/utils/geo_helpers.py` | Geo-observation reshaping | CORRECT | INFO | Correctly consumes the already-resolved `geo.resolved_observation_counts` view output; no separate hardcoded province map found here (the one genuinely new-geo-foundation-integrated file in the dashboard) |
| `dashboard/utils/helpers.py` vs. `dashboard/sections/hydrology.py` | River-risk classification | DUPLICATE | LOW | `hydrology.py` reimplements its own `classify_status()` identical to `helpers.py::classify_river_risk()` instead of importing it |

No SQL-injection risk found — every query is built from internal constants, never from raw user input; the generic `execute_query()`/`run_query()` pass-throughs exist but are never called with user-supplied SQL by any current caller. Full 31-file table in `codebase_audit.csv`.

---

## End-to-End Compatibility

`EXTRACTION → RAW → PARSING → DQ → DB → DASHBOARD`, traced against real code and real files on disk (not assumed):

| Source | Status | Notes |
|---|---|---|
| **NDMA** | **WORKING** (with known gaps) | Full chain live: `extract_ndma.py` → `data/raw/ndma/...` → `parse_ndma.py` (quarantine + gate) → `load_ndma.py` (all 5 Task-6 guarantees) → `ndma_casualties/damage/relief/rescue` → dashboard pages 1–2. Gaps: extractor has no status-code/checksum guard; 243 NDMA advisories/guidelines PDFs already downloaded have no parser at all. |
| **PDMA Punjab** | **WORKING** (with known gaps) | Full chain live for daily/rainfall/gauge. Gaps: `parse_rainfall.py` has production debug prints and no trace-value handling; `parse_gauge.py` uses brittle positional column indices; NDMC earthquake reports folder has zero PDFs and no parser exists for it. |
| **PDMA Sindh** | **NOT_IMPLEMENTED** | No extraction, parsing, or loading code anywhere in the repository for this province. Confirmed by grep — zero matches for "sindh" outside documentation/planning files. |
| **PDMA KP** | **NOT_IMPLEMENTED** | Same as Sindh — no code exists. |
| **PDMA Balochistan** | **NOT_IMPLEMENTED** | Same as Sindh — no code exists. |
| **PMD** | **PARTIAL** | Full chain live for daily/weekly/alerts, but `pmd/pipeline.py` never calls `validation.pmd.*` (dead DQ module) — PMD output is only row-level structurally validated, never schema/quality-scored like NDMA/PDMA. `latest.json` is overwritten every run with no per-date archive (self-documented known gap in the Task 8 test suite itself). |
| **SUPARCO DisasterWatch** | **PARTIAL** (by design) | `EXTRACTION → RAW` only, via Task 15's `scripts/acquisition/acquire_suparco_disasterwatch.py`. No parsing/DQ/DB/dashboard integration exists — explicitly out of scope per Task 15's own instructions, not a gap in this audit's sense. |
| **EPA Punjab AQI** | **PARTIAL** (by design) | Same as SUPARCO — `EXTRACTION → RAW` only via `acquire_aqi_punjab.py`. |
| **FFC** | **PARTIAL** (by design) | Same as SUPARCO — `EXTRACTION → RAW` only via `acquire_ffc.py`, homepage + DFSR/GLOF archive + controlled PDF batch. |

---

## Critical Issues

Evidence-backed, all independently re-verified in this session (not merely repeated from an agent's claim):

1. **`config/database.py:39`** — `print(DATABASE_URL)` prints the live database password in plaintext on every import of this near-universally-imported module. Confirmed via grep.
2. **`dashboard/db.py:52`** — `print("PASS =", password)` prints the live database password in plaintext on every dashboard load. Confirmed via grep.
3. **`dashboard/db.py`'s `_read_sql()`** swallows every exception, so `get_latest_weather()`/`get_weather_summary()` (querying the nonexistent `pmd_weather` table) and `get_dashboard_summary()` (querying the nonexistent `pipeline_logs` table) fail silently rather than visibly — confirmed both tables absent from every DDL script in `scripts/database/`.
4. **`load_ndma_v2.py`** would raise `UndefinedColumn` if ever run — its INSERT column lists were directly compared against `create_tables.py`'s actual DDL and do not match at all. Not DAG-referenced today, so this is latent, not live.
5. **`scripts/database/create_pdma_tables.py`** is not DDL at all — reading the file confirms it is an old PDMA loader under a misleading filename, exactly the trap CLAUDE.md's gotcha table warns readers about ("Running it as the README instructs re-runs a legacy loader").
6. **`aws/redshift/setup.py`** has a hardcoded plaintext admin password in committed source — dead code today, but a real secret-hygiene defect regardless of whether it ever runs.
7. **`pipeline/dags/disaster_pipeline.py`**'s `wait_for_completion=True` triggers of `pdma_pipeline`/`pmd_pipeline` collide with those DAGs' own independent, overlapping `0 */6 * * *` schedules — a real deadlock/stall risk that would resurface the moment any of these DAGs is unpaused, exactly the pattern the original architecture assessment flagged.

## Minor Issues

Representative, non-exhaustive (full list in `codebase_audit.csv`):

- `scripts/parsing/parse_rainfall.py` and `scripts/parsing/common/pdf_table_reader.py` both contain leftover production `print()` debug dumps.
- `validation/rules.py` and `validation/translator.py` each silently shadow a function definition with a second, behaviorally-different one in the same file — currently tested-correct via the live (second) definition, but a real footgun for future edits.
- `scripts/parsing/pmd/utils.py`'s city→province/district table and `validation/translator.py`'s richer table are two independently-maintained, divergent sources of truth actually in simultaneous live use for different fields of the same PMD record.
- Five `dashboard/pages/*.py` files carry four separate, non-shared inline CSS design-token systems instead of the one real design system (`dashboard/styles/theme.py`) that only `Home.py` uses.
- `dashboard/components/alerts.py`'s platform-health banner is permanently stuck at "degraded" because of the `pipeline_logs` gap above.
- `pipeline/utils/script_runner.py` and `pipeline/helpers/script_runner.py` are two genuinely divergent (not byte-identical) implementations of the same function; only the `helpers/` copy is ever imported by a DAG.
- All 7 DAGs use the deprecated `airflow.utils.dates.days_ago(1)` start-date pattern.

## Dead/Duplicate Code

(List only — nothing here was deleted or modified.)

- **Duplicate**: `aws/glue/scripts/etl_pdma.py` ≡ `aws/glue/scripts/etl_pmd.py` (byte-identical, confirmed via `diff`).
- **Duplicate**: `scripts/warehouse/create_dim_station.py` vs. `create_station_dimension.py` — two conflicting DDL definitions of the same table.
- **Duplicate**: `scripts/parsing/common/ndma_parser.py` — exact duplicate of functions in `ndma_information_extractor.py`, the one actually imported.
- **Duplicate**: `pipeline/utils/script_runner.py` vs. `pipeline/helpers/script_runner.py` — divergent, only the latter used.
- **Duplicate**: `scripts/warehouse/load_fact_ndma.py` overlaps `load_fact_ndma_casualties.py` + `load_fact_ndma_damage.py` — three files, two different FK-handling strategies, for the same two fact tables.
- **Dead**: entire `scripts/risk_engine/` package (confirmed still never executed, matches original baseline) and 14 of `scripts/warehouse/`'s 17 files (confirmed no DAG references any of them).
- **Dead**: `pipeline/sensors/*` (all 3 sensor files, confirmed by grep still imported by nothing).
- **Dead**: `pipeline/utils/metadata_logger.py` and `pipeline/utils/duplicate_checker.py` are still empty files (0 bytes), matching the original architecture assessment finding unchanged.
- **Dead**: 11 of 13 files under `aws/` (everything except `pmd_parser.py`-adjacent extraction code, which is separate) — confirmed unreferenced by any active DAG, consistent with CLAUDE.md rule 11.
- **Dead**: `validation/pmd/{schema,completeness,score}.py` — fully written, never imported by production code.
- **Dead**: `scripts/parsing/test_cleaner.py`, `test_pdf.py`, `test_tables.py` — manual print-scripts with the `test_` filename prefix but zero real `test_*` functions; would collect 0 tests under pytest.

---

## Recommended Fix Order

Order only — no implementation in this task.

1. **Remove the two live password `print()` statements** (`config/database.py:39`, `dashboard/db.py:52`) — zero-risk, one-line-each, highest-value fix available.
2. **Fix or remove `dashboard/db.py`'s two nonexistent-table queries** (`pmd_weather`, `pipeline_logs`) and give `_read_sql()` a way to distinguish "query failed" from "table is empty."
3. **Resolve the `disaster_pipeline.py` schedule-collision risk** before any DAG is ever unpaused.
4. **Delete or clearly quarantine the three broken/dangerous loaders** (`load_ndma_v2.py`, `load_pdma_gauge_json.py`, the loader hiding inside `create_pdma_tables.py`) so no one runs them by mistake, and rename `create_pdma_tables.py` to stop it looking like DDL.
5. **Resolve the `dim_station` DDL conflict** before `scripts/warehouse/` is ever reactivated.
6. **Wire `validation.pmd.*` into `pmd/pipeline.py`** for DQ parity with NDMA/PDMA.
7. **Remove the dead first definitions in `validation/rules.py` and `validation/translator.py`** so a future edit can't accidentally target the wrong (dead) copy.
8. **Consolidate the divergent PMD city→province/district tables** (`scripts/parsing/pmd/utils.py` vs. `validation/translator.py`).
9. Lower-priority hygiene: remove leftover `print()` debug dumps, delete confirmed-dead duplicate files (`ndma_parser.py`, one of the two `script_runner.py` copies, `etl_pdma.py`), consolidate dashboard page CSS onto `theme.py`, add `execution_timeout` via `pipeline/config/default_args.py` across all 7 DAGs.
10. New scope (not a fix, a gap): PDMA Sindh/KP/Balochistan have no code at all — building them is new-feature work, correctly out of Phase 1's scope per CLAUDE.md rule 9.
