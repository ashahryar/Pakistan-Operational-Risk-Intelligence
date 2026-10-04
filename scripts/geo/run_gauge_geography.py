"""Task 24/25 -- gauge station inventory, evidence registry, boundary crosswalk, geography mapping and coverage
on the REAL Gold data.

Reads data/analytics/gold/datasets/gold_gauge_daily.jsonl, config/gauge_station_evidence.yaml,
config/admin_boundary_sources.yaml, the (gitignored, re-downloadable) boundary GeoJSON under data/raw/boundaries/,
and one READ-ONLY geo.admin_unit lookup. Writes only data/analytics/geo/gauge_*.json. No PostgreSQL writes.
If the boundary files are absent the run still completes: coordinate mapping is simply unavailable.

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

from pipeline.geo.boundaries import (  # noqa: E402
    MATCHED,
    build_crosswalk,
    crosswalk_lookup,
    find_duplicate_coordinates,
    load_index,
    validate_index,
)
from pipeline.geo.gauge_mapping import (  # noqa: E402
    ELIGIBLE_STATUSES,
    EVIDENCE_STATUSES,
    STATUSES,
    apply_to_gauge_rows,
    before_after,
    build_mapping,
    top_unresolved,
)
from pipeline.geo.gauge_station import build_inventory  # noqa: E402

GOLD_GAUGE = PROJECT_ROOT / "data" / "analytics" / "gold" / "datasets" / "gold_gauge_daily.jsonl"
EVIDENCE = PROJECT_ROOT / "config" / "gauge_station_evidence.yaml"
BOUNDARY_CFG = PROJECT_ROOT / "config" / "admin_boundary_sources.yaml"
OUT = PROJECT_ROOT / "data" / "analytics" / "geo"

# Task 24 committed result (b43c1a2), kept as a fixed historical reference for the comparison.
TASK24 = {"mapping_status_counts": {"ambiguous": 1, "caveated": 1, "resolved_inferred": 4, "unresolved": 35},
          "eligible_stations": 0, "observations_eligible_for_risk": 0, "observations_unresolved": 3686}


def load_gauge_rows(path: Path = GOLD_GAUGE) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def load_evidence(path: Path = EVIDENCE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_boundary_cfg(path: Path = BOUNDARY_CFG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def units_by_name() -> tuple[dict, set, set, list]:
    from scripts.geo.canonical_data import DISTRICTS, PROVINCES
    from scripts.risk.run_risk_engine import _caveated, _unit_info
    info = _unit_info()
    cav_ids = _caveated(info) if info else set()
    caveated = {info[u]["name"] for u in cav_ids}
    by_name = {}
    for uid, i in sorted(info.items()):
        by_name.setdefault(i["name"], {"id": uid, "level": i["level"], "province": i["province"]})
    aliases = {(1, p["name"]): p.get("aliases", []) for p in PROVINCES}
    aliases.update({(2, d["name"]): d.get("aliases", []) for d in DISTRICTS})
    canonical = [{"id": uid, "name": i["name"], "level": i["level"], "province": i["province"],
                  "aliases": aliases.get((i["level"], i["name"]), [])} for uid, i in sorted(info.items()) if i["level"] in (1, 2)]
    return by_name, caveated, cav_ids, canonical


def boundary_foundation(canonical: list[dict], cfg: dict):
    """-> (index | None, crosswalk rows, validation report). Absent boundary files degrade gracefully."""
    src = cfg["sources"][cfg["active_source"]]
    if not all((PROJECT_ROOT / src["local_dir"] / f).exists() for f in src["files"].values()):
        return None, [], {"available": False, "reason": f"boundary files not found under {src['local_dir']} (re-download via resource_url)"}
    index = load_index(cfg, PROJECT_ROOT)
    report = validate_index(index, cfg["policy"].get("pakistan_bbox"))
    rows = build_crosswalk(index, canonical, cfg.get("crosswalk_aliases") or {}) if canonical else []
    report["available"] = True
    return index, rows, report


def validate(inventory: list[dict], mapping: list[dict], policy: dict | None = None) -> list[str]:
    errs = []
    keys = [s["station_key"] for s in inventory]
    if len(keys) != len(set(keys)):
        errs.append("duplicate station_key in inventory")
    if {m["station_key"] for m in mapping} != set(keys):
        errs.append("mapping and inventory station sets differ")
    for s in inventory:
        if s["latitude"] is not None or s["longitude"] is not None:
            errs.append(f"{s['station_key']}: coordinates present in the inventory without a sourced coordinate field")
        if s["basin_name"] or s["catchment_name"]:
            errs.append(f"{s['station_key']}: basin/catchment present but the source publishes none")
    for m in mapping:
        k = m["station_key"]
        if m["mapping_status"] not in STATUSES:
            errs.append(f"{k}: unknown status {m['mapping_status']}")
        if m["eligible_for_admin_risk"]:
            if m["mapping_status"] not in ELIGIBLE_STATUSES or not m["admin_unit_id"] or m["ineligibility_reason"]:
                errs.append(f"{k}: eligible without sufficient evidence")
            if not any(e["evidence_status"] == "authoritative" for e in m["evidence"]):
                errs.append(f"{k}: eligible without authoritative evidence")
            if m["geography_derivation"] == "authoritative_source_reported":
                errs.append(f"{k}: coordinate-derived geography mislabelled")
        elif not m["ineligibility_reason"]:
            errs.append(f"{k}: ineligible without a reason")
        if m["mapping_status"] in {"resolved_authoritative", "resolved_coordinate", "resolved_source_reported", "resolved_inferred"} \
                and not (m["mapping_source"] and m["mapping_source_record"]):
            errs.append(f"{k}: resolved without provenance")
        if m["mapping_status"] == "resolved_coordinate" and m["geography_derivation"] != "coordinate_based":
            errs.append(f"{k}: resolved_coordinate must be coordinate_based")
        if not m["mapping_version"]:
            errs.append(f"{k}: missing mapping_version")
        for e in m["evidence"]:
            if e["evidence_status"] not in EVIDENCE_STATUSES:
                errs.append(f"{k}: unknown evidence_status {e['evidence_status']}")
    return errs


def compute_mapping(gauge: list[dict]) -> dict:
    """Everything the mapping needs, computed once (shared with the risk runner)."""
    cfg = load_evidence()
    bcfg = load_boundary_cfg()
    by_name, caveated, cav_ids, canonical = units_by_name()
    index, crosswalk_rows, boundary_report = boundary_foundation(canonical, bcfg)
    inventory = build_inventory(gauge)
    mapping = build_mapping(inventory, cfg, by_name, caveated, index, crosswalk_lookup(crosswalk_rows), bcfg["policy"],
                            bcfg["policy"].get("pakistan_bbox"))
    return {"cfg": cfg, "bcfg": bcfg, "by_name": by_name, "cav_ids": cav_ids, "canonical": canonical, "index": index,
            "crosswalk_rows": crosswalk_rows, "boundary_report": boundary_report, "inventory": inventory, "mapping": mapping}


def main() -> dict:
    gauge = load_gauge_rows()
    c = compute_mapping(gauge)
    cfg, bcfg, by_name, cav_ids, canonical = c["cfg"], c["bcfg"], c["by_name"], c["cav_ids"], c["canonical"]
    index, crosswalk_rows, boundary_report = c["index"], c["crosswalk_rows"], c["boundary_report"]
    inventory, mapping = c["inventory"], c["mapping"]
    mapped_rows = apply_to_gauge_rows(gauge, mapping, inventory)
    errors = validate(inventory, mapping, bcfg["policy"])
    if boundary_report.get("available") and not boundary_report["valid"]:
        errors.append("boundary dataset failed structural validation")
    dup = find_duplicate_coordinates([{"station_key": s["station_key"], **e} for s, m in zip(inventory, mapping) for e in m["evidence"]
                                      if e.get("latitude") is not None])
    if dup:
        errors.append(f"duplicate coordinates across stations: {dup}")
    ba = before_after(gauge, mapped_rows, inventory, mapping, cav_ids)
    eligible_obs = sum(1 for r in mapped_rows if r.get("resolution_status") == "resolved" and r.get("admin_unit_id"))
    cw_status = dict(sorted(Counter((r["boundary_level"], r["match_status"]) for r in crosswalk_rows).items()))
    coverage = {
        "mapping_version": cfg["mapping_version"], "mapping_date": cfg["mapping_date"], "validation_status": cfg["validation_status"],
        "admin_unit_labels_from_db": bool(by_name), "distinct_stations": len(inventory),
        "mapping_status_counts": dict(sorted(Counter(m["mapping_status"] for m in mapping).items())),
        "geography_derivation_counts": dict(sorted(Counter(m["geography_derivation"] for m in mapping).items())),
        "river_context_status_counts": dict(sorted(Counter(s["river_context_status"] for s in inventory).items())),
        "basin_context_status_counts": dict(sorted(Counter(s["basin_context_status"] for s in inventory).items())),
        "authoritative_station_mappings": sum(1 for m in mapping if m["mapping_status"] == "resolved_authoritative"),
        "coordinate_derived_mappings": sum(1 for m in mapping if m["mapping_status"] == "resolved_coordinate"),
        "stations_with_authoritative_coordinates": sum(1 for m in mapping for e in m["evidence"]
                                                       if e.get("latitude") is not None and e["evidence_status"] == "authoritative"),
        "eligible_stations": sum(1 for m in mapping if m["eligible_for_admin_risk"]),
        "observations_eligible_for_risk": eligible_obs, "observations_unresolved": len(gauge) - eligible_obs,
        "boundary_available": bool(index),
        "boundary_crosswalk_status_by_level": {f"level{k[0]}:{k[1]}": v for k, v in cw_status.items()},
        "task24_reference": TASK24, "before_after": ba,
        "top_unresolved_by_observations": top_unresolved(mapping, inventory),
        "validation_errors": errors,
    }
    evidence_out = {"mapping_version": cfg["mapping_version"], "mapping_date": cfg["mapping_date"],
                    "policy": bcfg["policy"], "investigation_log": cfg.get("investigation_log", []),
                    "evidence_status_counts": dict(sorted(Counter(e["evidence_status"] for m in mapping for e in m["evidence"]).items())),
                    "authoritative_evidence_records": sum(1 for m in mapping for e in m["evidence"] if e["evidence_status"] == "authoritative"),
                    "stations": [{"station_key": m["station_key"], "mapping_status": m["mapping_status"],
                                  "eligible_for_admin_risk": m["eligible_for_admin_risk"], "evidence": m["evidence"]}
                                 for m in mapping if m["evidence"]]}
    src = bcfg["sources"][bcfg["active_source"]]
    crosswalk_out = {"boundary_source": {k: src[k] for k in ("publisher", "original_source", "dataset", "dataset_url", "version", "license",
                                                              "retrieved", "archive_sha256", "crs", "levels", "government_certified",
                                                              "accepted_for_coordinate_mapping", "limitations")},
                     "validation": boundary_report, "match_status_counts": coverage["boundary_crosswalk_status_by_level"],
                     "pori_units_without_boundary": sorted(c["name"] for c in canonical if c["level"] == 2 and c["id"] not in
                                                           {r["pori_admin_unit_id"] for r in crosswalk_rows if r["pori_admin_unit_id"]})
                     if crosswalk_rows else [],
                     "crosswalk": crosswalk_rows}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, obj in (("gauge_station_inventory.json", inventory), ("gauge_station_mapping.json", mapping),
                      ("gauge_station_evidence.json", evidence_out), ("gauge_boundary_crosswalk.json", crosswalk_out),
                      ("gauge_geography_coverage.json", coverage)):
        (OUT / name).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return coverage


_ = MATCHED

if __name__ == "__main__":
    result = main()
    print(json.dumps({k: v for k, v in result.items() if k not in ("before_after", "top_unresolved_by_observations")},
                     indent=2, sort_keys=True, ensure_ascii=False))
    sys.exit(1 if result["validation_errors"] else 0)
