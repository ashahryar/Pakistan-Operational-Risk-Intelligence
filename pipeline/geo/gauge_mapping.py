"""Station -> admin-unit mapping with explicit evidence tiers and a CONFIG-DRIVEN eligibility policy.

Evidence (config/gauge_station_evidence.yaml) -> mapping status:
  authoritative district statement                -> resolved_authoritative
  authoritative coordinates + accepted boundary    -> resolved_coordinate   (derivation = coordinate_based)
  official_secondary                               -> resolved_source_reported (derivation = source_reported)
  secondary                                        -> resolved_inferred        (derivation = inferred)
  conflicting candidates                           -> ambiguous
  candidate is a caveated seed unit                -> caveated
  nothing usable                                   -> unresolved
A status is only ELIGIBLE for admin risk when config policy (config/admin_boundary_sources.yaml `policy:`) allows
that evidence status. By default only `authoritative` evidence is eligible; secondary, official_secondary,
inferred, ambiguous, caveated and unresolved never are. A coordinate-derived result is always labelled
`coordinate_based`, never `authoritative_source_reported`.

River/basin context is carried separately (pipeline.geo.hydrography) and never becomes an admin unit.
Station geography is treated as static: no relocation evidence exists and no effective dates are invented.
"""

from __future__ import annotations

from typing import Any, Optional

from pipeline.geo.boundaries import BoundaryIndex, locate_station, locate_within_radius, validate_coordinate
from pipeline.geo.gauge_station import match_key

ELIGIBLE_STATUSES = {"resolved_authoritative", "resolved_coordinate", "resolved_source_reported"}
STATUSES = ELIGIBLE_STATUSES | {"resolved_inferred", "ambiguous", "caveated", "unresolved"}
EVIDENCE_STATUSES = {"authoritative", "official_secondary", "secondary", "conflicting", "unresolved"}
_RANK = {"authoritative": 3, "official_secondary": 2, "secondary": 1}
_DEFAULT_POLICY = {"eligible_evidence_statuses": ["authoritative"], "official_secondary_eligible": False,
                   "secondary_eligible": False, "allow_coordinate_derived_eligibility": False,
                   "min_coordinate_decimals": 3}


def _blank(station: dict, evidence_cfg: dict) -> dict:
    return {
        "station_key": station["station_key"], "station_name": station["station_name"],
        "normalized_station_name": station["normalized_station_name"], "source": station["source"],
        "admin_unit_id": None, "admin_unit_name": None, "admin_level": None, "province": None,
        "mapping_status": "unresolved", "mapping_basis": "none", "mapping_confidence": None,
        "mapping_source": None, "mapping_source_record": None, "caveat": None,
        "geography_derivation": "none",
        "eligible_for_admin_risk": False, "ineligibility_reason": "no_evidence",
        "evidence": [], "coordinate_validation": None,
        "boundary_source": None, "boundary_version": None, "boundary_level": None, "boundary_unit_name": None,
        "boundary_pcode": None, "boundary_match_basis": None, "boundary_confidence": None,
        "mapping_version": evidence_cfg["mapping_version"], "mapping_date": evidence_cfg["mapping_date"],
        "validation_status": evidence_cfg.get("validation_status", "pending_manual_review"),
        "temporal_assumption": "station geography treated as static; no relocation evidence; no effective dates",
    }


def _compact(e: dict) -> dict:
    keys = ("station_name", "source", "source_type", "source_url", "source_record", "station_id", "latitude",
            "longitude", "position_uncertainty_m", "district", "tehsil", "river", "basin", "evidence_status", "evidence_strength", "notes", "retrieved",
            "source_title", "source_organization", "source_page", "station_name_in_source", "source_statement")
    return {k: e.get(k) for k in keys}


def _eligible_by_policy(evidence_status: str, derivation: str, policy: dict, boundary_ok: bool) -> bool:
    if evidence_status == "official_secondary":
        return bool(policy.get("official_secondary_eligible"))
    if evidence_status == "secondary":
        return bool(policy.get("secondary_eligible"))
    if evidence_status not in policy.get("eligible_evidence_statuses", []):
        return False
    if derivation == "coordinate_based":
        return bool(policy.get("allow_coordinate_derived_eligibility")) and boundary_ok
    return True


