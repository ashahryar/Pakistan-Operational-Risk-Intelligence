# CLAUDE.md — Project Rules

Permanent operating rules for the Pakistan Operational Risk Intelligence Platform.
This file is loaded automatically at the start of every session. **Read it before acting.**

| | |
|---|---|
| **Established** | 2026-09-02 (Phase 0) |
| **Current phase** | Phase 0 complete → Phase 1 (Stabilise) not yet started |
| **Authority** | These rules override convenience, speed and inferred intent. Changing them requires an explicit decision recorded as a new ADR. |
| **Context** | [`docs/assessment/ARCHITECTURE_ASSESSMENT.md`](docs/assessment/ARCHITECTURE_ASSESSMENT.md) · [`docs/DATA_QUALITY_BASELINE.md`](docs/DATA_QUALITY_BASELINE.md) · [`docs/decisions/ADR-0001-baseline-and-recovery.md`](docs/decisions/ADR-0001-baseline-and-recovery.md) |

---

## Where the project stands

The platform is **not currently running**. 38 of 39 DAG runs have failed; there has been one success in its history. NDMA data is stale by 35+ days, PDMA by 32+, PMD by 20+. Roughly half of all river-gauge measurements are NULL, and a third of the river dimension is PDF artefacts stored as real entities.

This is not a project that needs new features. It is a project that needs to run correctly and tell the truth about its own data. Act accordingly.

---

## The rules

### 1. Never run destructive database or Docker commands without explicit approval

Ask first, every time. No exceptions for "it's obviously fine".

Requires explicit approval: `DROP`, `TRUNCATE`, `DELETE`, `ALTER ... DROP`, `airflow db reset`, `airflow db clean`, `docker compose down -v`, `docker volume rm`, `docker system prune`, `rm -rf`, `git reset --hard`, `git push --force`, and anything that removes files under `data/`.

**Why it matters here.** Application data currently lives inside the Airflow metadata database (see rule 3). A single `airflow db reset` destroys 12,808 rows representing months of collection. The 733 source PDFs under `data/raw/` come from government sites with shallow archives and cannot be re-downloaded.

---

### 2. A fresh backup is required before any database schema change

Before any migration, DDL statement, or structural change:

1. `pg_dump` the target database to a location **outside** the repository and outside the Docker volume.
2. **Verify the dump by restoring it into a scratch database.** An unrestored backup is a hypothesis, not a backup.
3. Only then apply the change.

This applies to the Phase 1 database split, every Alembic migration, and any manual `ALTER`.

---

### 3. The Airflow metadata database and the PORI application database must be separate

**Current state (defect):** both live in database `airflow`, in schema `public`, under the same superuser. `\dt` returns 42 Airflow internal tables interleaved with 12 application tables.

**Target state (from Phase 1 onward):**

| Database | Contents | Role |
|---|---|---|
| `airflow` | Airflow metadata only | `airflow` |
| `pori` | All application data | `pori_writer` (pipeline), `pori_reader` (dashboard) |

After Phase 1, **never create an application table in the `airflow` database**, and never connect the dashboard or a loader as the Airflow superuser.

---

### 4. Alembic is the only schema-change mechanism after Phase 1

Once Phase 1 lands, every schema change is an Alembic revision — reviewed, versioned, reversible, and applied by an orchestrated task.

Prohibited after Phase 1:

- `CREATE TABLE IF NOT EXISTS` in a Python script
- Inline `ALTER TABLE` outside a migration
- Any hand-run `psql` DDL against a non-scratch database

**Why it matters here.** `create_tables.py` and `create_pmd_tables.py` currently define the *same tables with different constraints*; whichever runs first wins. That single ambiguity produced 25 `UndefinedColumn` errors and 82 `UndefinedTable` errors in the logs.

---

### 5. No silent record dropping

Every record that enters a pipeline must leave it in a **countable** state: loaded, quarantined, or explicitly and loudly rejected. Never simply skipped.

Required of every parser and loader:

- Return `(processed, succeeded, rejected)` — not `None`, not a bare bool.
- **Fail the task when the rejection ratio exceeds its threshold.** A task that processes 27 of 88 files and reports success is a defect, not a partial success.
- Never `except Exception: continue` without incrementing a counter and writing the reason.
- Never `if not valid: continue`.
- Never let a `dropna()` or a silently-swallowed exception decide what reaches the user.

