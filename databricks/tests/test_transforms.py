"""
databricks/tests/test_transforms.py

Task 16A (Phase 1 / ADR-0001) -- tests for the generic Spark
transformation helpers in databricks/src/common/transforms.py.
SKIPPED (not failed) when pyspark is not installed -- see
databricks/tests/conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("pyspark", reason="pyspark not installed -- see databricks/README.md")

from databricks.src.common.transforms import (  # noqa: E402
    add_ingestion_metadata,
    assert_no_fully_null_rows,
    deduplicate_by_key,
)


def test_deduplicate_by_key_keeps_the_latest_row_per_key(spark):
    df = spark.createDataFrame(
        [
            ("Lahore", "2026-09-01", 30.0),
            ("Lahore", "2026-09-02", 34.0),  # latest for Lahore -- should survive
            ("Karachi", "2026-09-01", 28.0),
        ],
        ["city", "observed_date", "temperature"],
    )

    result = deduplicate_by_key(df, key_columns=["city"], order_by="observed_date")
    rows = {r["city"]: r["temperature"] for r in result.collect()}

    assert rows == {"Lahore": 34.0, "Karachi": 28.0}


def test_deduplicate_by_key_is_a_no_op_when_no_duplicates_exist(spark):
    df = spark.createDataFrame(
        [("Lahore", "2026-09-01", 30.0), ("Karachi", "2026-09-01", 28.0)],
        ["city", "observed_date", "temperature"],
    )

    result = deduplicate_by_key(df, key_columns=["city"], order_by="observed_date")

    assert result.count() == 2


def test_add_ingestion_metadata_is_deterministic(spark):
    df = spark.createDataFrame([("Lahore",)], ["city"])
    fixed_time = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)

    result_1 = add_ingestion_metadata(df, source="pmd", ingested_at=fixed_time, parser_version="1.0.0")
    result_2 = add_ingestion_metadata(df, source="pmd", ingested_at=fixed_time, parser_version="1.0.0")

    assert result_1.collect() == result_2.collect()

    row = result_1.collect()[0]
    assert row["_source"] == "pmd"
    assert row["_parser_version"] == "1.0.0"


def test_assert_no_fully_null_rows_passes_valid_data_through_unchanged(spark):
    df = spark.createDataFrame(
        [("Lahore", 30.0), ("Karachi", None)],
        ["city", "temperature"],
    )

    result = assert_no_fully_null_rows(df, required_columns=["city", "temperature"])

    assert result.count() == 2


def test_assert_no_fully_null_rows_raises_on_a_fully_null_row(spark):
    df = spark.createDataFrame(
        [("Lahore", 30.0), (None, None)],
        ["city", "temperature"],
    )

    with pytest.raises(ValueError, match="fully-null"):
        assert_no_fully_null_rows(df, required_columns=["city", "temperature"])