def build_mapping(inventory: list[dict], evidence_cfg: dict, units_by_name: dict[str, dict], caveated_names: set[str],
                  boundary: Optional[BoundaryIndex] = None, crosswalk: Optional[dict] = None,
                  policy: Optional[dict] = None, bbox: Optional[dict] = None) -> list[dict]:
    """units_by_name: {admin unit name: {"id", "level", "province"}} from geo.admin_unit (read-only)."""
    policy = {**_DEFAULT_POLICY, **(policy or {})}
    boundary_ok = bool(boundary and boundary.source.get("accepted_for_coordinate_mapping"))
    by_station: dict[str, list[dict]] = {}
    for e in evidence_cfg.get("evidence") or []:
        by_station.setdefault(match_key(e["station_name"]), []).append(e)
    out = []
    for st in inventory:
        m = _blank(st, evidence_cfg)
        entries = by_station.get(st["match_key"], [])
        if not entries:
            out.append(m)
            continue
        m["evidence"] = [_compact(e) for e in entries]
        m["mapping_source"] = "; ".join(sorted({e["source"] for e in entries}))
        m["mapping_source_record"] = "; ".join(f"{e['source']}: {e['source_record']}" for e in entries)
        notes: list[str] = []
        cands: list[dict] = []          # {unit, evidence_status, derivation}
        for e in entries:
            es = e.get("evidence_status", "unresolved")
            if e.get("latitude") is not None and e.get("longitude") is not None:
                v = validate_coordinate(e["latitude"], e["longitude"], bbox, policy.get("min_coordinate_decimals", 3))
                m["coordinate_validation"] = v
                if not v["valid"]:
                    notes.append(f"coordinates rejected ({', '.join(v['flags'])}); not used")
                elif boundary is None:
                    notes.append("coordinates valid but no boundary dataset loaded; not mapped")
                else:
                    unc = e.get("position_uncertainty_m")
                    if unc:                 # coordinate known only to within `unc` metres: attribution must hold across the whole disc
                        loc = locate_within_radius(boundary, crosswalk or {}, float(e["latitude"]), float(e["longitude"]), float(unc))
                    else:
                        loc = locate_station(boundary, crosswalk or {}, float(e["latitude"]), float(e["longitude"]))
                    if not (unc and loc["polygon_status"] == "inside" and not loc["stable"]):      # an unstable attribution is not recorded as the boundary unit
                        m.update({k: loc[k] for k in ("boundary_source", "boundary_version", "boundary_level", "boundary_unit_name",
                                                      "boundary_pcode", "boundary_match_basis", "boundary_confidence")})
                    if loc["polygon_status"] != "inside":
                        notes.append(f"coordinate polygon result {loc['polygon_status']}; no district assigned")
                    elif unc and not loc["stable"]:
                        notes.append(f"coordinate attribution is not stable within the stated {unc} m position uncertainty "
                                     f"(probe districts {loc['probe_units']}); no district assigned")
                    elif loc["pori_admin_unit_name"] is None:
                        notes.append(f"coordinate falls in boundary district {loc['boundary_unit_name']!r} which has no "
                                     f"canonical match (crosswalk {loc['crosswalk_status']})")
                    else:
                        cands.append({"unit": loc["pori_admin_unit_name"], "evidence_status": es, "derivation": "coordinate_based"})
            if e.get("district"):
                deriv = "source_reported" if es in ("authoritative", "official_secondary") else "inferred"
                cands.append({"unit": e["district"], "evidence_status": es, "derivation": deriv})
        names = sorted({c["unit"] for c in cands})
        if any(n in caveated_names for n in names):
            cav = next(n for n in names if n in caveated_names)
            u = units_by_name.get(cav) or {}
            others = [n for n in names if n != cav]
            m.update(mapping_status="caveated", mapping_basis="name_match_legacy", mapping_confidence="low",
                     geography_derivation="inferred", admin_unit_id=u.get("id"), admin_unit_name=cav,
                     admin_level=u.get("level"), province=u.get("province"),
                     caveat=(f"{cav!r} is a caveated Task 10 seed row (not a real district); the name match is not an "
                             "authoritative station location. "
                             + (f"Secondary references place the station in {others}, which is not adopted (not authoritative). " if others else "")
                             + "Hydrographic location is its primary representation."),
                     ineligibility_reason="caveated_geography")
        elif len(names) > 1 or any(e.get("evidence_status") == "conflicting" for e in entries):
            m.update(mapping_status="ambiguous", mapping_basis="conflicting_evidence", mapping_confidence="low",
                     caveat=f"conflicting candidate admin units {names}; none selected (all evidence records preserved)",
                     ineligibility_reason="ambiguous_mapping")
        elif not names:
            m.update(mapping_basis="no_usable_evidence", ineligibility_reason="no_usable_evidence",
                     caveat=None if notes else "evidence present but names no admin unit")
        else:
            name = names[0]
            best = max(cands, key=lambda c: _RANK.get(c["evidence_status"], 0))
            unit = units_by_name.get(name)
            if unit is None:
                m.update(mapping_basis="evidence_without_canonical_unit", ineligibility_reason="admin_unit_not_in_canonical_geography",
                         caveat=f"evidence names {name!r} but geo.admin_unit has no such unit")
            else:
                es, deriv = best["evidence_status"], best["derivation"]
                if es == "authoritative":
                    status = "resolved_coordinate" if deriv == "coordinate_based" else "resolved_authoritative"
                    basis = "coordinate_point_in_polygon" if deriv == "coordinate_based" else "authoritative_source"
                    conf = "high" if deriv != "coordinate_based" else "medium"
                elif es == "official_secondary":
                    status, basis, conf = "resolved_source_reported", "official_secondary_source", "medium"
                else:
                    status, basis, conf = "resolved_inferred", "inferred", "low"
                m.update(mapping_status=status, mapping_basis=basis, mapping_confidence=conf, geography_derivation=deriv,
                         admin_unit_id=unit["id"], admin_unit_name=name, admin_level=unit["level"], province=unit.get("province"))
                if _eligible_by_policy(es, deriv, policy, boundary_ok):
                    m.update(eligible_for_admin_risk=True, ineligibility_reason=None)
                else:
                    m.update(ineligibility_reason=f"{es}_evidence_not_eligible_by_policy",
                             caveat="evidence class is not eligible under the configured policy; pending manual review; not used for risk")
        if notes and not m["caveat"]:
            m["caveat"] = "; ".join(notes)
        elif notes:
            m["caveat"] += " | " + "; ".join(notes)
        out.append(m)
    keys = [x["station_key"] for x in out]
    assert len(keys) == len(set(keys))
    return out