**Why it matters here.** 61 of 88 rainfall reports were lost this way and Airflow showed green. The dashboard's `_read_sql()` catches every exception and returns an empty DataFrame, which is why two queries against non-existent tables have failed invisibly since they were written.

---

### 6. Invalid or unparseable records go to quarantine

Not to `/dev/null`, not to a `print()`, not to a folder with no index.

Every rejection writes a row to `dq.quarantine` carrying: the source document reference, the raw payload, a machine-readable reason code, a human-readable message, the parser version, and a timestamp. Quarantined records must be queryable, countable, and re-processable once the parser is fixed.

**Why it matters here.** 37 NDMA sitreps were rejected; 2 PDFs sit in `data/rejected/`. There is no record of why the other 35 were discarded, or that they were discarded at all.

---

### 7. Never fabricate data

Do not invent, interpolate, default, or infer a value to make a pipeline pass or a chart render.

- A missing coordinate is `NULL`, not a province centroid.
- A missing date is `NULL` and a rejection, not `datetime.now()`.
- An unmatched station name is `unresolved`, not a fuzzy guess silently accepted.
- An unknown province is `NULL` or `'Unknown'` — and the count of `'Unknown'` is reported, not hidden.
- Interpolated or estimated values carry `quality_flag = 'estimated'` and are labelled as such wherever they surface.

Do not fabricate figures in documentation or commit messages either. Every number in `docs/` must be traceable to a query, a log count, or a file count.

**Why it matters here.** This platform is intended to inform flood and disaster response. A fabricated water level is not a cosmetic defect.

---

### 8. Do not redesign the architecture without explicit approval

The target architecture is recorded in the assessment and the ADRs. Follow it.

If a better approach becomes apparent mid-task: stop, state the case in one or two sentences, and ask. Do not refactor beyond the task's stated scope, do not swap a library for a preferred alternative, and do not restructure directories opportunistically.

Substantive deviations are recorded as a new ADR under `docs/decisions/` before implementation, not after.

---

### 9. Do not add new major features before Phase 1 passes validation

Phase 1 is stabilisation. It delivers **no new capability** by design.

Blocked until the Phase 1 gate is met: new data sources, new provinces, new domains, PostGIS, the lakehouse, streaming, ML, RAG, agents, the API, and dashboard redesign.

**Phase 1 exit gate — all criteria, simultaneously:**

| Criterion | Baseline | Required |
|---|---:|---|
| `ndma_pipeline`, `pdma_pipeline`, `pmd_pipeline` green | 0 days | **7 consecutive days** |
| `InFailedSqlTransaction` occurrences | 2,016 | **0** |
| Silently dropped records | uncounted | **0** |
| Application tables in the `airflow` database | 12 | **0** |
| Automated tests | 0 | DAG integrity + parser golden files + type coercion, green in CI |
| Secrets printed to logs | 2 call sites | **0** |
| NDMA data age | 35 days | **< 48 hours** |
| PDMA / PMD data age | 32 / 20 days | **< 12 hours** |

---

### 10. Verify every change with tests or concrete runtime evidence

"It should work now" is not a result. Acceptable evidence:

- A passing test that fails without the change
- Actual command output — a task log, a query result, a row count
- A before/after comparison against [`docs/DATA_QUALITY_BASELINE.md`](docs/DATA_QUALITY_BASELINE.md)

Report outcomes faithfully. If a fix is unverified, say so. If a test fails, show the output. If part of a task was skipped, state which part and why.

**Why it matters here.** Both live production failures were found by reading task logs, not by reasoning about the code. The logs are the ground truth; use them.

---

### 11. AWS Glue and Redshift remain an inactive extension until explicitly re-enabled

Current AWS footprint: **S3 only.** No Redshift cluster, no Glue job, no Lambda function is running.

- Do not uncomment Glue or Redshift tasks in any DAG.
- Do not provision Redshift, Glue jobs, crawlers or Lambda functions.
- Do not delete the code either — the repair-or-retire decision is deferred to Phase 6.

