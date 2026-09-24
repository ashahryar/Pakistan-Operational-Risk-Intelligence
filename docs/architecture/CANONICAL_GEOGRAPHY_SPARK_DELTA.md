# Canonical geography integration + Spark/Delta Bronze/Silver foundation

Task 18 closes the two follow-up gaps Task 17 identified, without touching Task 10's geography semantics or Task 17's canonical contracts.

## 1. Canonical → geography enrichment

`pipeline/canonical/geography.py::enrich_location()` is the new integration boundary. It calls the existing Task 10 pure resolver (`scripts/geo/resolver.py::resolve()`) unchanged, then optionally maps the resolver's matched canonical name to a real `geo.admin_unit.id` via an injected `admin_unit_lookup` callable. No second resolver, alias table, or matching algorithm was created.

`pipeline/canonical/adapters.py::_geo()` is now a thin wrapper around `enrich_location()`. Every `adapt_*` function gained an optional `admin_unit_lookup=None` keyword — when omitted, `admin_unit_id` stays `None` exactly as it did in Task 17 (fully backward compatible); when supplied, real IDs are populated.

## 2. Resolved / ambiguous / unresolved semantics

Unchanged from Task 10, reused verbatim:
- **resolved** — `admin_unit_id` populated (if a lookup was supplied) and `admin_unit_key`/`resolution_status="resolved"`.
- **ambiguous** — `admin_unit_id` stays `None`; a comma/slash-separated multi-value string (e.g. `"Gujranwala, Jhelum"`) is never split or guessed.
- **unresolved** — `admin_unit_id` stays `None`; original text is preserved in `location_original`.

Hierarchy safety is structural, not a convention: the resolver only ever sees the candidate pool the caller passes (`PROVINCES` or `DISTRICTS` from `scripts/geo/canonical_data.py`), so a province-only value (e.g. `"Punjab"`) can never resolve against the district pool.

## 3. PostgreSQL / PostGIS role

`build_db_admin_unit_lookup(engine)` issues exactly one read-only query per unique name — `SELECT id FROM geo.admin_unit WHERE name = :name` — the same query `scripts/geo/resolve_observations.py::_admin_unit_id` already uses. No `INSERT`/`UPDATE`/`DELETE` is ever issued by this module. `geo.admin_unit`/`geo.name_alias` remain the single geography source of truth; the lakehouse layer (§4–7) does not duplicate them.

## 4. Bronze contract

`databricks/src/bronze/canonical_bronze.py::load_canonical_to_bronze()` reads a Task 17 canonical JSONL file with an explicit `StructType` (`databricks/src/common/schemas.py` — one schema per domain: `weather_observation`, `rainfall_observation`, `gauge_observation`, `disaster_event`, `hazard_alert`; AQI remains contract-only, no adapter exists yet), never `spark.read.json()` inference. Every canonical field — provenance, geography, and domain fields — is preserved verbatim. Deduplication keys on `(domain, source, source_record_id)`, keeping the row with the latest `ingestion_timestamp`.

`write_bronze_delta()` is idempotent **across** runs, not just within one load: it reads any existing Delta table at the target path, unions in the new rows, re-deduplicates, and overwrites — so re-running the same canonical input twice produces the same row count, not doubled rows.

## 5. Silver contract

`databricks/src/silver/canonical_silver.py::to_silver()` casts each domain's ISO timestamp string columns to real Spark `TimestampType` (e.g. `observed_at`, `event_date`, `issued_at`), re-applies the same dedup key, and guards against fully-null observation rows via the existing `assert_no_fully_null_rows()` (Task 16A, reused unchanged). Numeric fields are already typed by the explicit bronze schema — silver does not re-implement numeric casting.

## 6. Spark transformation boundary

New modules live inside the existing Task 16A `databricks/src/{bronze,silver,common}/` structure — no new top-level `databricks/spark/` folder was created. `databricks/src/common/schemas.py` (explicit domain schemas) and `databricks/src/common/io.py` (Delta read/write with a caller-supplied base path) are new; `databricks/src/common/transforms.py`'s existing `deduplicate_by_key`/`assert_no_fully_null_rows` (Task 16A) are reused, not reimplemented.

## 7. Delta storage boundary

`io.py::write_delta()`/`read_delta()` always use `.format("delta")`. If `delta-spark` is not configured, Spark itself raises a real error at write time — this module never falls back to Parquet and calls it Delta. No path is hardcoded: tests pass a `tmp_path` local directory; a real deployment would pass an `s3://.../bronze` or Unity Catalog path with no code change.

## 8. Local testing

`pyspark` is still not installed in this project's environments (venv or Docker image) — confirmed again this task. Every new Spark test (`databricks/tests/test_canonical_bronze_silver.py`) begins with `pytest.importorskip("pyspark", ...)`, matching Task 16A's established convention, so the suite reports **skipped**, not failed, and will actually run once `pyspark`/`delta-spark` are installed. No dependency was added to `requirements.txt`/`airflow_requirements.txt` in this task — adding a JVM-backed, multi-hundred-MB dependency solely for tests that cannot run in the current environment was explicitly out of scope (Task 18 Part 29).

Geography enrichment, by contrast, is fully real and DB-tested: `tests/canonical/test_geography.py` (10 tests, no database) and `tests/canonical/test_geography_live_db.py` (3 tests, live read-only queries against the real `geo.admin_unit` table) both pass today.

## 9. Databricks deployment status

No live Databricks workspace was connected to, and none is required. No credentials were requested, stored, or hardcoded anywhere in this task.

## 10. Current limitations

- The Bronze→Silver Spark tests are written and lint-clean but **not executed** in this environment (no pyspark). They are real, reviewable code following Task 16A's established local-Spark pattern, not a fabricated pass.
- AQI has a documented schema slot but no adapter — unchanged from Task 17 (no parsed AQI source exists yet).
- No Gold layer, ML feature store, or risk score — out of scope for Task 18 by explicit instruction.
- `write_bronze_delta`'s idempotent read-union-dedupe-overwrite pattern is a reasonable local/small-table approach; a production-scale deployment would likely prefer a Delta `MERGE INTO` upsert instead — noted as a natural follow-on, not implemented here to keep this task's Spark surface small and testable.