def apply_to_gauge_rows(gauge_rows: list[dict], mapping: list[dict], inventory: list[dict]) -> list[dict]:
    """Return gauge rows whose geography is decided ONLY by an eligible mapping.

    Eligible -> resolved + mapping admin unit. Anything else -> resolution_status 'unresolved' and
    admin_unit_id None (the observation is preserved, with `geography_unresolved_reason`). The legacy
    Gold resolution is never trusted on its own. Inputs are not mutated.
    """
    by_key = {m["station_key"]: m for m in mapping}
    name_to_keys: dict[str, list[str]] = {}
    for s in inventory:
        name_to_keys.setdefault(s["match_key"], []).append(s["station_key"])
    from pipeline.geo.gauge_station import SOURCE
    out = []
    for r in gauge_rows:
        mk = match_key(r.get("station_name") or r.get("location_original"))
        keys = name_to_keys.get(mk, [])
        if len(keys) == 1:
            key = keys[0]
        else:
            rk = match_key(r.get("river_name"))
            key = f"{SOURCE}:{mk}:{rk}" if f"{SOURCE}:{mk}:{rk}" in by_key else None
        m = by_key.get(key) if key else None
        nr = dict(r)
        if m and m["eligible_for_admin_risk"]:
            nr.update(admin_unit_id=m["admin_unit_id"], resolution_status="resolved", station_key=key,
                      geography_mapping_status=m["mapping_status"], geography_derivation=m["geography_derivation"])
        else:
            nr.update(admin_unit_id=None, resolution_status="unresolved", station_key=key,
                      geography_mapping_status=(m or {}).get("mapping_status", "unresolved"),
                      geography_unresolved_reason=(m or {}).get("ineligibility_reason") or "station_not_in_inventory")
        out.append(nr)
    return out


