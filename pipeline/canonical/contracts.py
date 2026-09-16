"""Versioned canonical contracts. Optional source fields remain ``None``."""

from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "1.0.0"
NORMALIZATION_VERSION = "1.0.0"
REQUIRED = {"source", "source_record_id", "provenance", "ingestion_timestamp"}

DOMAINS = {
    "weather_observation", "rainfall_observation", "gauge_observation", "disaster_event", "hazard_alert", "air_quality_observation",
}


def validate_record(record: dict[str, Any]) -> list[str]:
    errors = []
    if record.get("domain") not in DOMAINS:
        errors.append("invalid_domain")
    for field in REQUIRED:
        if record.get(field) in (None, "", {}):
            errors.append(f"missing_{field}")
    timestamp_field = {
        "weather_observation": "observed_at",
        "rainfall_observation": "observed_at",
        "gauge_observation": "observed_at",
        "disaster_event": "event_date",
        "hazard_alert": "issued_at",
        "air_quality_observation": "observed_at",
    }.get(record.get("domain"))
    if timestamp_field and record.get(timestamp_field) is None:
        errors.append(f"missing_{timestamp_field}")
    provenance = record.get("provenance") or {}
    for field in ("source_organization", "source_dataset", "parser_version", "normalization_version"):
        if not provenance.get(field):
            errors.append(f"missing_provenance_{field}")
    for field, value in record.items():
        if field in {"latitude", "longitude", "temperature", "humidity", "pressure", "wind_speed", "wind_direction", "precipitation", "rainfall_amount", "water_level", "discharge", "deaths", "injured", "affected_population", "houses_damaged", "roads_damaged", "bridges_damaged", "crops_affected", "livestock_affected", "rescued", "evacuated", "aqi", "pm25", "pm10", "no2", "so2", "co", "o3"} and value is not None and not isinstance(value, (int, float)):
            errors.append(f"invalid_numeric_{field}")
    if record.get("admin_unit_id") is not None and not isinstance(record["admin_unit_id"], int):
        errors.append("invalid_admin_unit_id")
    return errors
