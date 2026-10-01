"""Task 21 -- Gold/analytics transformations.

Pure Python (no pandas, no pyspark), matching the project's existing local-validation precedent
(databricks/src/common/local_validation.py, scripts/parsing/tier1/run_tier1.py). Each function
is a plain `list[dict] -> list[dict]` transform, directly reusable as the body of a future Spark
UDF/transform once pyspark is available -- nothing here depends on a particular runtime.

Every Silver-level record is first passed through `bronze_dedupe` (the exact Task 18/20 Bronze
identity -- (domain, source, source_record_id), latest ingestion_timestamp wins) before any Gold
aggregation, so Gold never double-counts a record Bronze would have deduplicated.

No function in this module computes a risk score, probability, or composite index.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Callable

from databricks.src.common.local_validation import bronze_dedupe


def _date_part(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    return value[:10] if len(value) >= 10 else None


def _geography_key(record: dict) -> str:
    """Resolved -> the real admin_unit_key (district/province name). Unresolved/ambiguous ->
    a distinct, clearly-labelled key per original source text, so two different unresolved
    stations never collapse into one fake "unknown" bucket (Step 4's explicit requirement)."""
    if record.get("resolution_status") == "resolved" and record.get("admin_unit_key"):
        return record["admin_unit_key"]
    original = record.get("location_original") or record.get("station_name") or "no_location"
    return f"unresolved:{original}"


def _numeric_values(records: list[dict], field: str) -> list[float]:
    return [r[field] for r in records if isinstance(r.get(field), (int, float))]


def _stat(records: list[dict], field: str, fn: Callable[[list[float]], float]) -> float | None:
    values = _numeric_values(records, field)
    return fn(values) if values else None


def _provenance_sources(records: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in records:
        key = (r.get("source"), r.get("source_record_id"))
        if key not in seen:
            seen.add(key)
            out.append({"source": r.get("source"), "source_record_id": r.get("source_record_id")})
    return sorted(out, key=lambda x: (x["source"] or "", x["source_record_id"] or ""))


def _group(records: list[dict], key_fn: Callable[[dict], tuple]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        groups[key_fn(r)].append(r)
    return dict(groups)


# ---------------------------------------------------------------- A. gold_weather_daily
def build_gold_weather_daily(records: list[dict]) -> list[dict]:
    deduped = bronze_dedupe(records)
    groups = _group(deduped, lambda r: (_geography_key(r), _date_part(r.get("observed_at"))))
    out = []
    for (geo_key, date), rows in sorted(groups.items()):
        if date is None:
            continue
        sample = rows[0]
        out.append({
            "dataset": "gold_weather_daily", "geography_key": geo_key, "date": date,
            "admin_unit_id": sample.get("admin_unit_id") if sample.get("resolution_status") == "resolved" else None,
            "district": sample.get("district") if sample.get("resolution_status") == "resolved" else None,
            "location_original": sample.get("location_original"), "resolution_status": sample.get("resolution_status"),
            "temperature_avg": _stat(rows, "temperature", mean), "temperature_min": _stat(rows, "temperature", min),
            "temperature_max": _stat(rows, "temperature", max), "humidity_avg": _stat(rows, "humidity", mean),
            "weather_condition": next((r["weather_condition"] for r in rows if r.get("weather_condition")), None),
            "precipitation_avg": _stat(rows, "precipitation", mean), "wind_speed_avg": _stat(rows, "wind_speed", mean),
            "observation_count": len(rows), "observation_time_basis": "source_observed",
            "provenance": {"sources": _provenance_sources(rows)},
        })
    return out


# ---------------------------------------------------------------- B. gold_rainfall_daily
def build_gold_rainfall_daily(records: list[dict]) -> list[dict]:
    deduped = bronze_dedupe(records)
    groups = _group(deduped, lambda r: (r.get("station_name"), _date_part(r.get("observed_at"))))
    out = []
    for (station, date), rows in sorted(groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        if station is None or date is None:
            continue
        sample = rows[0]
        values = _numeric_values(rows, "rainfall_amount")
        out.append({
            "dataset": "gold_rainfall_daily", "station_name": station, "date": date,
            "admin_unit_id": sample.get("admin_unit_id") if sample.get("resolution_status") == "resolved" else None,
            "district": sample.get("district") if sample.get("resolution_status") == "resolved" else None,
            "location_original": sample.get("location_original"), "resolution_status": sample.get("resolution_status"),
            "rainfall_total": sum(values) if values else None, "rainfall_avg": mean(values) if values else None,
            "unit": sample.get("unit"), "observation_count": len(rows), "observation_time_basis": "source_observed",
            "provenance": {"sources": _provenance_sources(rows)},
        })
    return out


# ---------------------------------------------------------------- C. gold_gauge_daily
def build_gold_gauge_daily(records: list[dict]) -> list[dict]:
    deduped = bronze_dedupe(records)
    groups = _group(deduped, lambda r: (r.get("station_name"), _date_part(r.get("observed_at"))))
    out = []
    for (station, date), rows in sorted(groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        if station is None or date is None:
            continue
        sample = rows[0]
        out.append({
            "dataset": "gold_gauge_daily", "station_name": station, "date": date,
            "river_name": sample.get("river_name"),
            # CRITICAL (Step 4/8): an unresolved gauge station NEVER receives a fabricated admin_unit_id.
            "admin_unit_id": sample.get("admin_unit_id") if sample.get("resolution_status") == "resolved" else None,
            "district": sample.get("district") if sample.get("resolution_status") == "resolved" else None,
            "location_original": sample.get("location_original"), "resolution_status": sample.get("resolution_status"),
            "water_level_min": _stat(rows, "water_level", min), "water_level_max": _stat(rows, "water_level", max),
            "water_level_avg": _stat(rows, "water_level", mean), "discharge_min": _stat(rows, "discharge", min),
            "discharge_max": _stat(rows, "discharge", max), "discharge_avg": _stat(rows, "discharge", mean),
            "observation_count": len(rows), "observation_time_basis": "source_observed",
            "provenance": {"sources": _provenance_sources(rows)},
        })
    return out


# ---------------------------------------------------------------- D. gold_air_quality
def build_gold_air_quality(records: list[dict]) -> list[dict]:
    deduped = bronze_dedupe(records)
    groups = _group(deduped, lambda r: (_geography_key(r), _date_part(r.get("observed_at")), r.get("granularity")))
    out = []
    for (geo_key, date, granularity), rows in sorted(groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "", kv[0][2] or "")):
        if date is None:
            continue
        sample = rows[0]
        out.append({
            "dataset": "gold_air_quality", "geography_key": geo_key, "date": date, "granularity": granularity,
            "admin_unit_id": sample.get("admin_unit_id") if sample.get("resolution_status") == "resolved" else None,
            "district": sample.get("district") if sample.get("resolution_status") == "resolved" else None,
            "location_original": sample.get("location_original"), "resolution_status": sample.get("resolution_status"),
            "station_name": sample.get("station_name"), "aqi_avg": _stat(rows, "aqi", mean),
            "pm25_avg": _stat(rows, "pm25", mean), "pm10_avg": _stat(rows, "pm10", mean),
            "no2_avg": _stat(rows, "no2", mean), "so2_avg": _stat(rows, "so2", mean),
            "co_avg": _stat(rows, "co", mean), "o3_avg": _stat(rows, "o3", mean),
            "observation_count": len(rows), "observation_time_basis": sample.get("observed_at_basis"),
            "provenance": {"sources": _provenance_sources(rows)},
        })
    return out


# ---------------------------------------------------------------- E/F/G. pass-through datasets
def _pass_through(records: list[dict], dataset: str, select: Callable[[dict], dict]) -> list[dict]:
    deduped = bronze_dedupe(records)
    return [select(r) for r in sorted(deduped, key=lambda r: (r.get("source") or "", r.get("source_record_id") or ""))]


def build_gold_disaster_events(records: list[dict]) -> list[dict]:
    def select(r):
        return {"dataset": "gold_disaster_events", "event_id": r.get("source_record_id"), "source": r.get("source"),
                "event_type": r.get("event_type"), "event_name": r.get("event_name"), "event_date": r.get("event_date"),
                "admin_unit_id": r.get("admin_unit_id") if r.get("resolution_status") == "resolved" else None,
                "province": r.get("province"), "district": r.get("district"), "location_original": r.get("location_original"),
                "resolution_status": r.get("resolution_status"), "deaths": r.get("deaths"), "injured": r.get("injured"),
                "affected_population": r.get("affected_population"), "houses_damaged": r.get("houses_damaged"),
                "roads_damaged": r.get("roads_damaged"), "bridges_damaged": r.get("bridges_damaged"),
                "rescued": r.get("rescued"), "evacuated": r.get("evacuated"),
                "observation_time_basis": "source_observed", "provenance": r.get("provenance")}
    return _pass_through(records, "gold_disaster_events", select)


def build_gold_hazard_alerts(records: list[dict]) -> list[dict]:
    def select(r):
        return {"dataset": "gold_hazard_alerts", "alert_id": r.get("source_record_id"), "source": r.get("source"),
                "hazard_type": r.get("hazard_type"), "issued_at": r.get("issued_at"), "valid_from": r.get("valid_from"),
                "valid_until": r.get("valid_until"), "severity": r.get("severity"), "title": r.get("title"),
                "description": r.get("description"),
                "admin_unit_id": r.get("admin_unit_id") if r.get("resolution_status") == "resolved" else None,
                "province": r.get("province"), "district": r.get("district"), "location_original": r.get("location_original"),
                "resolution_status": r.get("resolution_status"), "observation_time_basis": "source_observed",
                "provenance": r.get("provenance")}
    return _pass_through(records, "gold_hazard_alerts", select)


def build_gold_reservoir_status(records: list[dict]) -> list[dict]:
    def select(r):
        return {"dataset": "gold_reservoir_status", "reservoir_name": r.get("reservoir_name"), "source": r.get("source"),
                "observed_at": r.get("observed_at"), "water_level": r.get("water_level"),
                "live_storage": r.get("live_storage"), "combined_live_storage": r.get("combined_live_storage"),
                # Geography intentionally not attempted (Task 19/20: "Mangla" false-matches a district name).
                "admin_unit_id": None, "resolution_status": "not_attempted", "observation_time_basis": "source_observed",
                "provenance": r.get("provenance")}
    return _pass_through(records, "gold_reservoir_status", select)


def build_gold_documents(records: list[dict]) -> list[dict]:
    def select(r):
        effective_date, basis = None, None
        for field, label in (("report_date", "report_date"), ("publication_date", "publication_date"),
                             ("issued_at", "issued_at"), ("period_start", "period_start")):
            if r.get(field):
                effective_date, basis = r[field], label
                break
        return {"dataset": "gold_documents", "document_id": r.get("source_record_id"), "source": r.get("source"),
                "doc_type": r.get("doc_type"), "title": r.get("title"), "effective_date": effective_date,
                "effective_date_basis": basis, "issuing_organization": r.get("issuing_organization"),
                "hazard_topic": r.get("hazard_topic"), "source_file": (r.get("provenance") or {}).get("source_file"),
                "sha256": (r.get("provenance") or {}).get("sha256"),
                "retrieved_at": (r.get("provenance") or {}).get("retrieved_at"), "provenance": r.get("provenance")}
    return _pass_through(records, "gold_documents", select)


# ---------------------------------------------------------------- I. gold_operational_risk_inputs
def build_gold_operational_risk_inputs(
    rainfall: list[dict], gauge: list[dict], aqi: list[dict], weather: list[dict],
    hazard_alerts: list[dict], disaster_events: list[dict],
) -> list[dict]:
    """Aligns RESOLVED-geography signals by (admin_unit_id, date). Unresolved-geography records
    from any source are excluded from alignment entirely (Step 8/4: never forced into a fake
    geography). A (admin_unit_id, date) cell with no contributing signal for a given field stays
    NULL -- this dataset computes NO risk score of any kind."""
    cells: dict[tuple[int, str], dict[str, Any]] = {}

    def cell(admin_unit_id: int, date: str) -> dict:
        key = (admin_unit_id, date)
        if key not in cells:
            cells[key] = {"dataset": "gold_operational_risk_inputs", "admin_unit_id": admin_unit_id, "date": date,
                         "rainfall_total": None, "gauge_discharge_avg": None, "gauge_water_level_avg": None,
                         "aqi_avg": None, "temperature_avg": None, "active_hazard_alert_count": 0,
                         "disaster_event_count": 0, "coverage": {}}
        return cells[key]

    def resolved_date_groups(records: list[dict], date_field: str):
        resolved = [r for r in bronze_dedupe(records) if r.get("resolution_status") == "resolved" and r.get("admin_unit_id")]
        return _group(resolved, lambda r: (r["admin_unit_id"], _date_part(r.get(date_field))))

    for (uid, date), rows in sorted(resolved_date_groups(rainfall, "observed_at").items()):
        if date is None:
            continue
        values = _numeric_values(rows, "rainfall_amount")
        c = cell(uid, date)
        c["rainfall_total"] = sum(values) if values else None
        c["coverage"]["rainfall_observation"] = True

    for (uid, date), rows in sorted(resolved_date_groups(gauge, "observed_at").items()):
        if date is None:
            continue
        c = cell(uid, date)
        c["gauge_discharge_avg"] = _stat(rows, "discharge", mean)
        c["gauge_water_level_avg"] = _stat(rows, "water_level", mean)
        c["coverage"]["gauge_observation"] = True

    for (uid, date), rows in sorted(resolved_date_groups(aqi, "observed_at").items()):
        if date is None:
            continue
        c = cell(uid, date)
        c["aqi_avg"] = _stat(rows, "aqi", mean)
        c["coverage"]["air_quality_observation"] = True

    for (uid, date), rows in sorted(resolved_date_groups(weather, "observed_at").items()):
        if date is None:
            continue
        c = cell(uid, date)
        c["temperature_avg"] = _stat(rows, "temperature", mean)
        c["coverage"]["weather_observation"] = True

    for (uid, date), rows in sorted(resolved_date_groups(hazard_alerts, "issued_at").items()):
        if date is None:
            continue
        c = cell(uid, date)
        c["active_hazard_alert_count"] = len(rows)
        c["coverage"]["hazard_alert"] = True

    for (uid, date), rows in sorted(resolved_date_groups(disaster_events, "event_date").items()):
        if date is None:
            continue
        c = cell(uid, date)
        c["disaster_event_count"] = len(rows)
        c["coverage"]["disaster_event"] = True

    return [cells[k] for k in sorted(cells)]
