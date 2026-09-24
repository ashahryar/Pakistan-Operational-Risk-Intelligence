"""
databricks/tests/test_canonical_bronze_silver.py

Task 18 (Phase 1 / ADR-0001) -- canonical JSONL -> Spark Bronze -> Spark
Silver, end to end, using real pipeline.canonical.adapters output (not
hand-written mock JSON) as the fixture. SKIPPED (not failed) when
pyspark is not installed -- see databricks/tests/conftest.py. No live
Databricks workspace or AWS credentials are required; all reads/writes
use a pytest `tmp_path` local filesystem directory.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pyspark", reason="pyspark not installed -- see databricks/README.md")

from pipeline.canonical.adapters import adapt_pdma_gauge  # noqa: E402
from pipeline.canonical.geography import build_dict_admin_unit_lookup  # noqa: E402
from pipeline.canonical.output import write_jsonl  # noqa: E402
from databricks.src.bronze.canonical_bronze import load_canonical_to_bronze, write_bronze_delta  # noqa: E402
from databricks.src.silver.canonical_silver import to_silver_gauge  # noqa: E402

INGESTED = "2026-09-24T12:00:00+00:00"


def _canonical_gauge_records():
    lookup = build_dict_admin_unit_lookup({"Rajanpur": 501})
    return adapt_pdma_gauge(
        {
            "source_file": "gauge.pdf",
            "created_at": INGESTED,
            "report_datetime": "2026-07-02T12:00:00",
            "gauges": [
                {"station": "Rajanpur", "river": "Indus", "current_level_ft": "12.5", "discharge_cusecs": "1,250", "flow_status": "Rising"},
                {"station": "Unknown Place", "river": "Chenab", "current_level_ft": None, "discharge_cusecs": None, "flow_status": None},
            ],
        },
        admin_unit_lookup=lookup,
    )


@pytest.fixture
def canonical_gauge_jsonl(tmp_path):
    records = _canonical_gauge_records()
    return write_jsonl(records, tmp_path / "canonical" / "gauge_observation.jsonl")


def test_bronze_schema_matches_explicit_domain_schema(spark, canonical_gauge_jsonl):
    bronze = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation")
    assert "water_level" in bronze.columns
    assert "admin_unit_id" in bronze.columns
    assert bronze.count() == 2


def test_bronze_preserves_provenance_and_geography(spark, canonical_gauge_jsonl):
    bronze = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation")
    rows = {r["station_name"]: r for r in bronze.collect()}

    resolved_row = rows["Rajanpur"]
    assert resolved_row["provenance"]["parser_version"] == "task17-adapter-1.0.0"
    assert resolved_row["admin_unit_id"] == 501
    assert resolved_row["district"] == "Rajanpur"
    assert resolved_row["resolution_status"] == "resolved"

    unresolved_row = rows["Unknown Place"]
    assert unresolved_row["admin_unit_id"] is None
    assert unresolved_row["resolution_status"] == "unresolved"


def test_bronze_null_stays_null_and_typed_numbers_stay_numeric(spark, canonical_gauge_jsonl):
    bronze = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation")
    rows = {r["station_name"]: r for r in bronze.collect()}

    assert rows["Rajanpur"]["water_level"] == 12.5
    assert rows["Rajanpur"]["discharge"] == 1250.0
    assert rows["Unknown Place"]["water_level"] is None
    assert rows["Unknown Place"]["discharge"] is None


def test_silver_types_the_observed_at_timestamp(spark, canonical_gauge_jsonl):
    from pyspark.sql.types import TimestampType

    bronze = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation")
    silver = to_silver_gauge(bronze)

    assert isinstance(silver.schema["observed_at"].dataType, TimestampType)
    row = silver.filter(silver.station_name == "Rajanpur").collect()[0]
    assert row["observed_at"] is not None


def test_silver_duplicate_handling_keeps_one_row_per_logical_key(spark, canonical_gauge_jsonl):
    bronze = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation")
    doubled = bronze.union(bronze)  # simulate the same records appearing twice
    silver = to_silver_gauge(doubled)

    assert silver.count() == 2


def test_bronze_write_is_idempotent_across_repeated_runs(spark, canonical_gauge_jsonl, tmp_path):
    bronze = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation")
    base_path = str(tmp_path / "lakehouse")

    write_bronze_delta(spark, bronze, base_path, "gauge_observation")
    write_bronze_delta(spark, bronze, base_path, "gauge_observation")  # run 2: same input

    from databricks.src.common.io import read_delta

    table = read_delta(spark, f"{base_path}/bronze/gauge_observation")
    assert table.count() == 2  # no duplicate rows from the second run


def test_bronze_output_is_deterministic(spark, canonical_gauge_jsonl):
    first = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation").collect()
    second = load_canonical_to_bronze(spark, str(canonical_gauge_jsonl), "gauge_observation").collect()

    key = lambda rows: sorted(rows, key=lambda r: r["source_record_id"])  # noqa: E731
    assert [r.asDict() for r in key(first)] == [r.asDict() for r in key(second)]
