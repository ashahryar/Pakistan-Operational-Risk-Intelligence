# Databricks resources (infrastructure configuration)

**Status: documentation only, nothing provisioned.**

This directory will hold Databricks Asset Bundle resource
definitions (workspace, cluster policy, Unity Catalog external
location reference, secret scope) once the project actually connects
to a Databricks workspace. None of that exists yet:

- No Databricks workspace has been created.
- No Unity Catalog metastore or external location has been created.
- No Databricks secret scope or instance profile has been created.
- No cluster or SQL warehouse has been created.

## Planned S3 <-> Unity Catalog wiring (documented, not executed)

1. An IAM role trusting Databricks's Unity Catalog service principal,
   scoped to read (and, for bronze ingestion, write) the project's
   existing S3 bucket/prefix (`aws/s3/upload.py`'s target bucket) —
   would be defined in `infrastructure/terraform/`, not here, and not
   applied by this task (see Part N of Task 16A: no AWS resource
   changes).
2. A Unity Catalog external location in the Databricks workspace,
   pointing at that S3 path via the IAM role above.
3. Unity Catalog catalogs/schemas `pori.bronze`, `pori.silver`,
   `pori.gold`, each backed by that external location (or a
   sub-location per layer).

No AWS access key, secret key, or IAM role ARN is hardcoded anywhere
in this repository. Local development uses
`databricks/src/common/spark_session.py::get_local_spark_session()`
(a plain local Spark session, no cloud credentials needed) rather than
a real Databricks connection — see `databricks/README.md`.
