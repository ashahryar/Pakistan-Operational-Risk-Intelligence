"""Adapters from the deliberately unchanged Task 8 parser outputs."""

from __future__ import annotations

from typing import Any, Callable

from scripts.geo.canonical_data import DISTRICTS, PROVINCES

from .contracts import NORMALIZATION_VERSION, validate_record
from .geography import AdminUnitLookup, enrich_location
from .normalization import normalize_number, normalize_string, normalize_timestamp

PARSER_VERSION = "task17-adapter-1.0.0"


def _geo(value: Any, candidates: list[dict], *, hierarchy_field: str | None = None,
         admin_unit_lookup: AdminUnitLookup | None = None) -> dict[str, Any]:
    """
    Task 18: thin wrapper around pipeline.canonical.geography.enrich_location.
    `admin_unit_lookup` defaults to None, which preserves Task 17's
    original, DB-free behavior exactly (admin_unit_id stays None) for
    every existing caller that doesn't pass one.
    """
    return enrich_location(value, candidates, hierarchy_field=hierarchy_field, admin_unit_lookup=admin_unit_lookup)


def _base(domain: str, source: str, record_id: str, document: str | None, ingestion_timestamp: str, dataset: str) -> dict[str, Any]:
    return {"domain": domain, "source": source, "source_record_id": record_id, "ingestion_timestamp": ingestion_timestamp,
            "provenance": {"source_organization": source.upper(), "source_dataset": dataset, "source_document": document,
                           "source_url_or_path": document, "parser_version": PARSER_VERSION, "normalization_version": NORMALIZATION_VERSION}}


def _finish(records: list[dict], quarantine: Callable[..., bool] | None = None) -> list[dict]:
    valid = []
    for record in records:
        errors = validate_record(record)
        if errors:
            sink = quarantine
            if sink is None:
                from pipeline.utils.quarantine import write_quarantine
                sink = write_quarantine
            if sink:
                sink(source=record.get("source", "unknown"), domain=record.get("domain", "canonical"),
                           source_document=record.get("provenance", {}).get("source_document"), reason_code="canonical_invalid",
                           message="; ".join(errors), parser_version=PARSER_VERSION, raw_payload=record)
            continue
        valid.append(record)
    return valid


def adapt_ndma(parsed: dict, *, ingestion_timestamp: str | None = None, quarantine=None,
                admin_unit_lookup: AdminUnitLookup | None = None) -> list[dict]:
    ingested = ingestion_timestamp or normalize_timestamp(parsed.get("parsed_at")) or "unknown"
    doc, report_id, date = parsed.get("filename"), str(parsed.get("report_number") or parsed.get("filename")), normalize_timestamp(parsed.get("report_date"))
    records = []
    for section, fields in (("casualties", ("deaths", "injured")), ("damage", ("houses_damaged", "roads_damaged", "bridges_damaged", "livestock_affected")), ("rescue", ("rescued",))):
        for index, row in enumerate(parsed.get(section, [])):
            record = _base("disaster_event", "ndma", f"{report_id}:{section}:{index}", doc, ingested, "sitrep")
            province = normalize_string(row.get("province")); record.update(_geo(province, PROVINCES, admin_unit_lookup=admin_unit_lookup))
            record.update({"event_type": "disaster_situation_report", "event_name": parsed.get("subject"), "event_date": date,
                           "province": province, "district": normalize_string(row.get("district")), "tehsil": None, "locality": None,
                           "deaths": normalize_number(row.get("deaths")), "injured": normalize_number(row.get("injured")),
                           "houses_damaged": normalize_number(row.get("houses_damaged")), "roads_damaged": normalize_number(row.get("roads_km")),
                           "bridges_damaged": normalize_number(row.get("bridges")), "livestock_affected": normalize_number(row.get("livestock")),
                           "rescued": normalize_number(row.get("persons_rescued") or row.get("rescued")), "affected_population": None, "infrastructure_damage": None,
                           "crops_affected": None, "evacuated": None, "source_document": doc})
            records.append(record)
    return _finish(records, quarantine)


def adapt_pdma_rainfall(parsed: dict, *, ingestion_timestamp: str | None = None, quarantine=None,
                         admin_unit_lookup: AdminUnitLookup | None = None) -> list[dict]:
    ingested = ingestion_timestamp or normalize_timestamp(parsed.get("created_at")) or "unknown"
    return _finish([dict(_base("rainfall_observation", "pdma", f"{parsed.get('source_file')}:{i}", parsed.get("source_file"), ingested, "rainfall_report"),
                         **_geo(row.get("station"), DISTRICTS, hierarchy_field="district", admin_unit_lookup=admin_unit_lookup),
                         observed_at=normalize_timestamp(parsed.get("report_date")), station_name=normalize_string(row.get("station")), station_id=None,
                         rainfall_amount=normalize_number(row.get("rainfall_mm")), rainfall_period="P1D", unit="mm", source_document=parsed.get("source_file"))
                    for i, row in enumerate(parsed.get("stations", []))], quarantine)


