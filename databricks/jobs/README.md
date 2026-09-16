# Databricks Jobs

**Status: no job defined or deployed.**

This directory will hold Databricks Jobs definitions (either as
Databricks Asset Bundle YAML or notebook-based job configs) once there
is real bronze/silver/gold transformation code to schedule — see
`databricks/src/` and `databricks/README.md`.

Planned shape, once implemented, matching the existing Airflow
convention of one DAG per domain rather than one giant job:

```
databricks/jobs/
├── bronze_ingestion_job.yml     (bronze/* modules, triggered after
│                                  Airflow's existing extraction DAGs
│                                  land new raw data in S3)
├── silver_transform_job.yml     (silver/* modules)
└── gold_aggregation_job.yml     (gold/* modules)
```

No job here is triggered by any Airflow DAG today, and none will be
until the underlying `databricks/src/bronze|silver|gold/` modules
exist and have been tested. Airflow remains the orchestration layer
for source extraction/acquisition (unchanged); if/when this lakehouse
layer becomes real, the likely integration point is an Airflow task
that triggers a Databricks Job via the Databricks REST API — not
implemented, not scoped for this task.
