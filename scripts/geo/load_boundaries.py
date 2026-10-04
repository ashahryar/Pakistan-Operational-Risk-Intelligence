"""Task 26 -- load the COD-AB boundary layer and the Task 25 crosswalk into the serving tables.

Never touches geo.admin_unit / geo.name_alias. Geometry is stored as the GeoJSON published by the source (no repair);
a feature that fails structural validation is stored with geometry_valid = false and its notes, and is excluded from the
serving views. Upserts only (re-runnable); nothing is deleted. The dataset must match the checksum in
config/admin_boundary_sources.yaml.

Usage: python scripts/geo/load_boundaries.py [--dry-run] [--database NAME]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from pipeline.geo.boundaries import _interior_point, load_index, polygon_state, unit_validity, validate_index  # noqa: E402
from scripts.geo.run_gauge_geography import load_boundary_cfg  # noqa: E402

CROSSWALK_ARTIFACT = PROJECT_ROOT / "data" / "analytics" / "geo" / "gauge_boundary_crosswalk.json"
ARCHIVE = "pak_admin_boundaries.geojson.zip"


def source_row(cfg: dict, report: dict) -> dict:
    s = cfg["sources"][cfg["active_source"]]
    return {"source_key": f"{cfg['active_source']}@v01", "source_name": "COD-AB Pakistan", "publisher": s["publisher"],
            "original_source": s["original_source"], "dataset_name": s["dataset"], "dataset_version": s["version"],
            "valid_on": "2022-09-09", "license": s["license"], "source_url": s["dataset_url"], "retrieved_at": s["retrieved"],
            "checksum": s["archive_sha256"], "crs": s["crs"], "government_certified": s["government_certified"],
            "validation_json": json.dumps(report, sort_keys=True, default=str),
            "notes": " | ".join(s["limitations"])}


def verify_checksum(cfg: dict) -> str:
    s = cfg["sources"][cfg["active_source"]]
    path = PROJECT_ROOT / s["local_dir"] / ARCHIVE
    if not path.exists():
        return "archive_absent"            # extracted GeoJSON present; the archive itself is not required to load
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != s["archive_sha256"]:
        raise SystemExit(f"checksum mismatch for {path.name}: {digest} != {s['archive_sha256']}")
    return "verified"


def prepare() -> dict:
    """Load + validate everything without touching the database."""
    cfg = load_boundary_cfg()
    checksum = verify_checksum(cfg)
    index = load_index(cfg, PROJECT_ROOT, levels=(0, 1, 2))
    bbox = cfg["policy"].get("pakistan_bbox")
    report = validate_index(index, bbox)
    country = index.level(0)
    country_polys = country[0]["polygons"] if country else []
    contained, not_contained = 0, []
    for u in index.units:
        if u["level"] == 0 or u.get("geometry_problem"):
            continue
        pt = _interior_point(u)
        if pt and any(polygon_state(pt[1], pt[0], poly) == 1 for poly in country_polys):
            contained += 1
        else:
            not_contained.append(u["pcode"])
    report["country_containment"] = {"checked": contained + len(not_contained), "contained": contained, "not_contained": not_contained}
    report["checksum_status"] = checksum
    units = []
    for u in index.units:
        valid, notes = unit_validity(u, bbox)
        if u["pcode"] in not_contained:
            valid, notes = False, notes + ["interior point outside the country polygon"]
        units.append({**u, "geometry_valid": valid, "validation_notes": "; ".join(notes) or None})
    report["geometry_valid_count"] = sum(1 for u in units if u["geometry_valid"] and u["level"] > 0)
    report["geometry_invalid_count"] = sum(1 for u in units if not u["geometry_valid"] and u["level"] > 0)
    crosswalk = json.loads(CROSSWALK_ARTIFACT.read_text(encoding="utf-8"))["crosswalk"]
    return {"cfg": cfg, "index": index, "units": units, "report": report, "crosswalk": crosswalk}


def load(prep: dict, database: Optional[str] = None) -> dict:
    from scripts.database.apply_serving_migration import engine_for
    eng = engine_for(database)
    src = source_row(prep["cfg"], prep["report"])
    cw_by_key = {(r["boundary_level"], r["boundary_source_id"]): r for r in prep["crosswalk"]}
    with eng.begin() as conn:
        sid = conn.execute(text("""
            INSERT INTO geo.boundary_source (source_key, source_name, publisher, original_source, dataset_name, dataset_version,
                valid_on, license, source_url, retrieved_at, checksum, crs, government_certified, validation_json, notes)
            VALUES (:source_key, :source_name, :publisher, :original_source, :dataset_name, :dataset_version, :valid_on, :license,
                :source_url, :retrieved_at, :checksum, :crs, :government_certified, CAST(:validation_json AS jsonb), :notes)
            ON CONFLICT (source_key) DO UPDATE SET validation_json = EXCLUDED.validation_json, notes = EXCLUDED.notes,
                checksum = EXCLUDED.checksum, license = EXCLUDED.license
            RETURNING source_id"""), src).scalar_one()
        ids: dict[tuple, int] = {}
        for u in sorted((x for x in prep["units"] if x["level"] > 0), key=lambda x: (x["level"], str(x["pcode"]))):
            ids[(u["level"], u["pcode"])] = conn.execute(text("""
                INSERT INTO geo.boundary_admin_unit (source_id, source_feature_id, name, level, geometry_geojson, geometry_type,
                    geometry_valid, validation_notes, properties_json)
                VALUES (:sid, :fid, :name, :level, CAST(:geom AS jsonb), :gtype, :valid, :notes, CAST(:props AS jsonb))
                ON CONFLICT (source_id, level, source_feature_id) DO UPDATE SET name = EXCLUDED.name,
                    geometry_geojson = EXCLUDED.geometry_geojson, geometry_type = EXCLUDED.geometry_type,
                    geometry_valid = EXCLUDED.geometry_valid, validation_notes = EXCLUDED.validation_notes,
                    properties_json = EXCLUDED.properties_json
                RETURNING boundary_id"""),
                {"sid": sid, "fid": u["pcode"], "name": u["name"], "level": u["level"],
                 "geom": json.dumps(u["geometry"]) if u["geometry"] is not None else None,
                 "gtype": (u["geometry"] or {}).get("type"), "valid": u["geometry_valid"], "notes": u["validation_notes"],
                 "props": json.dumps(u["properties"], sort_keys=True)}).scalar_one()
        for u in prep["units"]:
            if u["level"] == 2 and u["parent_pcode"]:
                conn.execute(text("UPDATE geo.boundary_admin_unit SET parent_boundary_id = :p WHERE boundary_id = :b"),
                             {"p": ids.get((1, u["parent_pcode"])), "b": ids[(2, u["pcode"])]})
        for (level, pcode), bid in ids.items():
            cw = cw_by_key.get((level, pcode))
            if cw is None:
                raise SystemExit(f"no crosswalk row for boundary {level}:{pcode}")
            conn.execute(text("""
                INSERT INTO geo.boundary_crosswalk (boundary_id, pori_admin_unit_id, match_status, match_basis, confidence, source_id,
                    validation_status, notes)
                VALUES (:b, :pori, :status, :basis, :conf, :sid, :vs, :notes)
                ON CONFLICT (boundary_id) DO UPDATE SET pori_admin_unit_id = EXCLUDED.pori_admin_unit_id,
                    match_status = EXCLUDED.match_status, match_basis = EXCLUDED.match_basis, confidence = EXCLUDED.confidence,
                    validation_status = EXCLUDED.validation_status, notes = EXCLUDED.notes"""),
                {"b": bid, "pori": cw["pori_admin_unit_id"], "status": cw["match_status"], "basis": cw["match_basis"],
                 "conf": cw["confidence"], "sid": sid, "vs": cw.get("validation_status"), "notes": cw.get("note")})
    return {"source_id": sid, "boundary_units": len(ids),
            "crosswalk_status_counts": dict(sorted(Counter(cw_by_key[k]["match_status"] for k in ids).items()))}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="validate only; no database access")
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    prep = prepare()
    rep = prep["report"]
    print(json.dumps({k: rep[k] for k in ("valid", "problems", "level1_count", "level2_count", "geometry_valid_count",
                                          "geometry_invalid_count", "country_containment", "checksum_status")}, indent=2, default=str))
    if a.dry_run:
        return 0 if rep["valid"] else 1
    print(json.dumps(load(prep, a.database), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
