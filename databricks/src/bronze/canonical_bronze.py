"""
databricks/src/bronze/canonical_bronze.py

Task 18 (Phase 1 / ADR-0001) -- canonical JSONL -> Spark Bronze.

Bronze is a near-verbatim, append-oriented, traceable copy of the Task
17 canonical output: every provenance field, geography field, and
domain field is preserved exactly as pipeline/canonical/adapters.py
produced it (Part 13 -- "Bronze should preserve ... Do NOT silently
lose source fields"). The only addition is deduplication by logical
record identity, which makes repeated runs over the same canonical
input idempotent (Part 20) without inventing a random UUID.

STATUS: scaffolded, not exercised against real data -- pyspark is not
currently installed (see databricks/README.md). Every function is a
plain, testable `DataFrame -> DataFrame` (or path -> DataFrame)
transformation with lazy imports, matching Task 16A's established
pattern in databricks/src/common/{spark_session,transforms}.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from databricks.src.common.io import read_canonical_jsonl, read_delta, write_delta
from databricks.src.common.transforms import deduplicate_by_key
from databricks.src.common.schemas import DOMAIN_SCHEMAS

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

# Deterministic record identity for bronze deduplication (Part 20):
# domain + source + source_record_id is exactly the same identity Task
# 17's own canonical adapters already construct source_record_id from
# (see pipeline/canonical/adapters.py's f"{report_id}:{section}:{index}"
# style keys) -- reused, not reinvented. Ties broken by the latest
# ingestion_timestamp, matching databricks/src/common/transforms.py's
# existing deduplicate_by_key() dedup pattern from Task 16A.
BRONZE_KEY_COLUMNS = ("domain", "source", "source_record_id")
BRONZE_ORDER_BY = "ingestion_timestamp"


def load_canonical_to_bronze(spark: "SparkSession", jsonl_path: str, domain: str) -> "DataFrame":
    """
    Reads one domain's canonical JSONL file with its explicit schema
    (never `spark.read.json` inference) and deduplicates it into a
    bronze-ready DataFrame. Does not write anything -- callers combine
    this with `write_bronze_delta()` or inspect the DataFrame directly
    in tests.
    """
    if domain not in DOMAIN_SCHEMAS:
        raise ValueError(f"no bronze schema registered for domain {domain!r}; see databricks/src/common/schemas.py")
    schema = DOMAIN_SCHEMAS[domain]()
    df = read_canonical_jsonl(spark, jsonl_path, schema)
    return deduplicate_by_key(df, BRONZE_KEY_COLUMNS, BRONZE_ORDER_BY)


def write_bronze_delta(spark: "SparkSession", df: "DataFrame", base_path: str, domain: str) -> str:
    """
    Writes `df` to the bronze Delta table for `domain`, partitioned by
    `source` (Part 13's "append-oriented and traceable"). `base_path`
    is caller-supplied (a tmp_path in tests, an s3://.../bronze path in
    a real deployment) -- never hardcoded here.

    Idempotent ACROSS runs (Part 20), not just within one load: if a
    table already exists at the target path, this reads it, unions the
    new rows in, and re-deduplicates on BRONZE_KEY_COLUMNS before an
    overwrite -- so re-running the exact same canonical input never
    creates duplicate rows, and a genuinely updated record (same key,
    newer ingestion_timestamp) correctly replaces the older one rather
    than being appended alongside it.
    """
    path = f"{base_path.rstrip('/')}/bronze/{domain}"
    try:
        existing = read_delta(spark, path)
        combined = existing.unionByName(df, allowMissingColumns=True)
    except Exception:
        # No existing Delta table at this path yet -- first write.
        combined = df
    deduped = deduplicate_by_key(combined, BRONZE_KEY_COLUMNS, BRONZE_ORDER_BY)
    write_delta(deduped, path, mode="overwrite", partition_by=("source",))
    return path
