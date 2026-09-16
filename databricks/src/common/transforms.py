"""
databricks/src/common/transforms.py

Task 16A (Phase 1 / ADR-0001) -- generic, reusable Spark transformation
helpers that any future bronze/silver/gold module builds on, so those
modules don't each reimplement the same dedup/metadata patterns.

STATUS: scaffolded and unit-tested (see databricks/tests/), but not
yet called from any real bronze/silver/gold pipeline -- there isn't
one yet. Every function here is a plain `DataFrame -> DataFrame`
transformation: no I/O, no `.collect()`, no wall-clock access (a
caller passes `ingested_at` explicitly rather than this module calling
`datetime.now()` itself, keeping every transform deterministic and
testable with a fixed input).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from pyspark.sql import DataFrame


def deduplicate_by_key(df: "DataFrame", key_columns: Sequence[str], order_by: str) -> "DataFrame":
    """
    Keeps exactly one row per unique combination of `key_columns`,
    preferring the row with the greatest `order_by` value (e.g. the
    latest `ingested_at` or `scraped_at`) -- the standard bronze/silver
    dedup pattern for a source that can legitimately be re-ingested
    (Task 15's raw acquisition already guarantees the underlying files
    are immutable and deduplicated by checksum; this is the analogous
    guarantee one layer up, for the structured records built from
    them).

    Uses a window function, not `.dropDuplicates()` (which keeps an
    arbitrary row, not the latest one) and not `.collect()` (stays a
    distributed DataFrame operation throughout).
    """
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    window = Window.partitionBy(*key_columns).orderBy(F.col(order_by).desc())

    return (
        df.withColumn("_rn", F.row_number().over(window))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )


def add_ingestion_metadata(df: "DataFrame", *, source: str, ingested_at: datetime, parser_version: str) -> "DataFrame":
    """
    Attaches the provenance columns every bronze table's contract
    requires (databricks/README.md's bronze layer description):
    `_source`, `_ingested_at`, `_parser_version`. `ingested_at` is
    passed in by the caller (not computed here) so this function
    stays deterministic and testable -- calling it twice with the same
    inputs always produces the same output.
    """
    from pyspark.sql import functions as F

    return (
        df.withColumn("_source", F.lit(source))
        .withColumn("_ingested_at", F.lit(ingested_at))
        .withColumn("_parser_version", F.lit(parser_version))
    )


def assert_no_fully_null_rows(df: "DataFrame", required_columns: Sequence[str]) -> "DataFrame":
    """
    Silver-layer guard, matching CLAUDE.md rule 7 ("never fabricate a
    value") extended to the lakehouse: a row missing every one of its
    `required_columns` is not a valid observation, and this raises
    rather than silently letting it through. Rows missing only *some*
    required columns are not this function's concern (that is a
    per-dataset schema-validation decision, deliberately left to each
    real silver module once one exists) -- this only catches the
    all-null degenerate case that indicates a genuine upstream bug.
    """
    from pyspark.sql import functions as F

    condition = None
    for column in required_columns:
        col_is_null = F.col(column).isNull()
        condition = col_is_null if condition is None else (condition & col_is_null)

    if condition is None:
        return df

    fully_null_count = df.filter(condition).count()
    if fully_null_count > 0:
        raise ValueError(
            f"{fully_null_count} row(s) have every one of {list(required_columns)} "
            f"NULL -- refusing to pass a fully-null observation through to silver"
        )

    return df
