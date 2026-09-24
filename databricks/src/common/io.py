"""
databricks/src/common/io.py

Task 18 (Phase 1 / ADR-0001) -- Delta-compatible read/write boundary for
the bronze/silver layers. Uses a configurable base path (never a
hardcoded Databricks workspace path, AWS account ID, S3 credential, or
Unity Catalog name) -- local tests pass a `tmp_path` filesystem
directory; a real deployment would pass an `s3://...` or Unity Catalog
path instead, with no code change.

STATUS: scaffolded. Writes always use `.format("delta")` -- if
delta-spark isn't installed/configured, Spark itself raises a real,
honest error at write time. This module never falls back to Parquet
and calls the result "Delta" -- Task 18 Part 16's explicit requirement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def write_delta(df: "DataFrame", path: str, *, mode: str = "append", partition_by: Sequence[str] | None = None) -> None:
    """
    Writes `df` to `path` as a real Delta table (`.format("delta")`).
    `mode` is explicit at every call site (never a hidden default that
    could silently overwrite bronze history) -- "append" for bronze's
    append-oriented contract (Part 13), "overwrite" only where a caller
    deliberately chooses it for a rebuildable silver table.
    """
    writer = df.write.format("delta").mode(mode)
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.save(path)


def read_delta(spark: "SparkSession", path: str) -> "DataFrame":
    """Reads an existing Delta table at `path`. Raises Spark's own real
    error if the path is not a Delta table -- no silent fallback."""
    return spark.read.format("delta").load(path)


def read_canonical_jsonl(spark: "SparkSession", path: str, schema) -> "DataFrame":
    """
    Reads a Task 17 canonical JSONL file (pipeline/canonical/output.py)
    with an explicit schema (Task 18 Part 17) rather than
    `spark.read.json(path)`'s uncontrolled inference. A field present in
    the file but absent from `schema` is dropped by Spark (documented
    Spark behavior, not a silent data-loss bug specific to this
    module); a field in `schema` but absent from the file is null,
    matching the canonical contract's own "missing stays missing, never
    fabricated" rule.
    """
    return spark.read.schema(schema).json(path)
