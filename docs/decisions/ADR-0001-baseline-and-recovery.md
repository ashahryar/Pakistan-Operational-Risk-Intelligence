# ADR-0001 — Baseline and Recovery

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-02 |
| **Deciders** | Project owner |
| **Phase** | 0 — Audit and baseline |
| **Supersedes** | Nothing. First ADR. |
| **Superseded by** | — |
| **Related** | [`../assessment/ARCHITECTURE_ASSESSMENT.md`](../assessment/ARCHITECTURE_ASSESSMENT.md) · [`../DATA_QUALITY_BASELINE.md`](../DATA_QUALITY_BASELINE.md) · [`../../CLAUDE.md`](../../CLAUDE.md) |

---

## Context

The Pakistan Operational Risk Intelligence Platform is being evolved from a working prototype into a national operational-risk intelligence platform, serving both institutional users (NDMA/PDMA, NGOs, emergency operations teams, researchers, infrastructure and insurance risk teams) and general public users who need to understand conditions in their own district or tehsil.

A full read-only technical assessment was carried out on 2026-09-01 against branch `project-redesign-baseline` @ `d452c3b`. It read all 168 tracked source files, queried the running PostgreSQL container read-only, and aggregated 4,771 Airflow task logs.

**The assessment found that the platform is not currently running.** 38 of 39 DAG runs have failed; there has been exactly one success in the platform's history. NDMA data is 35 days stale, PDMA 32 days, PMD 20 days. Roughly half of all river-gauge measurements in the database are NULL, and the river dimension contains PDF artefacts stored as real entities.

This ADR records the state of the system at that moment, the decisions taken before any remediation begins, and the principle that governs the order of work. It exists so that a future reader — including a future version of the project owner — can reconstruct **why** the next several months of work were sequenced the way they were.

No code, schema, container or cloud resource was modified in Phase 0.

---

## 1. Current architecture (as built, 2026-09-01)

### Data flow

```
Government sources (no APIs published — all scraped)
  NDMA ndma.gov.pk · PDMA Punjab pdma.punjab.gov.pk · PMD pmd.gov.pk + nwfc.pmd.gov.pk
                                   │
                          Extraction (requests + BeautifulSoup)
                          → data/raw/{ndma,pdma,pmd}/  (733 PDFs, 69 images, 16 JSON)
                                   │
                          Parsing (pdfplumber, PyMuPDF)
                          → data/parsed/  +  data/analytics/  +  data/rejected/
                                   │
                          Validation (schema / completeness / quality score)
                                   │
                          Loading (SQLAlchemy Core, raw SQL)
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
        PostgreSQL 15                      Amazon S3
        database "airflow"                 raw/ parsed/ analytics/
        (see §1.2 — this is a defect)      (HEAD-check idempotency)
                    │                             │
                    ▼                             ╎ commented out of every DAG:
        Streamlit dashboard                       ╎ Lambda → Glue → Redshift
        (12,398 lines, 6 pages)                   ╎
```

### 1.1 Orchestration

Apache Airflow 2.9.3, `LocalExecutor`, in Docker Compose alongside PostgreSQL 15. Seven DAGs:

| DAG | Schedule | Status |
|---|---|---|
| `ndma_pipeline` | daily `0 5 * * *` | failing 17/17 at `parse_ndma` |
| `pdma_pipeline` | 6-hourly `0 */6 * * *` | failing 7/7 at `extract_pdma` |
| `pmd_pipeline` | 6-hourly `0 */6 * * *` | failing 5/6 at `load_postgres` |
| `disaster_pipeline` | 6-hourly, master | failing 5/5; blocks the DAGs it orchestrates |
| `weekly_full_pipeline` | weekly | failing |
| `backfill_pipeline` | manual | failing |
| `manual_pipeline` | manual | failing |

Every DAG task shells out to a standalone script via `subprocess` (`pipeline/helpers/script_runner.py`). Airflow is functioning as cron: no XCom, no Datasets, no incremental processing, no partitioning, no `execution_timeout`, no data-aware scheduling.

### 1.2 Storage — the defining structural defect

**Application data lives inside the Airflow metadata database.** `.env.docker` sets `DB_NAME=airflow`, `DB_USER=airflow` — the same database and superuser as `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`.

`\dt` returns 54 tables: 42 Airflow internal tables and 12 application tables in the same `public` schema, holding **12,808 rows** representing months of collection.

There is no migration tool. Schema evolves through ad-hoc `CREATE TABLE IF NOT EXISTS` across five scripts, two of which define the *same tables with different constraints*.

