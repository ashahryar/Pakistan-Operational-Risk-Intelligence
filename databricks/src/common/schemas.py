"""
databricks/src/common/schemas.py

Task 18 (Phase 1 / ADR-0001) -- explicit Spark schemas for the Task 17
canonical JSONL domains, so bronze reads never rely on
`spark.read.json(...)`'s uncontrolled type inference for a production
contract (Task 18 Part 17's explicit requirement).

STATUS: scaffolded, not exercised against real data -- pyspark is not
currently installed (see databricks/README.md). Imports are lazy
(inside each function), so importing this module never requires
pyspark; only calling one of these functions does.

Every schema mirrors the field names pipeline/canonical/adapters.py
actually emits (Task 17/18) -- nothing here is invented beyond what the
canonical layer already produces. Fields are nullable=True throughout:
a missing field is a genuinely missing value (never fabricated), never
a schema violation at the bronze layer -- bronze's job is to preserve
what the canonical layer produced, not to enforce completeness (that is
silver's job, see databricks/src/silver/canonical_silver.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql.types import StructType


def _provenance_struct():
    from pyspark.sql.types import StringType, StructField, StructType

    return StructType([
        StructField("source_organization", StringType(), True),
        StructField("source_dataset", StringType(), True),
        StructField("source_document", StringType(), True),
        StructField("source_url_or_path", StringType(), True),
        StructField("parser_version", StringType(), True),
        StructField("normalization_version", StringType(), True),
    ])


def _common_fields():
    """
    Fields every canonical domain carries, per pipeline/canonical/adapters.py::_base
    and pipeline/canonical/geography.py::enrich_location. Shared so each
    domain schema below doesn't repeat this list.
    """
    from pyspark.sql.types import IntegerType, StringType, StructField

    return [
        StructField("domain", StringType(), True),
        StructField("source", StringType(), True),
        StructField("source_record_id", StringType(), True),
        StructField("ingestion_timestamp", StringType(), True),
        StructField("provenance", _provenance_struct(), True),
        # geography enrichment (Task 18) -- see pipeline/canonical/geography.py
        StructField("location_original", StringType(), True),
        StructField("admin_unit_id", IntegerType(), True),
        StructField("admin_unit_key", StringType(), True),
        StructField("resolution_status", StringType(), True),
        StructField("resolution_method", StringType(), True),
        StructField("resolution_notes", StringType(), True),
        StructField("province", StringType(), True),
        StructField("district", StringType(), True),
        StructField("tehsil", StringType(), True),
        StructField("locality", StringType(), True),
    ]


def weather_observation_schema() -> "StructType":
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("observed_at", StringType(), True),
        StructField("location_name", StringType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True),
        StructField("temperature", DoubleType(), True),
        StructField("humidity", DoubleType(), True),
        StructField("pressure", DoubleType(), True),
        StructField("wind_speed", DoubleType(), True),
        StructField("wind_direction", StringType(), True),
        StructField("precipitation", DoubleType(), True),
        StructField("weather_condition", StringType(), True),
        StructField("source_document", StringType(), True),
    ])


def rainfall_observation_schema() -> "StructType":
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("observed_at", StringType(), True),
        StructField("station_name", StringType(), True),
        StructField("station_id", StringType(), True),
        StructField("rainfall_amount", DoubleType(), True),
        StructField("rainfall_period", StringType(), True),
        StructField("unit", StringType(), True),
        StructField("source_document", StringType(), True),
    ])


def gauge_observation_schema() -> "StructType":
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("observed_at", StringType(), True),
        StructField("station_name", StringType(), True),
        StructField("station_id", StringType(), True),
        StructField("river_name", StringType(), True),
        StructField("water_level", DoubleType(), True),
        StructField("discharge", DoubleType(), True),
        StructField("status", StringType(), True),
        StructField("unit", StringType(), True),
        StructField("discharge_unit", StringType(), True),
        StructField("source_document", StringType(), True),
    ])


def disaster_event_schema() -> "StructType":
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("event_type", StringType(), True),
        StructField("event_name", StringType(), True),
        StructField("event_date", StringType(), True),
        StructField("deaths", DoubleType(), True),
        StructField("injured", DoubleType(), True),
        StructField("affected_population", DoubleType(), True),
        StructField("houses_damaged", DoubleType(), True),
        StructField("infrastructure_damage", StringType(), True),
        StructField("roads_damaged", DoubleType(), True),
        StructField("bridges_damaged", DoubleType(), True),
        StructField("crops_affected", DoubleType(), True),
        StructField("livestock_affected", DoubleType(), True),
        StructField("rescued", DoubleType(), True),
        StructField("evacuated", DoubleType(), True),
        StructField("source_document", StringType(), True),
    ])


def hazard_alert_schema() -> "StructType":
    from pyspark.sql.types import StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("hazard_type", StringType(), True),
        StructField("issued_at", StringType(), True),
        StructField("valid_from", StringType(), True),
        StructField("valid_until", StringType(), True),
        StructField("severity", StringType(), True),
        StructField("affected_area", StringType(), True),
        StructField("title", StringType(), True),
        StructField("description", StringType(), True),
        StructField("source_document", StringType(), True),
    ])


# AQI remains contract-only (Task 17/18): no parsed AQI adapter exists
# yet, so no schema is defined here for it -- adding one would invite
# `spark.read` against a domain nothing ever produces.
DOMAIN_SCHEMAS = {
    "weather_observation": weather_observation_schema,
    "rainfall_observation": rainfall_observation_schema,
    "gauge_observation": gauge_observation_schema,
    "disaster_event": disaster_event_schema,
    "hazard_alert": hazard_alert_schema,
}
