"""
databricks/src/common/spark_session.py

Task 16A (Phase 1 / ADR-0001) -- minimal reusable Spark foundation.

STATUS: scaffolded, not exercised against real data. PySpark is not
currently a project dependency (see databricks/README.md's "What is
NOT done yet" for why); this module imports it lazily, inside each
function, so importing `databricks.src.common.spark_session` itself
never requires PySpark to be installed -- only actually calling
`get_local_spark_session()` does.

Design rules this module (and every future bronze/silver/gold module
built on top of it) follows, per Task 16A's explicit requirements:
  - explicit schemas where appropriate (no implicit schema inference
    on anything that will feed a downstream Delta table)
  - deterministic transformations (no wall-clock/randomness inside a
    transform function -- pass `as_of` as a parameter instead)
  - no uncontrolled `.collect()` -- collecting a full DataFrame to the
    driver is a deliberate, explicit, justified choice at the call
    site, never a default
  - partition-aware processing where appropriate (write functions
    accept a `partition_by` argument rather than hardcoding one)
  - every transformation is a plain, testable function taking and
    returning a DataFrame -- no notebook-only logic; notebooks (once
    written) will import from here, not the reverse
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


def get_local_spark_session(app_name: str = "pori-lakehouse-local") -> "SparkSession":
    """
    Returns a local, single-process SparkSession (`local[*]`) for
    running the transformation functions under `databricks/src/` from
    a test or a local script, with no Databricks workspace or cluster
    required -- Databricks's own recommended "write once, test
    locally" pattern.

    Configures Delta Lake's SQL extensions so `spark.read.format("delta")`
    / `df.write.format("delta")` work locally too, matching how the
    same code would run on a real Databricks cluster (Delta is the
    default table format there).

    Raises ImportError with a clear message if pyspark is not
    installed, rather than a confusing stack trace deep inside
    pyspark's own import machinery.
    """
    try:
        from pyspark.sql import SparkSession
    except ImportError as e:
        raise ImportError(
            "pyspark is not installed. It is intentionally not yet a "
            "project dependency (see databricks/README.md) -- install "
            "it (`pip install pyspark delta-spark`) to run lakehouse "
            "code locally."
        ) from e

    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "4")  # small, local-friendly default
        .config("spark.ui.showConsoleProgress", "false")
    )

    try:
        from delta import configure_spark_with_delta_pip
        builder = configure_spark_with_delta_pip(builder)
    except ImportError:
        # delta-spark not installed -- fine for non-Delta transform
        # tests, but any test that actually reads/writes a Delta table
        # will fail with a clear pyspark-level error, not a silent
        # fallback to parquet.
        pass

    return builder.getOrCreate()


def stop_spark_session(spark: "SparkSession") -> None:
    """Explicit, symmetrical teardown -- every test/script that calls
    get_local_spark_session() should call this in a finally block."""
    spark.stop()