### 1.3 Presentation

A Streamlit application (12,398 lines across 6 pages), reading PostgreSQL directly with `st.cache_data(ttl=60)` and a 60-second auto-refresh. No map, no authentication, no public/citizen view.

### 1.4 Cloud

S3 upload is active and working. AWS Glue, Amazon Redshift and the Lambda S3 trigger are fully written but commented out of every DAG — and `aws/glue/scripts/etl_pdma.py` is byte-identical to `etl_pmd.py`, so a PDMA Glue job has never existed.

### 1.5 Coverage

Punjab only for hydrology and rainfall; province-level only for disasters; ~40 cities for weather. No division, tehsil or locality level anywhere. No PostGIS, no geometry, no P-codes. Five separate, mutually inconsistent city→province mappings exist in the codebase.

---

## 2. Known defects at baseline

Full detail in the assessment; measured figures in the data-quality baseline. Recorded here so this ADR stands alone.

### P0 — data loss or platform down

| # | Defect | Location | Evidence |
|---|---|---|---|
| 1 | `parse_ndma` crashes on file 1 of 70. `shutil.copy2()` → `utime()` denied by the Windows bind mount to uid 50000. NDMA dead 35 days. | `scripts/parsing/parse_ndma.py:107` | `PermissionError [Errno 1]`, 17/17 task failures |
| 2 | `extract_pdma` crashes on page 1. A leftover `debug_pdma.html` write into the project root. Source returned HTTP 200. PDMA dead 32 days. | `scripts/extraction/extract_pdma.py:91` | `PermissionError [Errno 13]`, 7/7 task failures |
| 3 | Application data lives in the Airflow metadata database. `airflow db reset` or an Airflow upgrade would destroy 12,808 rows. | `.env.docker`, `docker-compose.yml` | `\dt` shows app tables beside `dag`, `task_instance`, `ab_user` |
| 4 | `load_ndma.py` TRUNCATEs all four NDMA tables on every run, then reloads only what survived parsing that day. A parser regression erases history rather than degrading it. | `scripts/database/load_ndma.py:453-469` | code |
| 5 | PMD overwrites `latest.json` at **both** the raw and parsed layers. Every failed load is permanently unrecoverable. **This loss is ongoing.** | `scripts/extraction/extract_pmd.py:83`, `scripts/parsing/pmd/pipeline.py` | 1 file per category; 108 rows sharing one timestamp |
| 6 | One bad row aborts an entire load. Each loader wraps its whole loop in a single `engine.begin()`. | all loaders | **2,016** `psycopg2.errors.InFailedSqlTransaction` in logs |
| 7 | Parsers drop records and still exit 0, so Airflow reports success. 61 of 88 rainfall reports were lost this way with no trace. | `scripts/parsing/parse_pdma.py:170-176` | 88 raw → 27 parsed, task green |
| 8 | Database password printed to stdout, captured in every Airflow task log. | `config/database.py:39`, `dashboard/db.py:52` | code |
| 9 | Raw date strings passed to `DATE` columns. Under `DateStyle = MDY`, `"12.07.2026"` becomes 7 December. Day > 12 raises and aborts the transaction. | all loaders | 74/80 daily reports have NULL `report_date` |

### P1 — correctness and trust