def adapt_pdma_gauge(parsed: dict, *, ingestion_timestamp: str | None = None, quarantine=None,
                      admin_unit_lookup: AdminUnitLookup | None = None) -> list[dict]:
    ingested = ingestion_timestamp or normalize_timestamp(parsed.get("created_at")) or "unknown"
    return _finish([dict(_base("gauge_observation", "pdma", f"{parsed.get('source_file')}:{i}", parsed.get("source_file"), ingested, "gauge_report"),
                         **_geo(row.get("station"), DISTRICTS, hierarchy_field="district", admin_unit_lookup=admin_unit_lookup),
                         observed_at=normalize_timestamp(parsed.get("report_datetime")), station_name=normalize_string(row.get("station")), station_id=None,
                         river_name=normalize_string(row.get("river")), water_level=normalize_number(row.get("current_level_ft")), discharge=normalize_number(row.get("discharge_cusecs")),
                         status=normalize_string(row.get("flow_status")), unit="ft", discharge_unit="cusecs", source_document=parsed.get("source_file"))
                    for i, row in enumerate(parsed.get("gauges", []))], quarantine)


def adapt_pmd_daily(records: list[dict], *, ingestion_timestamp: str, quarantine=None,
                     admin_unit_lookup: AdminUnitLookup | None = None) -> list[dict]:
    output = []
    for i, row in enumerate(records):
        city = normalize_string(row.get("city")); record = _base("weather_observation", "pmd", f"daily:{i}:{city}", None, ingestion_timestamp, "daily_forecast")
        record.update(_geo(city, DISTRICTS, hierarchy_field="district", admin_unit_lookup=admin_unit_lookup))
        # Task 20: real scripts/parsing/pmd/daily_parser.py output uses "temperature" (not
        # "max_temperature") and has no "weather"/"day1" field -- verified against real parsed
        # files in data/parsed/pmd/daily_forecast/latest.json. "max_temperature"/"day1" are kept
        # as a fallback only for backward compatibility with any caller still using those keys.
        record.update({"observed_at": normalize_timestamp(row.get("scraped_at")), "location_name": city, "latitude": None, "longitude": None,
            "temperature": normalize_number(row.get("temperature", row.get("max_temperature"))), "humidity": normalize_number(row.get("humidity")), "pressure": None, "wind_speed": None, "wind_direction": None,
            "precipitation": None, "weather_condition": normalize_string(row.get("weather") or row.get("day1") or row.get("forecast_day_1")), "source_document": None}); output.append(record)
    return _finish(output, quarantine)


def adapt_pmd_alerts(record: dict, *, ingestion_timestamp: str, quarantine=None,
                      admin_unit_lookup: AdminUnitLookup | None = None) -> list[dict]:
    regions = record.get("regions") or []
    return _finish([dict(_base("hazard_alert", "pmd", f"alert:{i}:{region}", None, ingestion_timestamp, "weather_alert"),
                         **_geo(region, PROVINCES, admin_unit_lookup=admin_unit_lookup),
                         hazard_type=normalize_string(record.get("alert_type")), issued_at=normalize_timestamp(record.get("scraped_at")), valid_from=None, valid_until=None,
                         severity=normalize_string(record.get("severity")), affected_area=normalize_string(region), province=normalize_string(region), district=None, tehsil=None, locality=None,
                         title=normalize_string(record.get("title")), description=normalize_string(record.get("forecast")), source_document=None)
                    for i, region in enumerate(regions)], quarantine)


def adapt_pmd_weekly(records: list[dict], *, ingestion_timestamp: str, quarantine=None,
                      admin_unit_lookup: AdminUnitLookup | None = None) -> list[dict]:
    """Weekly outlook is an advisory, not a fabricated weather observation."""
    output = []
    for index, row in enumerate(records):
        for region_index, region in enumerate(row.get("regions") or []):
            record = _base("hazard_alert", "pmd", f"weekly:{index}:{region_index}:{region}", None, ingestion_timestamp, "weekly_outlook")
            record.update(_geo(region, PROVINCES, admin_unit_lookup=admin_unit_lookup))
            record.update({"hazard_type": "weather_outlook", "issued_at": normalize_timestamp(row.get("scraped_at")),
                           "valid_from": normalize_timestamp(row.get("date")), "valid_until": None, "severity": None,
                           "affected_area": normalize_string(region), "province": normalize_string(region), "district": None,
                           "tehsil": None, "locality": None, "title": normalize_string(row.get("weekday")),
                           "description": normalize_string(row.get("weather_summary")), "source_document": None})
            output.append(record)
    return _finish(output, quarantine)
