# PORI Lakehouse — Databricks / Spark / Delta Lake

**Status: SCAFFOLDED, NOT IMPLEMENTED.** This directory establishes the
repository structure, schema contracts, and design documentation for
PORI's future analytical/lakehouse layer. It is not wired into the
Airflow pipeline, not connected to any live Databricks workspace, and
contains no code that reads or writes real data. PySpark is not
installed in this project's environments yet (deliberately — see
"What is NOT done yet" below).

Task 16A (Phase 1 / ADR-0001) formally changed PORI's architecture:
**AWS Glue and Amazon Redshift have been removed** (see
`docs/architecture/CODEBASE_AUDIT.md` and this task's own report).
Databricks + Apache Spark + Delta Lake is the new, selected
analytical/lakehouse platform.

## Target architecture

```
Official Sources
      |
      v
Airflow  (orchestration -- unchanged, scripts/acquisition + scripts/extraction)
      |
      v
AWS S3 Raw Zone  (unchanged -- aws/s3/upload.py)
      |
      v
Databricks  (Unity Catalog external location over the S3 raw zone)
      |
      v
Spark / Delta Lake
      |
      v
Bronze --> Silver --> Gold
      |
      v
ML / Forecasting / Risk Analytics
      |
      v
PostgreSQL + PostGIS  (operational/geospatial serving layer -- unchanged)
      |
      v
FastAPI  (see api/README.md)
      |
      v
Dashboard / Map / RAG / AI
```

PostgreSQL/PostGIS remains the operational, geospatial, dashboard-serving
database. This lakehouse layer is an *additional* analytical tier
upstream of it, not a replacement -- Databricks Gold tables are the
intended future source that populates PostgreSQL, not the other way
around, and that population step does not exist yet either.

## Directory layout

```
databricks/
├── README.md              this file
├── notebooks/              exploratory/interactive Databricks notebooks (none written yet)
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   ├── ml/
│   └── exploration/
├── src/                     reusable, testable Python modules (the actual transformation logic)
│   ├── bronze/                 raw-to-bronze ingestion functions
│   ├── silver/                  bronze-to-silver cleaning/normalization functions
│   ├── gold/                     silver-to-gold aggregation/analytics functions
│   ├── features/                  ML feature-engineering functions (future Task 9 successor)
│   ├── ml/                         model training/inference functions
│   └── common/                      shared Spark session/schema/IO helpers
├── jobs/                    Databricks Jobs definitions (none deployed yet -- see jobs/README.md)
├── schemas/                 documented, versioned table contracts per layer (see below)
│   ├── bronze/
│   ├── silver/
│   └── gold/
├── tests/                   pytest tests for src/ (skipped when pyspark isn't installed)
└── resources/               Databricks Asset Bundle / infra config docs (see resources/README.md)
```

## Lakehouse layers

### Bronze -- raw structured representation

One Delta table per source dataset, schema-on-read from the existing
`data/raw/` (legacy convention) and `data/raw/<org>/<dataset>/<date>/`
(Task 15 acquisition convention) JSON/PDF-extracted content, with
provenance columns (`source_document_id`, `ingested_at`,
`parser_version`) carried through unchanged from what the existing
parsers already attach. No cleaning, no normalization, no field
renaming -- bronze is the raw payload made queryable, nothing more.

Planned bronze datasets (contracts documented under `schemas/bronze/`,
none implemented yet):
- `bronze_ndma_sitreps` -- NDMA casualties/damage/relief/rescue, from `data/parsed/ndma/`
- `bronze_pdma_daily` / `bronze_pdma_rainfall` / `bronze_pdma_gauge` -- from `data/parsed/pdma/`
- `bronze_pmd_daily_forecast` / `bronze_pmd_weekly_outlook` / `bronze_pmd_weather_alerts` -- from `data/parsed/pmd/`
- `bronze_aqi_punjab` -- from Task 15's `data/raw/epa_punjab/aqi_punjab/`
- `bronze_ffc` -- from Task 15's `data/raw/ffc/`
- `bronze_suparco_disasterwatch` -- from Task 15's `data/raw/suparco/disasterwatch/`

### Silver -- cleaned, normalized, conformed data

Bronze records resolved against the existing canonical geography
(`scripts/geo/canonical_data.py`, `geo.admin_unit`/`geo.name_alias` --
reused, not reimplemented), timestamps standardized to UTC + PKT,
units normalized, and structurally validated. Silver is where a
record earns the right to be called "clean."

Planned silver datasets:
- `silver_geography` -- canonical admin-unit reference, mirrored from `geo.admin_unit`
- `silver_weather_observations` -- normalized PMD daily/weekly records
- `silver_rainfall_observations` -- normalized PDMA rainfall readings
- `silver_gauge_observations` -- normalized PDMA river gauge readings (feeds the existing Task 9 forecasting baseline)
- `silver_air_quality_observations` -- normalized AQI Punjab readings
- `silver_hazard_events` -- canonical NDMA/FFC/SUPARCO disaster-event records

### Gold -- business-ready analytics

Aggregated, analysis-ready tables intended to be the source PostgreSQL
eventually reads from (that read path does not exist yet).

Planned gold datasets:
- `gold_district_risk_summary` -- per-admin-unit composite risk indicators
- `gold_flood_risk` -- flood-specific risk analytics from gauge + rainfall silver tables
- `gold_weather_risk` -- heat/cold/AQI risk analytics
- `gold_infrastructure_damage` -- NDMA damage rollups by admin unit
- `gold_ml_features` -- the feature table a forecasting model trains against (successor to `scripts/forecasting/features.py`)

**None of the tables above have been created.** This is a documented
contract for what they will look like, not a schema that exists in any
Delta Lake, Unity Catalog, or Spark session today.

## S3 + Unity Catalog design (documented, not executed)

```
AWS S3 (existing raw zone, aws/s3/upload.py)
   |
   v
Unity Catalog external location  (points at the S3 bucket/prefix; created via
                                   Databricks admin console or Terraform --
                                   NOT created in this task, see
                                   infrastructure/terraform/README.md)
   |
   v
Delta Lake tables (managed or external, under a Unity Catalog schema
                    per layer: bronze / silver / gold)
```

No AWS credentials are hardcoded anywhere in this scaffold. No IAM
role, Unity Catalog metastore, or external location has been created.
Wiring this up requires: (1) a Databricks workspace (not provisioned),
(2) a Unity Catalog metastore with an external location IAM role
trusting the S3 bucket (not provisioned), (3) a Databricks secret scope
or instance profile for credentials (not provisioned). All of this is
future, paid-infrastructure work explicitly out of scope for Task 16A.

## Local development

`databricks/src/common/spark_session.py::get_local_spark_session()`
returns a local (`local[*]`), single-process SparkSession suitable for
running the same transformation functions under pytest without any
Databricks workspace -- the same "write once, test locally, deploy to
the real platform later" pattern Databricks itself recommends. PySpark
is not currently installed in this project's `requirements.txt` /
`airflow_requirements.txt` (deliberately, to avoid pulling in a large
JVM-dependent runtime before there is real lakehouse code to run) --
see `databricks/tests/` for how tests degrade gracefully
(`pytest.importorskip("pyspark")`) when it isn't installed, rather than
failing the suite.

## What is NOT done yet

- No PySpark dependency installed (by design, see above).
- No Delta table has ever been created or written.
- No Databricks workspace, cluster, or job has been created or run.
- No Unity Catalog metastore or external location exists.
- No data has moved from `data/raw/`/`data/parsed/`/Postgres into this
  layer.
- No DAG references anything under `databricks/`.
- The ML path (Task 9's `scripts/forecasting/`) is preserved exactly
  as-is; `databricks/src/features/` and `databricks/src/ml/` are empty
  scaffolding for a *future* successor, not a replacement -- see
  "ML / Forecasting" below.

## ML / Forecasting

Task 9's gauge-discharge forecasting baseline
(`scripts/forecasting/gauge_discharge_forecast.py`,
`scripts/forecasting/features.py`) is unchanged by this task -- not
deleted, not rewritten, and its existing honest baseline result is not
superseded by any claim made here. The intended future path once this
lakehouse layer is real:

```
silver_gauge_observations (Delta)
        |
        v
databricks/src/features/  (feature engineering, successor to
                            scripts/forecasting/features.py's approach,
                            same chronological-split discipline)
        |
        v
ML training dataset (gold_ml_features)
        |
        v
Forecast model (databricks/src/ml/)
        |
        v
Predictions
        |
        v
gold_flood_risk (or a new gold forecast table)
        |
        v
PostgreSQL/PostGIS --> FastAPI
```

No part of this future path has been implemented. No claim of improved
model performance is made anywhere in this scaffold relative to Task
9's existing, tested baseline.
