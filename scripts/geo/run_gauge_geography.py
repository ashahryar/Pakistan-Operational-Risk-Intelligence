"""Task 24 -- gauge station inventory, geography mapping and before/after coverage on the REAL Gold data.

Reads data/analytics/gold/datasets/gold_gauge_daily.jsonl + config/gauge_station_evidence.yaml and one
READ-ONLY geo.admin_unit lookup. Writes only data/analytics/geo/gauge_*.json. No PostgreSQL writes.

Usage: python scripts/geo/run_gauge_geography.py   (exit code 1 if validation fails)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.geo.gauge_mapping import (  # noqa: E402
    ELIGIBLE_STATUSES,
    STATUSES,
    apply_to_gauge_rows,
    before_after,
    build_mapping,
    top_unresolved,
)
from pipeline.geo.gauge_station import build_inventory  # noqa: E402

GOLD_GAUGE = PROJECT_ROOT / "data" / "analytics" / "gold" / "datasets" / "gold_gauge_daily.jsonl"
EVIDENCE = PROJECT_ROOT / "config" / "gauge_station_evidence.yaml"
OUT = PROJECT_ROOT / "data" / "analytics" / "geo"


def load_gauge_rows(path: Path = GOLD_GAUGE) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def load_evidence(path: Path = EVIDENCE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def units_by_name() -> tuple[dict, set, set]:
    from scripts.risk.run_risk_engine import _caveated, _unit_info
    info = _unit_info()
    cav_ids = _caveated(info) if info else set()
    caveated = {info[u]["name"] for u in cav_ids}
    by_name = {}
    for uid, i in sorted(info.items()):
        by_name.setdefault(i["name"], {"id": uid, "level": i["level"], "province": i["province"]})
    return by_name, caveated, cav_ids


def validate(inventory: list[dict], mapping: list[dict]) -> list[str]:
    errs = []
    keys = [s["station_key"] for s in inventory]
    if len(keys) != len(set(keys)):
        errs.append("duplicate station_key in inventory")
    if {m["station_key"] for m in mapping} != set(keys):
        errs.append("mapping and inventory station sets differ")
    for s in inventory:
        if s["latitude"] is not None or s["longitude"] is not None:
            errs.append(f"{s['station_key']}: coordinates present without a sourced coordinate field")
        if s["basin_name"] or s["catchment_name"]:
            errs.append(f"{s['station_key']}: basin/catchment present but the source publishes none")
    for m in mapping:
        k = m["station_key"]
        if m["mapping_status"] not in STATUSES:
            errs.append(f"{k}: unknown status {m['mapping_status']}")
        if m["eligible_for_admin_risk"]:
            if m["mapping_status"] not in ELIGIBLE_STATUSES or not m["admin_unit_id"] or m["caveat"]:
                errs.append(f"{k}: eligible without sufficient evidence")
        elif not m["ineligibility_reason"]:
            errs.append(f"{k}: ineligible without a reason")
        if m["mapping_status"] in {"resolved_authoritative", "resolved_coordinate", "resolved_source_reported", "resolved_inferred"} \
                and not (m["mapping_source"] and m["mapping_source_record"]):
            errs.append(f"{k}: resolved without provenance")
        if not m["mapping_version"]:
            errs.append(f"{k}: missing mapping_version")
    return errs


def main() -> dict:
    gauge = load_gauge_rows()
    cfg = load_evidence()
    by_name, caveated, cav_ids = units_by_name()
    inventory = build_inventory(gauge)
    mapping = build_mapping(inventory, cfg, by_name, caveated)
    mapped_rows = apply_to_gauge_rows(gauge, mapping, inventory)
    errors = validate(inventory, mapping)
    ba = before_after(gauge, mapped_rows, inventory, mapping, cav_ids)
    coverage = {
        "mapping_version": cfg["mapping_version"], "mapping_date": cfg["mapping_date"],
        "validation_status": cfg["validation_status"], "admin_unit_labels_from_db": bool(by_name),
        "distinct_stations": len(inventory),
        "mapping_status_counts": dict(sorted(Counter(m["mapping_status"] for m in mapping).items())),
        "river_context_status_counts": dict(sorted(Counter(s["river_context_status"] for s in inventory).items())),
        "basin_context_status_counts": dict(sorted(Counter(s["basin_context_status"] for s in inventory).items())),
        "coordinate_based_mappings": 0,
        "coordinate_note": "no authoritative station coordinates or boundary polygons exist in the project; no point-in-polygon mapping possible",
        "before_after": ba, "top_unresolved_by_observations": top_unresolved(mapping, inventory),
        "validation_errors": errors,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, obj in (("gauge_station_inventory.json", inventory), ("gauge_station_mapping.json", mapping),
                      ("gauge_geography_coverage.json", coverage)):
        (OUT / name).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return coverage


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    sys.exit(1 if result["validation_errors"] else 0)