| # | Defect | Evidence |
|---|---|---|
| 10 | 46.2% of gauge water levels and 51.0% of danger levels are NULL. Flood classification is impossible for most of the network. | live query |
| 11 | River dimension corrupted: `1230DG KHAN 1230HILL TORRENTS` (report time bled into the name), `NULLAHS DATA SOURCE: F` (PDF footer), plus letter-spaced duplicates. 4 of 12 values are artefacts. | live query |
| 12 | The most frequent rainfall "station" is the literal header word `Stations` (74 rows, 8.5%). 161 distinct names for 36 districts. | live query |
| 13 | 52.9% of NDMA sitreps rejected. `pdfplumber`'s line-based strategy finds 0 tables on pages 2–11 of borderless sitreps; validation then rejects the whole report if any one of four tables is empty. 35 rejections have no audit trail. | live log + file counts |
| 14 | The dashboard queries `pmd_weather` (a Redshift table name) and `pipeline_logs` — neither exists in PostgreSQL. `_read_sql` catches every exception and returns an empty DataFrame, so these have failed silently since they were written. | code + `\dt` |
| 15 | `build_ndma_dataset.py` produces 0 relief rows (treats dict rows as lists) and null `houses_total` in every row (field-name mismatch). The S3/Glue path therefore carries corrupted data while the PostgreSQL path does not. | `relief.json` = 0 records |
| 16 | Five conflicting city→province mappings; no canonical province dimension; no P-codes. | code |
| 17 | Two competing DDL scripts define the same tables with different constraints; whichever runs first wins. | 25 `UndefinedColumn` errors |
| 18 | `scripts/database/create_pdma_tables.py` contains the old PDMA **loader**, not DDL — and the README instructs running it. | `diff` vs `load_pdma.py` |
| 19 | `aws/glue/scripts/etl_pdma.py` is byte-identical to `etl_pmd.py`. | `diff` returns identical |
| 20 | No DAG creates database tables. DDL is a manual, undocumented, out-of-band step. | 82 `UndefinedTable` errors |
| 21 | `disaster_pipeline` blocks the DAGs it orchestrates (`wait_for_completion` + `max_active_runs=1` + `reset_dag_run` + independent schedules on a LocalExecutor). | 5/5 failures |
| 22 | **Zero tests, zero CI.** No `tests/`, `pytest.ini`, `pyproject.toml`, `.pre-commit-config.yaml` or `.github/`. ~3,400 logged import/name errors would have been caught by a 15-line DagBag test. | filesystem |
| 23 | Every task success and failure sends an email; the Gmail app password is dead. `SMTPAuthenticationError` fires on all ~40 task instances per cycle and buries the real error. | live logs |
| 24 | `requirements.txt` is UTF-16 encoded; `pip install -r` fails on Linux. `airflow_requirements.txt` is fully unpinned. | hexdump |
| 25 | 67 downloaded images, 243 NDMA advisories/guidelines and 3 earthquake reports are collected but never parsed. | file counts |

P2 (architecture/scale) and P3 (hygiene/debt) items 26–53 are catalogued in the assessment.

---

## 3. Decisions

### Decision 1 — A verified backup is required before any change

**Decision.** No Phase 1 work begins until a `pg_dump` of the `airflow` database and an archive of `data/raw/` have been taken, stored outside the repository and outside the Docker volume, and **verified by restoring into a scratch database**.

**Why.** 12,808 rows representing months of collection exist in exactly one place: a Docker volume attached to a database that Airflow can reset. 733 source PDFs sit in one directory, several from government sites with shallow public archives — PDMA Punjab's site only exposes 2025 onward. Neither can be recreated.

A backup that has not been restored is a hypothesis, not a backup. The verification step is part of the decision, not an optional extra.

**Consequences.** One day of Phase 0 effort. In exchange, every subsequent decision — splitting the database, rewriting loaders, changing schema — becomes reversible. This is the precondition that makes the rest of the roadmap safe to attempt.

**Standing rule derived from this:** a fresh backup is required before any schema change, for the life of the project. Recorded as rule 2 in `CLAUDE.md`.

---

### Decision 2 — Move the project into the WSL2 filesystem

**Decision.** Relocate the repository from `E:\Playing with code\...` (Windows NTFS, bind-mounted into Docker) into the native WSL2 filesystem (`~/projects/...`, **not** `/mnt/e/...`, which reintroduces the same problems through a different path).

**Why.** Two of the three current production failures are Windows bind-mount permission errors, not logic errors:

- `parse_ndma` — `utime()` denied to uid 50000 (`PermissionError [Errno 1]`)
- `extract_pdma` — file write to the project root denied (`PermissionError [Errno 13]`)

These are not one-off bugs. They are a *class* of bug produced by the NTFS↔Linux-container boundary, and it also produces line-ending inconsistencies, path-separator bugs, file-mode drift and degraded I/O performance. The codebase already carries scars from it: `s3_key = f"{prefix}/{relative}".replace("\\", "/")` in `aws/s3/upload.py`, and a UTF-16 `requirements.txt` produced by PowerShell redirection.

**Alternatives considered.**

| Option | Assessment |
|---|---|
| Stay on Windows, fix in code (`copy2` → `copy`, remove stray writes, set container UID) | Faster, but treats symptoms. The bug class recurs on every new file write, and the platform's target environment is Linux anyway. |
| Run everything natively on Windows without Docker | Abandons container parity with any future deployment. Airflow on Windows is not well supported. |
| **Move into WSL2** ✅ | One-time move. Eliminates the class permanently. Keeps Docker, keeps Windows as the desktop. Local environment matches the eventual production environment. |

**Consequences.** A one-time relocation with container rebuild. Docker volume paths change; data is already backed up under Decision 1. Editors continue to work through the WSL remote extension. All subsequent development, including CI images, targets Linux consistently.

---

### Decision 3 — AWS spend stays S3-only

