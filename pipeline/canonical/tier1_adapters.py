"""Task 19 -- canonical adapters for the Tier-1 national datasets.

Consumes the source-specific records produced by `scripts/parsing/tier1/*` (never raw files) and
emits canonical records through the existing Task 17/18 machinery: `_base` provenance, shared
normalizers, `enrich_location` geography and `_finish` validation/quarantine. No second
provenance, normalization, geography or DQ framework is introduced.

Geography is only attempted where a source states an administrative location (an EPA district, a
GLOF-alert province). Named facilities (reservoirs) and documents are NOT resolved: e.g. the
reservoir "Mangla" would otherwise fuzzy/exact-match the Task 10 district entry "Mangla" (a known
non-district caveat in scripts/geo/canonical_data.py), which would be a false mapping.
"""

from __future__ import annotations

from typing import Any

from scripts.geo.canonical_data import DISTRICTS, PROVINCES
from scripts.parsing.tier1 import PARSER_VERSION as TIER1_PARSER_VERSION

from .adapters import _base, _finish
from .geography import AdminUnitLookup, enrich_location
from .normalization import normalize_number, normalize_string, normalize_timestamp

NOT_ATTEMPTED = {"location_original": None, "admin_unit_id": None, "admin_unit_key": None,
                 "resolution_status": "not_attempted", "resolution_method": None,
                 "resolution_notes": "source states no administrative location for this record"}


def _tier1_base(domain: str, source: str, dataset: str, parsed: dict[str, Any]) -> dict[str, Any]:
    art = parsed["artifact"]
    record = _base(domain, source, parsed["source_record_id"], art.get("source_file"), art.get("retrieved_at"), dataset)
    record["provenance"].update({"parser_version": TIER1_PARSER_VERSION, "source_url_or_path": art.get("source_url"),
                                 "source_file": art.get("source_file"), "retrieved_at": art.get("retrieved_at"),
                                 "sha256": art.get("sha256")})
    return record


def adapt_suparco_campaigns(parsed: list[dict], *, quarantine=None, admin_unit_lookup: AdminUnitLookup | None = None):
    out = []
    for p in parsed:
        rec = _tier1_base("hazard_alert", "suparco", "disasterwatch_campaigns", p)
        rec.update(enrich_location(None, PROVINCES, admin_unit_lookup=admin_unit_lookup))
        rec.update({"hazard_type": p["hazard_type"], "issued_at": normalize_timestamp(p["last_updated"]),
                    "valid_from": normalize_timestamp(p["starts_at"]), "valid_until": normalize_timestamp(p["ends_at"]),
                    "severity": normalize_string(p["alert_level"]), "affected_area": None, "province": None,
                    "district": None, "tehsil": None, "locality": None, "title": normalize_string(p["name"]),
                    "description": normalize_string(p["description"]), "source_document": p["artifact"].get("source_file"),
                    "glide_number": p["glide_number"], "campaign_scope": p["scope"], "is_live": p["is_live"],
                    "resource_count": p["resource_count"]})
        out.append(rec)
    return _finish(out, quarantine)


def _aqi_common(rec: dict, p: dict, admin_unit_lookup):
    rec.update(enrich_location(p["district"], DISTRICTS, hierarchy_field="district", admin_unit_lookup=admin_unit_lookup))
    rec["city"] = None  # the API is keyed by district only; a city is never inferred


def adapt_epa_stations(parsed: list[dict], *, quarantine=None, admin_unit_lookup: AdminUnitLookup | None = None):
    out = []
    for p in parsed:
        rec = _tier1_base("air_quality_observation", "epa_punjab", "aqi_station_snapshot", p)
        _aqi_common(rec, p, admin_unit_lookup)
        rec.update({"observed_at": normalize_timestamp(p["observed_at"]), "observed_at_basis": p["observed_at_basis"],
                    "station_name": normalize_string(p["station_name"]), "station_id": None,
                    "aqi": normalize_number(p["aqi"]), "category": None,
                    "dominant_pollutant": normalize_string(p["major_pollutant"]), "granularity": "station_snapshot"})
        for pollutant in ("pm25", "pm10", "no2", "so2", "co", "o3"):
            rec[pollutant] = normalize_number(p[pollutant])
        out.append(rec)
    return _finish(out, quarantine)


