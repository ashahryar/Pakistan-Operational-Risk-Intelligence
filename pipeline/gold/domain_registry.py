"""Task 21 -- authoritative Gold/analytics dataset registry.

One entry per Gold dataset: its source Silver domain(s), grain, business key, geography and time
handling, and which fields are required vs. optional vs. derived. This is documentation plus a
cross-checkable contract (see tests/gold/test_gold_registry.py) -- it does not re-implement
transformation logic (see pipeline/gold/transforms.py) and does not duplicate
pipeline/canonical/domain_registry.py, which it imports from.

Every field named below was verified against real canonical output on disk
(data/parsed/canonical/<domain>/*.jsonl) before this registry was written -- see
docs/architecture/GOLD_ANALYTICS_STATUS.md for the exact field-presence findings.
"""

from __future__ import annotations

from typing import NamedTuple

from pipeline.canonical.domain_registry import DOMAIN_REGISTRY


class GoldSpec(NamedTuple):
    name: str
    source_silver_domains: tuple[str, ...]
    grain: str
    business_key: tuple[str, ...]
    geography_level: str          # 'district' | 'province' | 'station' | 'reservoir' | 'none' | 'event'
    time_field: str                # the field on the Gold row holding the grain's date/time
    observation_time_basis: str    # how time_field was derived -- see STEP 5
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    derived_fields: tuple[str, ...]
    null_behavior: str
    provenance_strategy: str
    aggregation_rule: str = "pass-through (no aggregation; Bronze-identity dedup only)"