**Decision.** The current AWS footprint is Amazon S3 only. No Redshift cluster, no Redshift Serverless workgroup, no Glue job and no Lambda function is running or will be started during Phases 0–5. A billing alarm is to be set during Phase 0.

**Why.** `.env` contains populated `REDSHIFT_HOST`, `REDSHIFT_USER`, `REDSHIFT_PASSWORD` and `GLUE_ROLE_ARN`, which suggested a possible running cluster incurring cost. This has been confirmed as **not running** — the Glue/Redshift/Lambda code paths are commented out of every DAG and were never activated.

Beyond cost, the code that would activate them is defective: `etl_pdma.py` is a duplicate of `etl_pmd.py`, Glue writes use `preactions: DELETE FROM <table>` (a full wipe on every run, so history could never accumulate), and each job reads only a single `latest.json` snapshot. Enabling this path today would load PMD data into PMD tables under a PDMA label and report success.

**Consequences.** Cloud cost stays near zero throughout the foundational phases. The analytical layer is developed locally — MinIO for object storage, local PySpark for distributed processing, dbt against PostgreSQL — with promotion to managed services deferred until the local implementation is correct.

The Glue/Redshift/Lambda code remains in the repository as an **inactive extension**. It is not deleted in Phase 0 and it is not enabled. Whether to repair or retire it is deferred to Phase 6, when the analytical layer is designed properly. Recorded as rule 11 in `CLAUDE.md`.

---

### Decision 4 — Optimise the analytical layer for learning value at zero cost

**Decision.** The lakehouse and warehouse layers will be built on MinIO + local PySpark + Delta Lake + dbt-core, with Databricks Free Edition as the managed-platform experience in Phase 6. Snowflake and Amazon Redshift are not adopted.

**Why.** The project has two goals in tension: a working platform and a serious learning vehicle. Optimising for both under a near-zero budget favours tooling that is free to run indefinitely, teaches transferable skills, and does not lock the data in.

| Option | Assessment |
|---|---|
| **Redshift** | Nothing running; weak geospatial support; awkward streaming; thin ML story; bills continuously. Teaches an AWS-specific product rather than a transferable skill. |
| **Snowflake** | Excellent product, but the trial expires and it teaches SQL-on-a-warehouse rather than distributed processing. Revisit only if a target role demands it. |
| **Databricks Free Edition** ✅ | Real Spark, Delta Lake, Unity Catalog, MLflow and notebooks at no cost. Strongest geospatial (Mosaic/Sedona) and ML story of the three. Delta Lake is portable, so this is not a lock-in. |
| **Local Spark + MinIO + dbt** ✅ | Free, offline-capable, and more is learned from a cluster that can be broken freely than from a managed one that cannot be afforded. Identical code path to S3. |

**Consequences.** Phase 5 (lakehouse) and Phase 6 (warehouse) are buildable at zero marginal cost. dbt-core provides tests, docs and lineage almost free and is close to a hiring prerequisite. The decision is revisitable: Delta Lake on object storage can be pointed at any engine later.

---

### Decision 5 — Stabilise before expanding *(governing principle)*

**Decision.** No new data source, no new province, no new domain, no PostGIS, no lakehouse, no streaming, no ML, no RAG and no agent work begins until the existing three domain pipelines run green, unattended, for **seven consecutive days**, with data-quality gates that fail loudly.

**Why.** This is the principle that orders everything else, and it follows directly from what the assessment measured.

The platform's problem is not that it lacks features. It has seven DAGs, a validation package, PDF table extraction, S3 archival, a Glue/Redshift implementation and a 12,000-line dashboard. Its problem is that **none of it currently runs, and when it did run it lost data without saying so.**

Three findings make the ordering non-negotiable:

1. **Failure is currently invisible.** A run in which 61 of 88 rainfall reports failed to parse exited 0 and Airflow showed green. The dashboard queries two tables that do not exist and displays blanks rather than errors. Any feature built on top of this inherits the blindness.
2. **The data is not yet trustworthy.** 46% of gauge water levels are NULL. A third of the river dimension is PDF artefacts. 93% of daily reports have no date. Adding six more provinces to this would multiply the corruption, not the value.
3. **There is no safety net.** Zero tests, no CI, no migrations, no lineage, application data inside the Airflow metadata database. Every change is currently unverifiable and potentially destructive.

Expanding scope before fixing these would produce a larger platform that is wrong in more places, and would make the eventual repair proportionally harder. Conversely, every later phase — geography, lakehouse, ML, RAG — consumes data this pipeline produces. If that data is wrong, everything downstream is wrong in ways that are expensive to detect and harder to unwind.