def adapt_epa_calendar(parsed: list[dict], *, quarantine=None, admin_unit_lookup: AdminUnitLookup | None = None):
    out = []
    for p in parsed:
        rec = _tier1_base("air_quality_observation", "epa_punjab", "aqi_daily_calendar", p)
        _aqi_common(rec, p, admin_unit_lookup)
        rec.update({"observed_at": normalize_timestamp(p["date"]), "observed_at_basis": "calendar_date",
                    "station_name": None, "station_id": None, "aqi": normalize_number(p["aqi"]), "category": None,
                    "station_count": normalize_number(p["station_count"]),
                    "stations_reporting": normalize_string(p["stations_reporting"]), "granularity": "daily_district"})
        for pollutant in ("pm25", "pm10", "no2", "so2", "co", "o3"):
            rec[pollutant] = None  # the calendar endpoint carries no pollutant values
        out.append(rec)
    return _finish(out, quarantine)


def adapt_ffc_reservoir(parsed: list[dict], *, quarantine=None):
    out = []
    for p in parsed:
        rec = _tier1_base("reservoir_observation", "ffc", "reservoir_levels", p)
        rec.update(NOT_ATTEMPTED)
        rec.update({"observed_at": normalize_timestamp(p["observed_at"]), "reservoir_name": p["reservoir_name"],
                    "reservoir_name_original": p["reservoir_name_original"],
                    "water_level": normalize_number(p["water_level"]), "unit": p["water_level_unit"],
                    "live_storage": normalize_number(p["live_storage"]), "storage_unit": p["live_storage_unit"],
                    "combined_live_storage": normalize_number(p["combined_live_storage"]),
                    "source_document": p["artifact"].get("source_file")})
        out.append(rec)
    return _finish(out, quarantine)


def adapt_glof_alerts(parsed: list[dict], *, quarantine=None, admin_unit_lookup: AdminUnitLookup | None = None):
    out = []
    for p in parsed:
        rec = _tier1_base("hazard_alert", "ffc", "glof_alert", p)
        rec.update(enrich_location(p["affected_area"], PROVINCES, hierarchy_field="province", admin_unit_lookup=admin_unit_lookup))
        rec.update({"hazard_type": p["hazard_type"], "issued_at": normalize_timestamp(p["issued_at"]), "valid_from": None,
                    "valid_until": None, "severity": None, "affected_area": normalize_string(p["affected_area"]),
                    "district": None, "tehsil": None, "locality": None, "title": p["title"],
                    "description": p["description"], "source_document": p["artifact"].get("source_file"),
                    "document_id": p["document_id"]})
        out.append(rec)
    return _finish(out, quarantine)


def adapt_documents(parsed: list[dict], *, source: str, dataset: str, quarantine=None):
    """FFC DFSR/GLOF/press-release and NDMC bulletin documents -> the `document` domain (RAG-ready)."""
    out = []
    for p in parsed:
        rec = _tier1_base("document", source, dataset, p)
        rec.update(NOT_ATTEMPTED)
        rec.update({"doc_type": p["doc_type"], "title": p.get("title"), "title_basis": p.get("title_basis"),
                    "issuing_organization": p["issuing_organization"], "hazard_topic": p["hazard_topic"],
                    "publication_date": normalize_timestamp(p.get("publication_date")),
                    "report_date": normalize_timestamp(p.get("report_date")),
                    "issued_at": normalize_timestamp(p.get("issued_at")),
                    "period_start": normalize_timestamp(p.get("period_start")),
                    "period_end": normalize_timestamp(p.get("period_end")),
                    "pdf_creation_date": p.get("pdf_creation_date"), "page_count": p["page_count"],
                    "script": p["script"], "text": p["text"], "text_char_count": p["text_char_count"],
                    "text_quality_note": p.get("text_quality_note"),
                    "source_document": p["artifact"].get("source_file")})
        out.append(rec)
    return _finish(out, quarantine)