GOLD_REGISTRY: dict[str, GoldSpec] = {
    "gold_weather_daily": GoldSpec(
        "gold_weather_daily", ("weather_observation",), "one geography (district if resolved, else the "
        "original location text) x one calendar date", ("geography_key", "date"), "district",
        "date", "source_observed (PMD's own scraped_at)",
        ("geography_key", "date", "resolution_status", "observation_count"),
        ("admin_unit_id", "district", "location_original", "temperature_avg", "temperature_min",
         "temperature_max", "humidity_avg", "weather_condition", "precipitation_avg", "wind_speed_avg"),
        ("observation_count", "temperature_avg", "temperature_min", "temperature_max", "humidity_avg"),
        "a metric absent from every contributing record for that geography/date stays NULL, never 0",
        "provenance.sources lists every distinct (source, source_record_id) folded into the row",
        "mean/min/max over same geography+date observations (Step 7: mathematically justified daily aggregation)",
    ),
    "gold_rainfall_daily": GoldSpec(
        "gold_rainfall_daily", ("rainfall_observation",), "one station/location x one calendar date",
        ("station_name", "date"), "station",
        "date", "source_observed (PDMA's own report_date)",
        ("station_name", "date", "resolution_status", "observation_count", "rainfall_total"),
        ("admin_unit_id", "district", "location_original", "unit"),
        ("observation_count", "rainfall_total", "rainfall_avg"),
        "rainfall_total/avg is NULL only when every contributing observation had a NULL amount",
        "provenance.sources lists every distinct (source, source_record_id) folded into the row",
        "sum + mean over same station+date observations",
    ),
    "gold_gauge_daily": GoldSpec(
        "gold_gauge_daily", ("gauge_observation",), "one gauge/station x one calendar date",
        ("station_name", "date"), "station",
        "date", "source_observed (PDMA's own report_datetime)",
        ("station_name", "date", "resolution_status", "observation_count"),
        ("admin_unit_id", "district", "river_name", "water_level_min", "water_level_max", "water_level_avg",
         "discharge_min", "discharge_max", "discharge_avg"),
        ("water_level_min", "water_level_max", "water_level_avg", "discharge_min", "discharge_max", "discharge_avg"),
        "min/max/avg computed only over the non-null observations for that station+date; NULL if all were null "
        "(CRITICAL: an unresolved station's admin_unit_id stays NULL -- never a guessed district)",
        "provenance.sources lists every distinct (source, source_record_id) folded into the row",
        "min/max/mean over same station+date observations",
    ),
    "gold_air_quality": GoldSpec(
        "gold_air_quality", ("air_quality_observation",), "one AQI station-or-district x one "
        "observation/retrieval date", ("geography_key", "date", "granularity"), "district",
        "date", "mixed -- carries the source record's own observed_at_basis (retrieved_at for station "
        "snapshots, calendar_date for the daily city calendar)",
        ("geography_key", "date", "granularity", "resolution_status", "observation_count"),
        ("admin_unit_id", "district", "station_name", "aqi_avg", "pm25_avg", "pm10_avg", "no2_avg",
         "so2_avg", "co_avg", "o3_avg"),
        ("observation_count", "aqi_avg"),
        "a pollutant absent from every contributing record stays NULL, never 0 or an invented category",
        "provenance.sources lists every distinct (source, source_record_id) folded into the row",
        "mean over same geography+date+granularity observations; station-snapshot and daily-calendar "
        "granularities are kept as separate rows (different grains), never merged",
    ),
    "gold_disaster_events": GoldSpec(
        "gold_disaster_events", ("disaster_event",), "one normalized disaster event record (no aggregation)",
        ("source", "event_id"), "province",
        "event_date", "source_observed (NDMA's own report_date)",
        ("event_id", "event_date", "source", "resolution_status"),
        ("admin_unit_id", "province", "district", "deaths", "injured", "affected_population",
         "houses_damaged", "roads_damaged", "bridges_damaged", "rescued", "evacuated"),
        (), "a casualty/damage figure absent from the source stays NULL, never 0",
        "provenance passed through unchanged from the canonical record",
        "pass-through; Bronze-identity (domain, source, source_record_id) dedup only, per Task 18/20",
    ),
    "gold_hazard_alerts": GoldSpec(
        "gold_hazard_alerts", ("hazard_alert",), "one alert record (no aggregation)",
        ("source", "alert_id"), "province",
        "issued_at", "source_observed (the alert's own issued_at/scraped_at where present)",
        ("alert_id", "source", "resolution_status"),
        ("admin_unit_id", "province", "district", "hazard_type", "issued_at", "valid_from", "valid_until",
         "severity", "title", "description"),
        (), "severity/hazard_type stay NULL when the source does not state one -- never ranked or inferred",
        "provenance passed through unchanged from the canonical record",
        "pass-through; Bronze-identity dedup only",
    ),
    "gold_reservoir_status": GoldSpec(
        "gold_reservoir_status", ("reservoir_observation",), "one reservoir x one observation date/time "
        "(no aggregation)", ("reservoir_name", "observed_at"), "none (geography intentionally not attempted)",
        "observed_at", "source_observed (FFC's own homepage sentence)",
        ("reservoir_name", "observed_at", "source"),
        ("water_level", "live_storage", "combined_live_storage"),
        (), "inflow/outflow/capacity are never populated -- the source page states none of them",
        "provenance passed through unchanged from the canonical record",
        "pass-through; Bronze-identity dedup only",
    ),
    "gold_documents": GoldSpec(
        "gold_documents", ("document",), "one source document (no aggregation)",
        ("source", "document_id"), "none",
        "effective_date", "mixed -- report_date, then publication_date, then issued_at, then "
        "period_start, in that preference order, whichever the source actually populated first; "
        "a document with none of those keeps effective_date NULL rather than falling back to "
        "pdf_creation_date (metadata, not a publication claim)",
        ("document_id", "source", "source_file", "sha256"),
        ("title", "doc_type", "effective_date", "effective_date_basis", "issuing_organization", "hazard_topic"),
        (), "title/publication date stay NULL when the source PDF does not state one",
        "source_file/sha256/retrieved_at/parser_version/normalization_version passed through unchanged",
        "pass-through; Bronze-identity dedup only",
    ),
    "gold_operational_risk_inputs": GoldSpec(
        "gold_operational_risk_inputs", ("rainfall_observation", "gauge_observation", "air_quality_observation",
        "weather_observation", "hazard_alert", "disaster_event"), "one RESOLVED geography x one calendar date "
        "(Step 8: only rows with a real admin_unit_id are aligned -- unresolved signals are never forced in)",
        ("admin_unit_id", "date"), "district-or-province (whatever each source signal actually resolved to)",
        "date", "source_observed (each aligned signal keeps its own domain's basis)",
        ("admin_unit_id", "date"),
        ("rainfall_total", "gauge_discharge_avg", "gauge_water_level_avg", "aqi_avg", "temperature_avg",
         "active_hazard_alert_count", "disaster_event_count"),
        (), "a signal with no resolved-geography observation for that date stays NULL -- "
        "NEVER treated as zero/no-risk (Step 8's explicit rule)",
        "coverage.<signal> records which domains actually contributed a value for that geography/date",
        "NO numeric risk score is computed anywhere in this dataset -- see docs/architecture/GOLD_ANALYTICS_STATUS.md",
    ),
}


def assert_gold_sources_exist_in_silver_registry() -> list[str]:
    """Every Gold dataset's source_silver_domains must be real, already-validated Silver domains
    (pipeline.canonical.domain_registry.DOMAIN_REGISTRY) -- never an invented upstream."""
    problems = []
    for name, spec in GOLD_REGISTRY.items():
        for domain in spec.source_silver_domains:
            if domain not in DOMAIN_REGISTRY:
                problems.append(f"{name}: source Silver domain {domain!r} is not in DOMAIN_REGISTRY")
    return problems
