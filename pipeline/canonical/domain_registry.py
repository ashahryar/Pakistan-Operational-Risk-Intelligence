"""Task 20 -- authoritative canonical domain registry.

Single source of truth describing every currently supported canonical domain: which fields are
required/optional, their types, the timestamp and geography fields, the provenance fields, and
the deduplication key. This module does NOT re-implement validation (see contracts.py), Bronze
schemas (see databricks/src/common/schemas.py) or Silver typing (see
databricks/src/silver/canonical_silver.py) -- it documents and cross-checks them, so drift
between those three places is caught by tests/tier1/test_domain_registry.py instead of silently
accumulating.

Every field named below is verified against the actual adapter code in
pipeline/canonical/adapters.py and pipeline/canonical/tier1_adapters.py, not invented.
"""

from __future__ import annotations

from typing import NamedTuple

# The same deduplication identity every Bronze/Silver module already uses
# (databricks/src/bronze/canonical_bronze.py::BRONZE_KEY_COLUMNS/BRONZE_ORDER_BY) -- documented
# here, not redefined. It is correct for every current domain: every adapter constructs
# source_record_id to already be unique within (domain, source) for one logical observation
# (e.g. NDMA "<report_id>:<section>:<index>", PDMA gauge "<source_file>:<row_index>", a Tier-1
# artifact's own natural id) -- no domain currently needs a stronger key.
DEDUPLICATION_KEY = ("domain", "source", "source_record_id")
DEDUPLICATION_TIE_BREAK = "ingestion_timestamp"  # latest wins

PROVENANCE_FIELDS = ("source_organization", "source_dataset", "source_document", "source_url_or_path",
                     "parser_version", "normalization_version")
# Tier-1 adapters (pipeline/canonical/tier1_adapters.py::_tier1_base) additionally populate these;
# Task 17 legacy adapters (NDMA/PDMA/PMD) do not have a raw-artifact manifest to draw them from.
TIER1_ONLY_PROVENANCE_FIELDS = ("source_file", "retrieved_at", "sha256")

GEOGRAPHY_FIELDS = ("location_original", "admin_unit_id", "admin_unit_key", "resolution_status",
                    "resolution_method", "resolution_notes")


class DomainSpec(NamedTuple):
    domain: str
    source_adapters: tuple[str, ...]      # functions in adapters.py / tier1_adapters.py
    timestamp_fields: tuple[str, ...]     # fields eligible for Silver's to_timestamp cast
    required_timestamp_field: str | None  # the one contracts.py::validate_record requires non-null
    required_non_null_any: tuple[str, ...]  # Silver's assert_no_fully_null_rows guard
    geography_applicable: bool            # False = enrich_location is intentionally never called
    notes: str = ""


DOMAIN_REGISTRY: dict[str, DomainSpec] = {
    "weather_observation": DomainSpec(
        "weather_observation", ("adapt_pmd_daily",), ("observed_at",), "observed_at",
        ("temperature", "humidity", "weather_condition"), True,
        "PMD daily forecast per city; geography resolved against DISTRICTS via city name.",
    ),
    "rainfall_observation": DomainSpec(
        "rainfall_observation", ("adapt_pdma_rainfall",), ("observed_at",), "observed_at",
        ("rainfall_amount",), True,
        "PDMA rainfall report rows; geography resolved against DISTRICTS via station name.",
    ),
    "gauge_observation": DomainSpec(
        "gauge_observation", ("adapt_pdma_gauge",), ("observed_at",), "observed_at",
        ("water_level", "discharge"), True,
        "PDMA river gauge rows; geography resolved against DISTRICTS via station name.",
    ),
    "disaster_event": DomainSpec(
        "disaster_event", ("adapt_ndma",), ("event_date",), "event_date",
        ("deaths", "injured", "houses_damaged", "roads_damaged", "bridges_damaged", "rescued"), True,
        "NDMA sitrep casualties/damage/rescue rows; geography resolved against PROVINCES.",
    ),
    "hazard_alert": DomainSpec(
        "hazard_alert", ("adapt_pmd_alerts", "adapt_pmd_weekly", "adapt_suparco_campaigns", "adapt_glof_alerts"),
        ("issued_at", "valid_from", "valid_until"), "issued_at", ("title", "description"), True,
        "PMD alerts/weekly outlook, SUPARCO campaigns (no location) and FFC GLOF alerts "
        "(province-level, from the alert text's opening paragraph only).",
    ),
    "air_quality_observation": DomainSpec(
        "air_quality_observation", ("adapt_epa_stations", "adapt_epa_calendar"), ("observed_at",), "observed_at",
        ("aqi", "pm25", "pm10", "no2", "so2", "co", "o3"), True,
        "EPA Punjab station snapshots and daily city calendar; geography resolved against DISTRICTS.",
    ),
    "reservoir_observation": DomainSpec(
        "reservoir_observation", ("adapt_ffc_reservoir",), ("observed_at",), "observed_at",
        ("water_level", "live_storage"), False,
        "FFC homepage reservoir levels; geography deliberately NOT attempted (the reservoir name "
        "'Mangla' would otherwise false-match the Task 10 district entry 'Mangla').",
    ),
    "document": DomainSpec(
        "document", ("adapt_documents",),
        ("publication_date", "report_date", "issued_at", "period_start", "period_end"), None,
        ("text",), False,
        "FFC DFSR/GLOF/press-release and PMD/NDMC bulletin narrative documents; no single required "
        "timestamp field (contracts.py intentionally has none for 'document'); geography not attempted.",
    ),
}


def assert_registry_matches_contracts() -> list[str]:
    """Cross-checks this registry against contracts.py/schemas.py/canonical_silver.py. Returns a
    list of mismatch descriptions (empty = consistent). Pyspark-free: only imports plain
    module-level Python constants, never a StructType-constructing function."""
    from pipeline.canonical.contracts import DOMAINS
    from databricks.src.common.schemas import DOMAIN_SCHEMAS
    from databricks.src.silver.canonical_silver import _REQUIRED_NON_NULL_ANY, _TIMESTAMP_COLUMNS

    problems = []
    registry_domains = set(DOMAIN_REGISTRY)
    if registry_domains != DOMAINS:
        problems.append(f"registry domains {registry_domains} != contracts.DOMAINS {DOMAINS}")
    if registry_domains != set(DOMAIN_SCHEMAS):
        problems.append(f"registry domains {registry_domains} != Bronze DOMAIN_SCHEMAS {set(DOMAIN_SCHEMAS)}")
    for domain, spec in DOMAIN_REGISTRY.items():
        if set(spec.timestamp_fields) != set(_TIMESTAMP_COLUMNS.get(domain, ())):
            problems.append(f"{domain}: timestamp_fields {spec.timestamp_fields} != Silver "
                            f"_TIMESTAMP_COLUMNS {_TIMESTAMP_COLUMNS.get(domain)}")
        if set(spec.required_non_null_any) != set(_REQUIRED_NON_NULL_ANY.get(domain, ())):
            problems.append(f"{domain}: required_non_null_any mismatch vs Silver _REQUIRED_NON_NULL_ANY")
    return problems
