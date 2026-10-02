"""Small, clearly-synthetic Gold-shaped rows for risk-engine edge-case tests."""

from __future__ import annotations

import datetime as dt


def days(start: str, n: int) -> list[str]:
    s = dt.date.fromisoformat(start)
    return [(s + dt.timedelta(days=i)).isoformat() for i in range(n)]


def _prov(rid):
    return {"sources": [{"source": "x", "source_record_id": rid}]}


def rain(unit, date, value, station=None, status="resolved"):
    station = station or f"S{unit}"
    return {"station_name": station, "date": date, "rainfall_total": value, "admin_unit_id": unit if status == "resolved" else None,
            "resolution_status": status, "location_original": station, "observation_time_basis": "source_observed",
            "provenance": _prov(f"{station}:{date}")}


def gauge(unit, date, value, station="G1", status="resolved"):
    return {"station_name": station, "date": date, "discharge_avg": value, "admin_unit_id": unit if status == "resolved" else None,
            "resolution_status": status, "location_original": station, "observation_time_basis": "source_observed",
            "provenance": _prov(f"{station}:{date}")}


def aqi(unit, date, value, granularity="daily_district"):
    return {"geography_key": f"U{unit}", "date": date, "aqi_avg": value, "granularity": granularity, "admin_unit_id": unit,
            "resolution_status": "resolved", "location_original": "Lahore", "observation_time_basis": "calendar_date",
            "provenance": _prov(f"aqi:{date}")}


def weather(unit, date, temp):
    return {"geography_key": f"U{unit}", "date": date, "temperature_avg": temp, "admin_unit_id": unit, "resolution_status": "resolved",
            "location_original": "L", "observation_time_basis": "source_observed", "provenance": _prov(f"w:{date}")}


def alert(unit, date, alert_id="a1", severity="Very Heavy", status="resolved", valid_until=None):
    return {"alert_id": alert_id, "issued_at": f"{date}T09:00:00", "valid_from": None, "valid_until": valid_until,
            "admin_unit_id": unit if status == "resolved" else None, "resolution_status": status,
            "hazard_type": "Rain", "severity": severity, "source": "pmd", "location_original": "Punjab"}


def event(unit, date, event_id="e1", status="resolved"):
    return {"event_id": event_id, "event_date": date, "admin_unit_id": unit if status == "resolved" else None,
            "resolution_status": status, "location_original": "Sindh", "deaths": 0}


def gold(**domains):
    base = {k: [] for k in ("rainfall", "weather", "gauge", "air_quality", "hazard_alert", "disaster_event", "reservoir")}
    base.update(domains)
    return base
