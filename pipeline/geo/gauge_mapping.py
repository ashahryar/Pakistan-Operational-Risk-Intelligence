"""Station -> admin-unit mapping with explicit evidence tiers and an eligibility policy.

Hierarchy (highest evidence first):
  1 authoritative explicit station->admin-unit  -> resolved_authoritative   (eligible)
  2 authoritative coordinates + authoritative boundary polygons -> resolved_coordinate (eligible)
        NOT available in this project (no boundary dataset) -> never produced here
  3 source-reported admin unit                  -> resolved_source_reported (eligible)
  4 secondary / inferred evidence               -> resolved_inferred        (NOT eligible)
  conflicting candidates                        -> ambiguous                (NOT eligible)
  candidate is a caveated seed unit             -> caveated                 (NOT eligible)
  nothing                                       -> unresolved               (NOT eligible)

River/basin context is carried separately (pipeline.geo.hydrography) and never becomes an admin unit.
Station geography is treated as static: one mapping applies to all dates; no relocation evidence exists in
the source and no effective dates are invented. A mapping is only consumed when `eligible_for_admin_risk`.
"""

from __future__ import annotations

from typing import Any, Optional

from pipeline.geo.gauge_station import match_key

ELIGIBLE_STATUSES = {"resolved_authoritative", "resolved_coordinate", "resolved_source_reported"}
STATUSES = ELIGIBLE_STATUSES | {"resolved_inferred", "ambiguous", "caveated", "unresolved"}
_CLASS_TO_STATUS = {"authoritative": "resolved_authoritative", "source_reported": "resolved_source_reported",
                    "secondary": "resolved_inferred"}
_CLASS_TO_BASIS = {"authoritative": "authoritative_source", "source_reported": "source_reported", "secondary": "inferred"}
_CONF = {"authoritative": "high", "source_reported": "medium", "secondary": "low"}


def _blank(station: dict, evidence_cfg: dict) -> dict:
    return {
        "station_key": station["station_key"], "station_name": station["station_name"],
        "normalized_station_name": station["normalized_station_name"], "source": station["source"],
        "admin_unit_id": None, "admin_unit_name": None, "admin_level": None, "province": None,
        "mapping_status": "unresolved", "mapping_basis": "none", "mapping_confidence": None,
        "mapping_source": None, "mapping_source_record": None, "caveat": None,
        "eligible_for_admin_risk": False, "ineligibility_reason": "no_evidence",
        "mapping_version": evidence_cfg["mapping_version"], "mapping_date": evidence_cfg["mapping_date"],
        "validation_status": evidence_cfg.get("validation_status", "pending_manual_review"),
        "temporal_assumption": "station geography treated as static; no relocation evidence; no effective dates",
    }


def build_mapping(inventory: list[dict], evidence_cfg: dict, units_by_name: dict[str, dict],
                  caveated_names: set[str]) -> list[dict]:
    """units_by_name: {admin unit name: {"id", "level", "province"}} from geo.admin_unit (read-only)."""
    evidence = {match_key(k): v for k, v in (evidence_cfg.get("stations") or {}).items()}
    out = []
    for st in inventory:
        m = _blank(st, evidence_cfg)
        ev = evidence.get(st["match_key"], [])
        if not ev:
            out.append(m)
            continue
        names = sorted({e["admin_unit"] for e in ev})
        recs = "; ".join(f"{e['source']}: {e['record']}" for e in ev)
        m["mapping_source"] = "; ".join(sorted({e["source"] for e in ev}))
        m["mapping_source_record"] = recs
        legacy = [e for e in ev if e["class"] == "legacy"]
        if any(n in caveated_names for n in names) or (legacy and legacy[0]["admin_unit"] in caveated_names):
            cav_name = next(n for n in names if n in caveated_names)
            u = units_by_name.get(cav_name) or {}
            others = [e for e in ev if e["admin_unit"] != cav_name]
            m.update(mapping_status="caveated", mapping_basis="name_match_legacy", mapping_confidence="low",
                     admin_unit_id=u.get("id"), admin_unit_name=cav_name, admin_level=u.get("level"),
                     province=u.get("province"),
                     caveat=(f"{cav_name!r} is a caveated Task 10 seed row (not a real district); the name match is not an "
                             "authoritative station location. " + ("A secondary reference places the station in "
                             f"{others[0]['admin_unit']}, which is not adopted (not authoritative). " if others else "")
                             + "Hydrographic location is its primary representation."),
                     ineligibility_reason="caveated_geography")
            out.append(m)
            continue
        if len(names) > 1:
            m.update(mapping_status="ambiguous", mapping_basis="conflicting_evidence", mapping_confidence="low",
                     caveat=f"conflicting candidate admin units {names}; none selected",
                     ineligibility_reason="ambiguous_mapping")
            out.append(m)
            continue
        name = names[0]
        unit = units_by_name.get(name)
        e = ev[0]
        cls = e["class"]
        if unit is None:
            m.update(mapping_basis="evidence_without_canonical_unit", ineligibility_reason="admin_unit_not_in_canonical_geography",
                     caveat=f"evidence names {name!r} but geo.admin_unit has no such unit")
            out.append(m)
            continue
        status = _CLASS_TO_STATUS.get(cls, "resolved_inferred")
        m.update(mapping_status=status, mapping_basis=_CLASS_TO_BASIS.get(cls, "inferred"),
                 mapping_confidence=_CONF.get(cls, "low"), admin_unit_id=unit["id"], admin_unit_name=name,
                 admin_level=unit["level"], province=unit.get("province"))
        if status in ELIGIBLE_STATUSES:
            m.update(eligible_for_admin_risk=True, ineligibility_reason=None)
        else:
            m.update(ineligibility_reason="inferred_mapping_not_authoritative",
                     caveat="secondary/inferred evidence only; pending manual review; not used for risk")
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
                      geography_mapping_status=m["mapping_status"])
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
