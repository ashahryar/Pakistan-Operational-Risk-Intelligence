"""Task 40 -- read-only gauge-station EVIDENCE view, served from the committed evidence outputs (no database, no write, no network).

Source files (written by scripts/geo/run_gauge_geography.py): gauge_station_inventory.json, gauge_station_mapping.json, gauge_geography_coverage.json.
Only an ELIGIBLE mapping exposes an administrative unit; for every other station the candidate districts are shown as candidates, never as the station's geography.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

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
def gauge_evidence() -> dict:
    inventory = {s["station_key"]: s for s in _load("gauge_station_inventory.json")}
    coverage = _load("gauge_geography_coverage.json")
    stations = []
    for m in sorted(_load("gauge_station_mapping.json"), key=lambda x: x["station_name"].lower()):
        inv = inventory[m["station_key"]]
        state = _STATE.get(m["mapping_status"], "UNRESOLVED")
        claimed = sorted({e["district"] for e in m.get("evidence") or [] if e.get("district")})
        stations.append({
            "station_name": m["station_name"], "river": inv.get("river_name_reported"), "observations": inv["observation_count"],
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
               "note": "Candidate districts are not the station's geography. Only ELIGIBLE rows carry an administrative unit."}
    return {"summary": summary, "stations": stations}
