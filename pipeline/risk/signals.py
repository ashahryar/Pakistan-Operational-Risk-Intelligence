"""Raw signal extraction from Gold datasets. Only RESOLVED geography becomes a signal; unresolved
rows are returned separately and never mapped. Duplicate source records are collapsed by their
natural key so a duplicated Gold row cannot multiply a signal.
"""

from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from statistics import mean
from typing import Any

from pipeline.risk.contracts import DOMAINS


def _resolved(row: dict) -> bool:
    return row.get("resolution_status") == "resolved" and bool(row.get("admin_unit_id"))


def _dedupe(rows: list[dict], key_fn) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = key_fn(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _prov_ids(row: dict) -> list[str]:
    return [s.get("source_record_id") for s in (row.get("provenance") or {}).get("sources", []) if s.get("source_record_id")]


def _numeric_obs(rows, domain, value_field, signal_name, key_fn, source):
    """-> ({(unit, date): obs}, unresolved). The value is the mean of non-null values from distinct source rows."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    unresolved = []
    for r in _dedupe(rows, key_fn):
        if r.get(value_field) is None:
            continue                                   # missing != 0: no observation is created
        if not _resolved(r):
            unresolved.append({"domain": domain, "date": r.get("date"), "raw_value": r[value_field],
                               "location_original": r.get("location_original"), "station_name": r.get("station_name"),
                               "resolution_status": r.get("resolution_status")})
            continue
        groups[(r["admin_unit_id"], r["date"])].append(r)
    obs = {}
    for (unit, date), rs in groups.items():
        obs[(unit, date)] = {"domain": domain, "unit": unit, "date": date, "signal_name": signal_name,
                             "raw_value": mean(x[value_field] for x in rs), "source": source,
                             "source_record_ids": sorted({i for x in rs for i in (_prov_ids(x) or [str(key_fn(x)[0])])}),
                             "basis": rs[0].get("observation_time_basis", "source_observed")}
    return obs, unresolved


def extract_signals(gold: dict[str, list[dict]], cfg: dict[str, Any]) -> dict[str, Any]:
    on = cfg["enabled_domains"]
    numeric: dict[str, dict] = {}
    unresolved: list[dict] = []
    specs = {
        "rainfall": ("rainfall_total", "daily_rainfall_total_mm_unit_mean", lambda r: (str(r.get("station_name")), r.get("date")), "pdma"),
        "weather": ("temperature_avg", "temperature_avg", lambda r: (str(r.get("geography_key")), r.get("date")), "pmd"),
        "gauge": ("discharge_avg", "discharge_avg_cusecs_unit_mean", lambda r: (str(r.get("station_name")), r.get("date")), "pdma"),
    }
    for domain, (field, name, key_fn, source) in specs.items():
        if on.get(domain):
            numeric[domain], unr = _numeric_obs(gold.get(domain, []), domain, field, name, key_fn, source)
            unresolved += unr
    if on.get("air_quality"):
        daily = [r for r in gold.get("air_quality", []) if r.get("granularity") == "daily_district"]
        numeric["air_quality"], unr = _numeric_obs(daily, "air_quality", "aqi_avg", "aqi_avg_daily_district",
                                                   lambda r: (str(r.get("geography_key")), r.get("date")), "epa_punjab")
        unresolved += unr

    alerts = []
    if on.get("hazard_alert"):
        extra = int(cfg.get("alert_default_extra_active_days", 0))
        for r in _dedupe(gold.get("hazard_alert", []), lambda r: (r.get("alert_id"),)):
            if not r.get("issued_at"):
                continue
            if not _resolved(r):
                unresolved.append({"domain": "hazard_alert", "date": str(r["issued_at"])[:10], "alert_id": r.get("alert_id"),
                                   "location_original": r.get("location_original"), "resolution_status": r.get("resolution_status")})
                continue
            start = _dt.date.fromisoformat((r.get("valid_from") or r["issued_at"])[:10])
            end = _dt.date.fromisoformat(r["valid_until"][:10]) if r.get("valid_until") else start + _dt.timedelta(days=extra)
            alerts.append({"unit": r["admin_unit_id"], "start": start.isoformat(), "end": end.isoformat(),
                           "alert_id": r["alert_id"], "source": r.get("source"),
                           "hazard_type": r.get("hazard_type"), "severity": r.get("severity")})

    events: dict[int, list[str]] = defaultdict(list)
    event_ids: dict[int, list[str]] = defaultdict(list)
    if on.get("disaster_event"):
        for r in _dedupe(gold.get("disaster_event", []), lambda r: (r.get("event_id"),)):
            if not r.get("event_date"):
                continue
            if not _resolved(r):
                unresolved.append({"domain": "disaster_event", "date": str(r["event_date"])[:10], "event_id": r.get("event_id"),
                                   "location_original": r.get("location_original"), "resolution_status": r.get("resolution_status")})
                continue
            events[r["admin_unit_id"]].append(str(r["event_date"])[:10])
            event_ids[r["admin_unit_id"]].append(r["event_id"])
    unresolved.sort(key=lambda u: (u["domain"], u.get("date") or "", str(u.get("station_name") or u.get("alert_id") or u.get("event_id") or "")))
    assert set(numeric) <= set(DOMAINS)
    return {"numeric": numeric, "alerts": alerts, "events": dict(events), "event_ids": dict(event_ids), "unresolved": unresolved}