**Consequences.**

- Phase 1 delivers **no new capability**. It fixes crashes, separates the databases, adopts Alembic, rewrites loaders for per-record error isolation, adds quarantine and rejection thresholds, and writes the first tests. This is deliberate.
- Feature work is deferred, not cancelled. The roadmap runs to Phase 14.
- Each phase carries an explicit exit gate. **No phase begins until the previous gate is met.**

**Phase 1 exit gate (the only gate that matters right now):**

| Criterion | Baseline | Required |
|---|---:|---|
| `ndma_pipeline`, `pdma_pipeline`, `pmd_pipeline` green | 0 days | **7 consecutive days** |
| `InFailedSqlTransaction` occurrences | 2,016 | **0** |
| Silently dropped records | uncounted | **0** — every rejection in `dq.quarantine` with a reason |
| Application tables in the `airflow` database | 12 | **0** — migrated to `pori` |
| Automated tests | 0 | DAG integrity + parser golden files + type coercion, green in CI |
| Secrets printed to logs | 2 call sites | **0** |
| NDMA data age | 35 days | **< 48 hours** |
| PDMA / PMD data age | 32 / 20 days | **< 12 hours** |

---

## 4. Consequences of this ADR taken as a whole

**Positive**

- The pre-change state is measured and frozen. Improvement becomes provable rather than asserted.
- Irreplaceable data (12,808 rows, 733 source PDFs) is protected before anything is touched.
- Two of the three live production failures are eliminated by an environment decision rather than by patching symptoms.
- Cloud cost stays near zero through the foundational phases.
- The work has an explicit order with explicit gates, so "am I ready for the next phase?" is answerable with a query rather than a judgement call.

**Negative / accepted costs**

- Phase 0 and Phase 1 together deliver roughly three to four weeks with **no new user-visible capability**. Accepted deliberately.
- The WSL2 move is a one-time disruption to a working local setup.
- Deferring the Glue/Redshift decision to Phase 6 leaves known-defective code in the repository. Mitigated by rule 11 in `CLAUDE.md`: it stays inactive and must not be enabled without an explicit decision.
- Gauge NULL rates, the corrupted river dimension and rainfall junk stations are **measured but not fixed** in Phase 1 — reducing them requires the reference data and canonical geography built in Phase 2. Phase 1's obligation is to make these rates counted, recorded and capable of failing a task when they regress.

**Neutral**

- The roadmap is long (~50 weeks at a steady pace). Phases 0–4 are the mandatory foundation; Phases 5–14 can be re-ordered or paused without breaking anything.

---

## 5. Open questions carried forward

Recorded so they are not lost. Full list in the assessment, Part E.

**Before Phase 1**

1. Is anything currently depending on the running PostgreSQL container (a bookmarked dashboard, a shared link)? Affects how disruptive the database split can be.
2. Is `data/` (866 tracked files, growing) intended to remain in Git? Decide before it becomes unmanageable — Git LFS, exclusion, or deliberate acceptance.

**Before Phase 2**

3. Which admin-boundary source is authoritative — HDX/OCHA COD-AB (P-codes) or GADM? Recommendation: HDX primary, GADM cross-check.
4. Are real coordinates obtainable for the 42 gauge and 161 rainfall stations? Without them, spatial analysis stays at district level.
5. **How should Indian-administered Kashmir localities appearing in PMD data be modelled?** Recommendation: `control_status = 'external'` — retained but explicitly labelled. Requires an owner decision, not a default.
6. Do reliable division and tehsil boundaries exist for all provinces, or only some?

**Before Phase 12**

7. **Is there a right to republish scraped NDMA/PDMA/PMD content publicly?** Government publication is not automatically an open licence. Must be resolved in writing before any public launch.

---

## 6. Notes

- The assessment underlying this ADR was strictly read-only. No file was modified, no database write was issued, no Docker or AWS resource was touched, no Git history was altered.
- Phase 0 creates documentation and scaffolding only: this ADR, the architecture assessment, the data-quality baseline, and `CLAUDE.md`.
- `.env` is untracked and has never been committed (`git log --all -- .env` returns empty). `.env.docker` **is** tracked despite `.env.*` in `.gitignore`, having been added before that rule; it currently contains no secrets, but the pattern is wrong and is scheduled for correction in Phase 1.
- Baseline figures were measured on **2026-09-01**; this ADR was written on **2026-09-02**. Data staleness figures are therefore one day older than stated in the baseline document, which is left unedited by design.
