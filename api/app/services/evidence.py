"""Task 40 -- read-only gauge-station EVIDENCE view, served from the committed evidence outputs (no database, no write, no network).

Source files (written by scripts/geo/run_gauge_geography.py): gauge_station_inventory.json, gauge_station_mapping.json, gauge_geography_coverage.json.
Only an ELIGIBLE mapping exposes an administrative unit; for every other station the candidate districts are shown as candidates, never as the station's geography.
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

from api.app.db import fetch_all

GEO_DIR = Path(__file__).resolve().parents[3] / "data" / "analytics" / "geo"

_STATE = {"resolved_authoritative": "ELIGIBLE", "resolved_coordinate": "ELIGIBLE", "resolved_source_reported": "ELIGIBLE",
          "ambiguous": "CONFLICTING_GEOGRAPHY", "resolved_inferred": "SECONDARY_ONLY", "caveated": "CAVEATED", "unresolved": "UNRESOLVED"}
_STATE_TEXT = {"ELIGIBLE": "authoritative evidence supports this administrative unit",
               "CONFLICTING_GEOGRAPHY": "sources disagree; no district is selected",
               "SECONDARY_ONLY": "only non-official references exist; not used for risk",
               "CAVEATED": "the only candidate unit is not a real district; not used for risk",
               "UNRESOLVED": "no usable evidence; the station is not attributed to any district"}


def _load(name: str):
    return json.loads((GEO_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _static_evidence() -> dict:
    inventory = {s["station_key"]: s for s in _load("gauge_station_inventory.json")}
    coverage = _load("gauge_geography_coverage.json")
    stations = []
    for m in sorted(_load("gauge_station_mapping.json"), key=lambda x: x["station_name"].lower()):
        inv = inventory[m["station_key"]]
        state = _STATE.get(m["mapping_status"], "UNRESOLVED")
        claimed = sorted({e["district"] for e in m.get("evidence") or [] if e.get("district")})
        stations.append({
            "match_key": _key(inv.get("match_key") or m["station_name"]), "station_name": m["station_name"], "river": inv.get("river_name_reported"), "observations": inv["observation_count"],
            "date_min": inv.get("date_min"), "date_max": inv.get("date_max"), "evidence_state": state, "evidence_state_meaning": _STATE_TEXT[state],
            "mapping_status": m["mapping_status"], "eligible_for_admin_risk": bool(m["eligible_for_admin_risk"]),
            "admin_unit_id": m["admin_unit_id"] if state == "ELIGIBLE" else None,
            "admin_unit_name": m["admin_unit_name"] if state == "ELIGIBLE" else None,
            "geography_derivation": m["geography_derivation"] if state == "ELIGIBLE" else None,
            "candidate_districts": [] if state == "ELIGIBLE" else claimed, "evidence_records": len(m.get("evidence") or []),
            "ineligibility_reason": m.get("ineligibility_reason")})
    counts: dict[str, int] = {}
    for s in stations:
        counts[s["evidence_state"]] = counts.get(s["evidence_state"], 0) + 1
    summary = {"stations": len(stations), "observations": sum(s["observations"] for s in stations), "state_counts": dict(sorted(counts.items())),
               "observations_with_eligible_mapping": coverage["observations_eligible_for_risk"], "mapping_version": coverage["mapping_version"],
               "observations_source": "evidence_snapshot", "latest_observation": max((s["date_max"] for s in stations if s["date_max"]), default=None),
               "note": "Candidate districts are not the station's geography. Only ELIGIBLE rows carry an administrative unit."}
    return {"summary": summary, "stations": stations}


def _key(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _live_observations() -> dict[str, dict]:
    """Per-station observation days and dates straight from the database (the evidence files are a frozen snapshot of the geography work).
    One observation = one report date, as in the inventory. Keyed by the compact station name, so spelling variants of one gauge merge."""
    rows = fetch_all("SELECT station, count(DISTINCT report_datetime::date) AS days, min(report_datetime::date) AS dmin, max(report_datetime::date) AS dmax "
                     "FROM pdma_gauge_readings WHERE report_datetime IS NOT NULL AND station IS NOT NULL GROUP BY station")
    live: dict[str, dict] = {}
    for r in rows:
        cur = live.setdefault(_key(r["station"]), {"days": 0, "dmin": r["dmin"], "dmax": r["dmax"]})
        cur["dmin"], cur["dmax"] = min(cur["dmin"], r["dmin"]), max(cur["dmax"], r["dmax"])
        cur["days"] = max(cur["days"], int(r["days"]))        # variants of one gauge report on the same dates: do not double-count a date
    return live


def gauge_evidence() -> dict:
    """The evidence view with LIVE observation counts and dates. If the database is unreadable, the frozen snapshot values are served and
    summary.observations_source says so (never silently)."""
    data = copy.deepcopy(_static_evidence())
    try:
        live = _live_observations()
    except Exception:
        return data
    for s in data["stations"]:
        v = live.get(s["match_key"])
        if v:
            s["observations"], s["date_min"], s["date_max"] = v["days"], v["dmin"].isoformat(), v["dmax"].isoformat()
    summ = data["summary"]
    summ["observations"] = sum(s["observations"] for s in data["stations"])
    summ["observations_with_eligible_mapping"] = sum(s["observations"] for s in data["stations"] if s["evidence_state"] == "ELIGIBLE")
    summ["latest_observation"] = max((s["date_max"] for s in data["stations"] if s["date_max"]), default=None)
    summ["observations_source"] = "database"
    return data