def _count(rows: list[dict]) -> dict[str, int]:
    return {"resolved": sum(1 for r in rows if r.get("resolution_status") == "resolved" and r.get("admin_unit_id")),
            "total": len(rows)}


def before_after(gauge_rows: list[dict], mapped_rows: list[dict], inventory: list[dict], mapping: list[dict],
                 caveated_unit_ids: Optional[set] = None) -> list[dict]:
    """Observation-level coverage, before vs after Task 24.

    before = Task 23 behaviour: Gold's own resolution, where a caveated unit never drove a status.
    after  = only eligible mappings. 'candidate' rows count any admin_unit_id regardless of eligibility.
    """
    caveated_unit_ids = caveated_unit_ids or set()
    inv = {s["station_key"]: s for s in inventory}
    legacy = {s["station_key"]: s["legacy_gold_admin_unit_ids"] for s in inventory if s["legacy_gold_admin_unit_ids"]}
    before_eligible = {k for k, ids in legacy.items() if any(i not in caveated_unit_ids for i in ids)}
    b_obs_candidate = sum(inv[k]["observation_count"] for k in legacy)
    b_obs_eligible = sum(inv[k]["observation_count"] for k in before_eligible)
    a_eligible = {m["station_key"] for m in mapping if m["eligible_for_admin_risk"]}
    a_obs_eligible = sum(1 for r in mapped_rows if r.get("resolution_status") == "resolved" and r.get("admin_unit_id"))
    cand = {m["station_key"] for m in mapping if m["admin_unit_id"]}
    total = len(gauge_rows)
    st = lambda f: sum(1 for m in mapping if f(m))  # noqa: E731
    river = st(lambda m: inv[m["station_key"]]["river_context_status"] != "unresolved")
    basin = st(lambda m: inv[m["station_key"]]["basin_context_status"] != "unresolved")
    metrics = [
        ("distinct_gauge_stations", len(inventory), len(inventory)),
        ("stations_with_candidate_admin_geography", len(legacy), len(cand)),
        ("stations_eligible_for_admin_risk", len(before_eligible), len(a_eligible)),
        ("stations_unresolved_for_risk", len(inventory) - len(before_eligible), len(inventory) - len(a_eligible)),
        ("observations_with_candidate_admin_geography", b_obs_candidate, sum(inv[k]["observation_count"] for k in cand)),
        ("observations_attributable_for_risk", b_obs_eligible, a_obs_eligible),
        ("observations_unresolved_for_risk", total - b_obs_eligible, total - a_obs_eligible),
        ("stations_with_river_context", river, river),
        ("stations_with_basin_context", basin, basin),
        ("caveated_stations", len(legacy) and sum(1 for k in legacy if k not in before_eligible), st(lambda m: m["mapping_status"] == "caveated")),
        ("ambiguous_stations", 0, st(lambda m: m["mapping_status"] == "ambiguous")),
        ("inferred_stations_not_eligible", 0, st(lambda m: m["mapping_status"] == "resolved_inferred")),
    ]
    return [{"metric": k, "before_task24": b_, "after_task24": a_, "change": a_ - b_} for k, b_, a_ in metrics]


def top_unresolved(mapping: list[dict], inventory: list[dict], n: int = 10) -> list[dict]:
    inv = {s["station_key"]: s for s in inventory}
    rows = [{"station_key": m["station_key"], "station_name": m["station_name"], "mapping_status": m["mapping_status"],
             "observation_count": inv[m["station_key"]]["observation_count"],
             "river_name_reported": inv[m["station_key"]]["river_name_reported"]}
            for m in mapping if not m["eligible_for_admin_risk"]]
    rows.sort(key=lambda r: (-r["observation_count"], r["station_key"]))
    return rows[:n]


_: Optional[Any] = None
