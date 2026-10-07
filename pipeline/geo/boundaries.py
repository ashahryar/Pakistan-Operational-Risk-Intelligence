"""Administrative boundary foundation: GeoJSON loading, structural validation, point-in-polygon and a
deterministic boundary -> canonical (geo.admin_unit) crosswalk. Pure Python (no geometry dependency).

Coordinates follow GeoJSON order (lon, lat). Only WGS84-equivalent CRS (CRS84 / EPSG:4326) is accepted;
anything else raises, because no reprojection library is available and silently using projected
coordinates would mis-locate stations.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Optional

from pipeline.geo.gauge_station import match_key

ACCEPTED_CRS = {"urn:ogc:def:crs:ogc:1.3:crs84", "urn:ogc:def:crs:epsg::4326", "epsg:4326", "crs84"}
DEFAULT_BBOX = {"lat_min": 23.5, "lat_max": 37.2, "lon_min": 60.8, "lon_max": 77.9}
_EPS = 1e-12


# ---------------------------------------------------------------- coordinates
def validate_coordinate(lat: Any, lon: Any, bbox: Optional[dict] = None, min_decimals: int = 3) -> dict:
    """-> {"valid": bool, "flags": [...]}. Never repairs a coordinate; a reversed pair is reported, not swapped."""
    bbox = bbox or DEFAULT_BBOX
    flags: list[str] = []
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return {"valid": False, "flags": ["not_numeric"]}
    if not (math.isfinite(la) and math.isfinite(lo)):
        return {"valid": False, "flags": ["not_finite"]}
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        flags.append("out_of_range")
        if -90 <= lo <= 90 and -180 <= la <= 180:
            flags.append("likely_reversed")
        return {"valid": False, "flags": flags}

    def inside(a: float, o: float) -> bool:
        return bbox["lat_min"] <= a <= bbox["lat_max"] and bbox["lon_min"] <= o <= bbox["lon_max"]

    if not inside(la, lo):
        flags.append("outside_pakistan_plausible_extent")
        if inside(lo, la):
            flags.append("likely_reversed")
        return {"valid": False, "flags": flags}
    for v in (lat, lon):
        s = repr(float(v))
        if "." in s and len(s.split(".")[1].rstrip("0")) < min_decimals:
            flags.append("low_precision")
            break
    return {"valid": True, "flags": flags}


def find_duplicate_coordinates(records: Iterable[dict]) -> dict[tuple, list[str]]:
    """records: {station_key, latitude, longitude}. -> {(lat, lon): [station_key, ...]} for >1 distinct stations."""
    seen: dict[tuple, set[str]] = {}
    for r in records:
        if r.get("latitude") is None or r.get("longitude") is None:
            continue
        seen.setdefault((round(float(r["latitude"]), 6), round(float(r["longitude"]), 6)), set()).add(r["station_key"])
    return {k: sorted(v) for k, v in sorted(seen.items()) if len(v) > 1}


# ---------------------------------------------------------------- geometry
def _ring_state(x: float, y: float, ring: list) -> int:
    """1 inside, 0 outside, -1 on the ring boundary (ray casting + on-segment test)."""
    inside = False
    n = len(ring)
    for i in range(n - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) <= _EPS and min(x1, x2) - _EPS <= x <= max(x1, x2) + _EPS and min(y1, y2) - _EPS <= y <= max(y1, y2) + _EPS:
            return -1
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return 1 if inside else 0


def polygon_state(x: float, y: float, polygon: list) -> int:
    outer = _ring_state(x, y, polygon[0])
    if outer != 1:
        return outer
    for hole in polygon[1:]:
        h = _ring_state(x, y, hole)
        if h == -1:
            return -1
        if h == 1:
            return 0
    return 1


def _polygons(geometry: dict) -> list:
    t = geometry["type"]
    if t == "Polygon":
        return [geometry["coordinates"]]
    if t == "MultiPolygon":
        return list(geometry["coordinates"])
    raise ValueError(f"unsupported geometry type {t}")


def _bbox(polys: list) -> tuple[float, float, float, float]:
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    return min(xs), min(ys), max(xs), max(ys)


def _ring_area(ring: list) -> float:
    return abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))) / 2


class BoundaryIndex:
    """Units of one or more levels with bbox pre-filtering."""

    def __init__(self, units: list[dict], source: dict, crs: str):
        self.units, self.source, self.crs = units, source, crs

    def level(self, level: int) -> list[dict]:
        return [u for u in self.units if u["level"] == level]

    def locate(self, lat: float, lon: float, level: int = 2) -> dict:
        """-> {"status": inside|outside|on_boundary|multiple, "matches": [unit ...]}. Never guesses on a boundary."""
        inside, edge = [], []
        for u in self.level(level):
            x0, y0, x1, y1 = u["bbox"]
            if not (x0 - _EPS <= lon <= x1 + _EPS and y0 - _EPS <= lat <= y1 + _EPS):
                continue
            states = [polygon_state(lon, lat, poly) for poly in u["polygons"]]
            if 1 in states:
                inside.append(u)
            elif -1 in states:
                edge.append(u)
        pub = lambda us: [{k: u[k] for k in ("level", "pcode", "name", "parent_pcode")} for u in us]  # noqa: E731
        if len(inside) == 1 and not edge:
            return {"status": "inside", "matches": pub(inside)}
        if len(inside) > 1:
            return {"status": "multiple", "matches": pub(inside)}
        if edge or inside:
            return {"status": "on_boundary", "matches": pub(inside + edge)}
        return {"status": "outside", "matches": []}


def _crs_name(collection: dict) -> str:
    crs = collection.get("crs")
    if crs is None:
        return "crs84"          # RFC 7946 default for GeoJSON without a crs member
    name = str((crs.get("properties") or {}).get("name", "")).lower()
    return name


def load_geojson_units(path: Path, level: int, id_field: str, name_field: str, parent_field: Optional[str] = None) -> tuple[list[dict], str]:
    collection = json.loads(Path(path).read_text(encoding="utf-8"))
    crs = _crs_name(collection)
    if crs not in ACCEPTED_CRS:
        raise ValueError(f"unsupported CRS {crs!r}: only WGS84-equivalent (CRS84/EPSG:4326) is accepted; no reprojection is performed")
    units = []
    for f in collection["features"]:
        p = f.get("properties") or {}
        geom = f.get("geometry")
        polys: list = []
        problem = None
        if geom is None:
            problem = "null geometry"
        else:
            try:
                polys = _polygons(geom)
            except (ValueError, KeyError) as exc:
                problem = f"unsupported geometry: {exc}"
            if not problem and not polys:
                problem = "empty geometry"
        units.append({"level": level, "pcode": p.get(id_field), "name": p.get(name_field),
                      "parent_pcode": p.get(parent_field) if parent_field else None,
                      "polygons": polys, "bbox": _bbox(polys) if polys else (0.0, 0.0, 0.0, 0.0),
                      "multipart": len(polys) > 1, "version": p.get("version"), "valid_on": p.get("valid_on"),
                      "geometry": geom, "properties": p, "geometry_problem": problem})
    return units, crs


def load_index(cfg: dict, root: Path, levels: tuple = (1, 2)) -> BoundaryIndex:
    src = cfg["sources"][cfg["active_source"]]
    base = root / src["local_dir"]
    units, crs = [], None
    for level in levels:
        u, crs = load_geojson_units(base / src["files"][level], level, src["id_field"][level], src["name_field"][level],
                                    (src.get("parent_id_field") or {}).get(level))
        units += u
    return BoundaryIndex(units, src, crs)


def unit_validity(unit: dict, bbox: Optional[dict] = None) -> tuple[bool, list[str]]:
    """Per-feature structural validity. Reports problems; never repairs geometry."""
    bbox = bbox or DEFAULT_BBOX
    notes: list[str] = []
    if unit.get("geometry_problem"):
        return False, [unit["geometry_problem"]]
    for i, poly in enumerate(unit["polygons"]):
        for j, ring in enumerate(poly):
            if len(ring) < 4:
                notes.append(f"polygon {i} ring {j}: fewer than 4 points")
            elif ring[0] != ring[-1]:
                notes.append(f"polygon {i} ring {j}: not closed")
            elif not all(math.isfinite(c) for pt in ring for c in pt[:2]):
                notes.append(f"polygon {i} ring {j}: non-finite coordinate")
            elif _ring_area(ring) <= 0:
                notes.append(f"polygon {i} ring {j}: zero area")
    x0, y0, x1, y1 = unit["bbox"]
    if not (bbox["lon_min"] <= x0 and x1 <= bbox["lon_max"] and bbox["lat_min"] <= y0 and y1 <= bbox["lat_max"]):
        notes.append("outside the Pakistan plausible extent")
    return not notes, notes


def _interior_point(unit: dict) -> Optional[tuple[float, float]]:
    """A point strictly inside the unit: midpoint of the widest scanline segment through the largest outer ring."""
    poly = max(unit["polygons"], key=lambda p: _ring_area(p[0]))
    ring = poly[0]
    ys = [p[1] for p in ring]
    best = None
    for frac in (0.5, 0.4, 0.6, 0.3, 0.7):
        y = min(ys) + (max(ys) - min(ys)) * frac
        xs = sorted((ring[i][0] + (y - ring[i][1]) * (ring[i + 1][0] - ring[i][0]) / (ring[i + 1][1] - ring[i][1]))
                    for i in range(len(ring) - 1) if (ring[i][1] > y) != (ring[i + 1][1] > y))
        for a, b in zip(xs[0::2], xs[1::2]):
            mid = ((a + b) / 2, y)
            if (best is None or b - a > best[0]) and polygon_state(mid[0], mid[1], poly) == 1:
                best = (b - a, mid)
        if best:
            return best[1][1], best[1][0]
    return None


def validate_index(index: BoundaryIndex, bbox: Optional[dict] = None) -> dict:
    """Structural validation report. Not a full topology check (no self-intersection test)."""
    bbox = bbox or DEFAULT_BBOX
    problems: list[str] = []
    rep: dict[str, Any] = {"crs": index.crs, "crs_accepted": index.crs in ACCEPTED_CRS}
    for level in (1, 2):
        us = index.level(level)
        rep[f"level{level}_count"] = len(us)
        names = [match_key(u["name"]) for u in us]
        dup = sorted({n for n in names if names.count(n) > 1})
        rep[f"level{level}_duplicate_names"] = dup
        rep[f"level{level}_missing_ids"] = sum(1 for u in us if not u["pcode"])
        rep[f"level{level}_multipart"] = sum(1 for u in us if u["multipart"])
        if dup:
            problems.append(f"level {level} duplicate names {dup}")
        if rep[f"level{level}_missing_ids"]:
            problems.append(f"level {level} units without identifier")
    bad_ring = out_of_country = 0
    null_or_empty = [u["pcode"] for u in index.units if u.get("geometry_problem")]
    rep["null_or_empty_geometries"] = null_or_empty
    if null_or_empty:
        problems.append(f"{len(null_or_empty)} null/empty geometries")
    ids = [(u["level"], u["pcode"]) for u in index.units if u["pcode"]]
    rep["duplicate_feature_ids"] = sorted({str(i) for i in ids if ids.count(i) > 1})
    if rep["duplicate_feature_ids"]:
        problems.append("duplicate feature ids")
    for u in index.units:
        if u.get("geometry_problem"):
            continue
        for poly in u["polygons"]:
            for ring in poly:
                finite = all(math.isfinite(c) for p in ring for c in p[:2])
                if len(ring) < 4 or ring[0] != ring[-1] or not finite or _ring_area(ring) <= 0:
                    bad_ring += 1
        x0, y0, x1, y1 = u["bbox"]
        if not (bbox["lon_min"] <= x0 and x1 <= bbox["lon_max"] and bbox["lat_min"] <= y0 and y1 <= bbox["lat_max"]):
            out_of_country += 1
    rep["invalid_rings"], rep["units_outside_pakistan_extent"] = bad_ring, out_of_country
    if bad_ring:
        problems.append(f"{bad_ring} invalid rings")
    if out_of_country:
        problems.append(f"{out_of_country} units outside the Pakistan extent")
    prov = {u["pcode"] for u in index.level(1)}
    orphans = [u["pcode"] for u in index.level(2) if u["parent_pcode"] not in prov]
    rep["districts_with_unknown_parent"] = orphans
    if orphans:
        problems.append("districts with unknown parent province")
    overlaps, no_point = [], []
    for u in index.level(2):
        if u.get("geometry_problem"):
            continue
        pt = _interior_point(u)
        if pt is None:
            no_point.append(u["pcode"])
            continue
        hit = index.locate(pt[0], pt[1], 2)
        if hit["status"] != "inside" or hit["matches"][0]["pcode"] != u["pcode"]:
            overlaps.append({"pcode": u["pcode"], "status": hit["status"], "hits": [m["pcode"] for m in hit["matches"]]})
    rep["overlap_sample_test"] = {"method": "interior scanline point of each district must fall inside exactly itself",
                                  "failures": overlaps, "units_without_test_point": no_point}
    if overlaps:
        problems.append(f"{len(overlaps)} districts failed the interior-point overlap test")
    rep["problems"], rep["valid"] = problems, not problems
    return rep


# ---------------------------------------------------------------- crosswalk
def build_crosswalk(index: BoundaryIndex, canonical_units: list[dict], declared_aliases: dict[str, str]) -> list[dict]:
    """Deterministic boundary -> canonical crosswalk. NO fuzzy matching.

    canonical_units: [{"id", "name", "level", "province", "aliases"}]. Level-2 matches must agree on province,
    otherwise the result is 'ambiguous' (kept visible, never auto-resolved).
    """
    by_level: dict[int, dict[str, list[tuple[dict, str]]]] = {1: {}, 2: {}}
    for c in canonical_units:
        if c["level"] not in by_level:
            continue
        by_level[c["level"]].setdefault(match_key(c["name"]), []).append((c, "exact"))
        for a in c.get("aliases") or []:
            by_level[c["level"]].setdefault(match_key(a), []).append((c, "alias"))
    declared = {match_key(k): v for k, v in declared_aliases.items()}
    canon_by_name = {(c["level"], match_key(c["name"])): c for c in canonical_units}

    def resolve(level: int, name: str, province: Optional[str]) -> tuple[Optional[dict], str, str, str]:
        key = match_key(name)
        cands = list(by_level[level].get(key, []))
        basis = "canonical_name"
        if not cands and key in declared:
            tgt = canon_by_name.get((level, match_key(declared[key])))
            if tgt:
                cands, basis = [(tgt, "alias")], "declared_crosswalk_alias"
        if not cands:
            return None, "unmatched", "none", "no canonical unit with this name or declared alias"
        uniq = {c["id"]: (c, kind) for c, kind in cands}
        if len(uniq) > 1:
            return None, "ambiguous", basis, f"name matches {len(uniq)} canonical units"
        c, kind = next(iter(uniq.values()))
        if level == 2 and province and c.get("province") and match_key(province) != match_key(c["province"]):
            return None, "ambiguous", basis, f"province mismatch: boundary {province!r} vs canonical {c['province']!r}"
        return c, kind, ("canonical_alias" if kind == "alias" and basis == "canonical_name" else basis), ""

    prov_name = {}
    rows = []
    for level in (1, 2):
        for u in sorted(index.level(level), key=lambda x: str(x["pcode"])):
            parent_province = prov_name.get(u["parent_pcode"]) if level == 2 else None
            c, status, basis, note = resolve(level, u["name"], parent_province)
            if level == 1:
                prov_name[u["pcode"]] = c["name"] if c else u["name"]
            rows.append({"boundary_source_id": u["pcode"], "boundary_name": u["name"], "boundary_level": level,
                         "boundary_parent_id": u["parent_pcode"],
                         "pori_admin_unit_id": c["id"] if c else None, "pori_admin_unit_name": c["name"] if c else None,
                         "match_status": status, "match_basis": basis,
                         "confidence": {"exact": "high", "alias": "medium"}.get(status),
                         "validation_status": "pending_manual_review", "note": note or None})
    return rows


MATCHED = {"exact", "alias", "manual_verified"}


def crosswalk_lookup(rows: list[dict]) -> dict[tuple[int, str], dict]:
    return {(r["boundary_level"], r["boundary_source_id"]): r for r in rows}


def locate_station(index: BoundaryIndex, crosswalk: dict, lat: float, lon: float) -> dict:
    """station coordinate -> district polygon -> canonical unit. Result is always labelled coordinate_based."""
    hit = index.locate(lat, lon, 2)
    out = {"geography_derivation": "coordinate_based", "boundary_source": index.source.get("dataset"),
           "boundary_version": index.source.get("version"), "boundary_level": 2, "boundary_match_basis": "point_in_polygon",
           "polygon_status": hit["status"], "boundary_unit_name": None, "boundary_pcode": None,
           "boundary_confidence": None, "pori_admin_unit_id": None, "pori_admin_unit_name": None, "crosswalk_status": None}
    if hit["status"] != "inside":
        return out
    m = hit["matches"][0]
    cw = crosswalk.get((2, m["pcode"]), {})
    out.update(boundary_unit_name=m["name"], boundary_pcode=m["pcode"], boundary_confidence="medium",
               crosswalk_status=cw.get("match_status", "unmatched"))
    if cw.get("match_status") in MATCHED:
        out.update(pori_admin_unit_id=cw["pori_admin_unit_id"], pori_admin_unit_name=cw["pori_admin_unit_name"])
    return out


def locate_within_radius(index: BoundaryIndex, crosswalk: dict, lat: float, lon: float, radius_m: float,
                         rings: int = 4, bearings: int = 16) -> dict:
    """Task 38 -- district attribution of a coordinate that is only known to within `radius_m` metres.

    The centre and `rings` x `bearings` probe points out to `radius_m` must ALL fall inside the same single boundary district; otherwise the
    attribution depends on where inside the uncertainty disc the true position is, and it is refused (`stable` False). Deterministic."""
    centre = locate_station(index, crosswalk, lat, lon)
    units = {centre["boundary_pcode"]} if centre["polygon_status"] == "inside" else {None}
    for r in range(1, rings + 1):
        d = radius_m * r / rings
        for k in range(bearings):
            a = 2 * math.pi * k / bearings
            p = locate_station(index, crosswalk, lat + d * math.sin(a) / 111320.0, lon + d * math.cos(a) / (111320.0 * math.cos(math.radians(lat))))
            units.add(p["boundary_pcode"] if p["polygon_status"] == "inside" else None)
    return {**centre, "position_uncertainty_m": radius_m, "probe_units": sorted(u or "outside/overlap" for u in units),
            "stable": len(units) == 1 and None not in units}
