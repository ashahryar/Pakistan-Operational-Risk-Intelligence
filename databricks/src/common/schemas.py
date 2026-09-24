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
        # Task 19: Tier-1 raw-artifact provenance (see pipeline/canonical/tier1_adapters.py)
        StructField("source_file", StringType(), True),
        StructField("retrieved_at", StringType(), True),
        StructField("sha256", StringType(), True),
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
    from pyspark.sql.types import BooleanType, IntegerType, StringType, StructField, StructType

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
        # Task 19: SUPARCO campaign / FFC GLOF extras
        StructField("glide_number", StringType(), True),
        StructField("campaign_scope", StringType(), True),
        StructField("is_live", BooleanType(), True),
        StructField("resource_count", IntegerType(), True),
        StructField("document_id", StringType(), True),
    ])


def air_quality_observation_schema() -> "StructType":
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("observed_at", StringType(), True),
        StructField("observed_at_basis", StringType(), True),
        StructField("granularity", StringType(), True),
        StructField("station_name", StringType(), True),
        StructField("station_id", StringType(), True),
        StructField("city", StringType(), True),
        StructField("aqi", DoubleType(), True),
        StructField("pm25", DoubleType(), True),
        StructField("pm10", DoubleType(), True),
        StructField("no2", DoubleType(), True),
        StructField("so2", DoubleType(), True),
        StructField("co", DoubleType(), True),
        StructField("o3", DoubleType(), True),
        StructField("category", StringType(), True),
        StructField("dominant_pollutant", StringType(), True),
        StructField("station_count", DoubleType(), True),
        StructField("stations_reporting", StringType(), True),
    ])


def reservoir_observation_schema() -> "StructType":
    from pyspark.sql.types import DoubleType, StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("observed_at", StringType(), True),
        StructField("reservoir_name", StringType(), True),
        StructField("reservoir_name_original", StringType(), True),
        StructField("water_level", DoubleType(), True),
        StructField("unit", StringType(), True),
        StructField("live_storage", DoubleType(), True),
        StructField("storage_unit", StringType(), True),
        StructField("combined_live_storage", DoubleType(), True),
        StructField("source_document", StringType(), True),
    ])


def document_schema() -> "StructType":
    from pyspark.sql.types import IntegerType, StringType, StructField, StructType

    return StructType(_common_fields() + [
        StructField("doc_type", StringType(), True),
        StructField("title", StringType(), True),
        StructField("title_basis", StringType(), True),
        StructField("issuing_organization", StringType(), True),
        StructField("hazard_topic", StringType(), True),
        StructField("publication_date", StringType(), True),
        StructField("report_date", StringType(), True),
        StructField("issued_at", StringType(), True),
        StructField("period_start", StringType(), True),
        StructField("period_end", StringType(), True),
        StructField("pdf_creation_date", StringType(), True),
        StructField("page_count", IntegerType(), True),
        StructField("script", StringType(), True),
        StructField("text", StringType(), True),
        StructField("text_char_count", IntegerType(), True),
        StructField("text_quality_note", StringType(), True),
        StructField("source_document", StringType(), True),
    ])


# One schema per canonical domain that currently has an adapter (Task 17-19).
DOMAIN_SCHEMAS = {
    "air_quality_observation": air_quality_observation_schema,
    "reservoir_observation": reservoir_observation_schema,
    "document": document_schema,
    "weather_observation": weather_observation_schema,
    "rainfall_observation": rainfall_observation_schema,
    "gauge_observation": gauge_observation_schema,
    "disaster_event": disaster_event_schema,
    "hazard_alert": hazard_alert_schema,
}
