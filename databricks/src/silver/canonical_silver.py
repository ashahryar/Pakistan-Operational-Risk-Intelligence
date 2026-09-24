"""
databricks/src/silver/canonical_silver.py

Task 18 (Phase 1 / ADR-0001) -- bronze -> silver: typed, cleaned,
analytics-ready canonical records (Part 14).

Silver reuses the same explicit schemas bronze already read with (the
bronze DataFrame is already typed by databricks/src/common/schemas.py
-- Part 15's "reuse shared definitions/contracts" requirement, not a
second set of type-casting rules). What silver adds on top:
  - timestamp columns parsed from the canonical layer's ISO/date
    strings into real Spark TimestampType/DateType columns
  - a not-fully-null guard on each domain's core measurement/event
    columns (reusing databricks/src/common/transforms.py's
    assert_no_fully_null_rows from Task 16A, not a new guard)
  - the same BRONZE_KEY_COLUMNS-based deduplication, so silver is
    idempotent for the same reason bronze is (Part 20)

STATUS: scaffolded, not exercised against real data -- pyspark is not
currently installed. Lazy imports throughout, matching Task 16A/18's
established pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from databricks.src.bronze.canonical_bronze import BRONZE_KEY_COLUMNS, BRONZE_ORDER_BY
from databricks.src.common.transforms import assert_no_fully_null_rows, deduplicate_by_key

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

# Per-domain: which string column(s) become typed timestamps, and which
# core columns must not ALL be null for a row to be a real observation
# (Task 18 Part 14/19 -- reuses assert_no_fully_null_rows's existing
# "fully null = not a valid observation" guard, not a new rule).
_TIMESTAMP_COLUMNS = {
    "weather_observation": ["observed_at"],
    "rainfall_observation": ["observed_at"],
    "gauge_observation": ["observed_at"],
    "disaster_event": ["event_date"],
    "hazard_alert": ["issued_at", "valid_from", "valid_until"],
    "air_quality_observation": ["observed_at"],
    "reservoir_observation": ["observed_at"],
    "document": ["publication_date", "report_date", "issued_at", "period_start", "period_end"],
}

_REQUIRED_NON_NULL_ANY = {
    "weather_observation": ["temperature", "humidity", "weather_condition"],
    "rainfall_observation": ["rainfall_amount"],
    "gauge_observation": ["water_level", "discharge"],
    "disaster_event": ["deaths", "injured", "houses_damaged", "roads_damaged", "bridges_damaged", "rescued"],
    "hazard_alert": ["title", "description"],
    "air_quality_observation": ["aqi", "pm25", "pm10", "no2", "so2", "co", "o3"],
    "reservoir_observation": ["water_level", "live_storage"],
    "document": ["text"],
}


def _to_timestamp(df: "DataFrame", columns: list[str]) -> "DataFrame":
    """
    Casts each ISO/date string column to Spark TimestampType via
    `to_timestamp`. A string that doesn't parse becomes Spark's own
    null (never a fabricated fallback date) -- matching Task 17's own
    normalize_timestamp() contract of "unparseable stays null".
    """
    from pyspark.sql import functions as F

    for column in columns:
        df = df.withColumn(column, F.to_timestamp(F.col(column)))
    return df


def to_silver(bronze_df: "DataFrame", domain: str) -> "DataFrame":
    """
    Transforms one domain's bronze DataFrame into its silver form:
    typed timestamps, deduplicated by the same logical identity bronze
    uses, and guarded against fully-null observation rows. Numeric
    fields are already typed by the explicit bronze schema (Part 15 --
    no second numeric-casting pass here).
    """
    if domain not in _TIMESTAMP_COLUMNS:
        raise ValueError(f"no silver transformation registered for domain {domain!r}")

    df = _to_timestamp(bronze_df, _TIMESTAMP_COLUMNS[domain])
    df = deduplicate_by_key(df, BRONZE_KEY_COLUMNS, BRONZE_ORDER_BY)

    required = _REQUIRED_NON_NULL_ANY.get(domain)
    if required:
        # assert_no_fully_null_rows raises if EVERY one of `required`
        # is null for some row -- a partially-populated row (e.g. only
        # `deaths` known) is a legitimate observation and passes
        # through untouched, consistent with CLAUDE.md rule 7.
        df = assert_no_fully_null_rows(df, required)

    return df


def to_silver_weather(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "weather_observation")


def to_silver_rainfall(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "rainfall_observation")


def to_silver_gauge(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "gauge_observation")


def to_silver_disaster_events(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "disaster_event")


def to_silver_alerts(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "hazard_alert")


def to_silver_air_quality(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "air_quality_observation")


def to_silver_reservoir(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "reservoir_observation")


def to_silver_documents(bronze_df: "DataFrame") -> "DataFrame":
    return to_silver(bronze_df, "document")