**Known defects in that code, for the record:** `aws/glue/scripts/etl_pdma.py` is byte-identical to `etl_pmd.py`, so a PDMA Glue job has never existed. Glue writes use `preactions: DELETE FROM <table>`, a full wipe on every run. Each job reads a single `latest.json` snapshot. Enabling this path today would load PMD data under a PDMA label and report success.

Any new AWS resource requires explicit approval and a billing check first.

---

### 12. The current target is a stable working baseline before expansion

When a decision is ambiguous, choose the option that makes the platform **more correct and more observable**, not the one that makes it larger.

- Correctness over coverage.
- Observability over features.
- One reliable province over six unreliable ones.
- A pipeline that fails loudly over one that succeeds quietly.

The roadmap runs to Phase 14 and the ambition is a national platform. That ambition is served by getting the foundation right first, not by racing ahead of it.

---

## Working notes

### Repository layout

```
scripts/extraction/   NDMA / PDMA / PMD scrapers        → data/raw/
scripts/parsing/      PDF + HTML → structured JSON      → data/parsed/, data/analytics/
scripts/database/     DDL + loaders (Alembic from P1)
scripts/warehouse/    star-schema scripts — NEVER EXECUTED, 3 files empty
scripts/risk_engine/  risk scoring — NEVER EXECUTED, 0 rows produced
validation/           per-source schema / completeness / score
pipeline/dags/        7 Airflow DAGs (mounted to /opt/airflow/dags)
pipeline/helpers/     script_runner, aws_helper, redshift_helper, email_helper
pipeline/sensors/     3 sensors — imported by no DAG
pipeline/utils/       callbacks, logging, DQ; metadata_logger.py & duplicate_checker.py are EMPTY
config/               settings, DB engine, AWS config, paths
aws/                  S3 upload/download, Glue, Redshift DDL, Lambda — INACTIVE (rule 11)
dashboard/            Streamlit, 12,398 lines, 6 pages
docs/assessment/      architecture assessment (source of truth)
docs/decisions/       ADRs
data/                 raw / parsed / analytics / rejected  (866 files tracked in Git)
```

### Container and connection facts

| Item | Value |
|---|---|
| Containers | `airflow_webserver`, `airflow_scheduler`, `airflow_postgres` |
| Postgres — from host | `localhost:5433` |
| Postgres — from container | `postgres:5432` |
| Airflow UI | `http://localhost:8088` |
| DAGs mounted from | `./pipeline/dags` → `/opt/airflow/dags` |
| Project mounted at | `/opt/project` (`PYTHONPATH`, `working_dir`) |
| Container UID | 50000 |

Read-only inspection (safe):

```bash
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT dag_id, state, count(*) FROM dag_run GROUP BY 1,2 ORDER BY 1;"
```

### Gotchas that have already caused outages

| Gotcha | Consequence |
|---|---|
| Windows bind mount denies `utime()` to uid 50000 | `shutil.copy2()` raises `PermissionError [Errno 1]` — killed `parse_ndma` for 5 weeks. Use `shutil.copy()`. Moving to WSL2 (ADR-0001, Decision 2) removes the class. |
| Writing to the project root from inside a container | `PermissionError [Errno 13]` — killed `extract_pdma` for 5 weeks. Never write to CWD; use an explicit path under `data/` or `/tmp`. |
| `create_pdma_tables.py` contains the old **loader**, not DDL | Running it as the README instructs re-runs a legacy loader with the date bug. |
| Postgres `DateStyle = MDY` | `"12.07.2026"` parses as 7 December. Day > 12 raises and aborts the whole transaction. Always parse dates in Python with `dayfirst=True`. |
| One `engine.begin()` around a whole load loop | One bad row rolls back everything — 2,016 logged occurrences. Isolate per record. |
| `requirements.txt` is UTF-16 | `pip install -r` fails on Linux. |
| `dashboard/db.py::_read_sql` swallows all exceptions | A broken query is indistinguishable from an empty table. |
| Local package names shadow framework names | ~3,400 logged `ImportError`/`NameError`. A `DagBag` import test catches all of them. |

### Never commit

`.env` (untracked, never committed — keep it that way) · AWS keys · SMTP passwords · database passwords · `pg_dump` output · anything under `airflow/logs/`.

`.env.docker` is currently tracked despite `.env.*` in `.gitignore`. It holds no secrets today; scheduled for correction in Phase 1.
