"""Document geography via the existing canonical geography (scripts/geo): exact / alias / normalized matches only.

The resolver's fuzzy step is deliberately NOT accepted here -- a near-miss stays unresolved, with the original text kept.
No gauge-station mapping is used. Admin-unit ids come from a caller-supplied lookup (the read-only geo.admin_unit), so
the pure functions need no database.
"""

from __future__ import annotations

from typing import Optional

from scripts.geo.canonical_data import DISTRICTS, PROVINCES
from scripts.geo.resolver import resolve

ACCEPTED_METHODS = {"exact", "alias", "normalized"}


def _resolve(raw: str, pool: list[dict], lookup: dict[str, int]) -> dict:
    r = resolve(raw, pool)
    if r.status == "resolved" and r.match_method in ACCEPTED_METHODS:
        return {"raw": raw, "name": r.admin_unit_key, "admin_unit_id": lookup.get(r.admin_unit_key), "status": "resolved",
                "match_method": r.match_method}
    return {"raw": raw, "name": None, "admin_unit_id": None, "status": "unresolved" if r.status != "ambiguous" else "ambiguous",
            "match_method": r.match_method if r.status == "resolved" else r.status}


def resolve_provinces(names: list[str], lookup: dict[str, int]) -> list[dict]:
    return [_resolve(n, PROVINCES, lookup) for n in names]


def resolve_districts(names: list[str], lookup: dict[str, int]) -> list[dict]:
    caveated = {d["name"] for d in DISTRICTS if d.get("caveat")}
    out = []
    for n in names:
        r = _resolve(n, DISTRICTS, lookup)
        if r["name"] in caveated:                      # caveated seed rows are not real districts: keep the text, no unit
            r.update(name=None, admin_unit_id=None, status="unresolved", match_method="caveated_seed_unit")
        out.append(r)
    return out


def summarize_geography(provinces: list[dict], districts: list[dict], jurisdiction: Optional[dict] = None) -> dict:
    """-> province / admin_unit_* / provinces / districts / admin_unit_ids / geography_status / geography_text.
    `jurisdiction` is an already-resolved province for sources whose issuing authority covers exactly one province
    (basis recorded by the caller). A single admin unit is set only when exactly one province is established."""
    prov_ok = [p for p in provinces if p["status"] == "resolved"]
    if jurisdiction:
        prov_ok = [jurisdiction] + [p for p in prov_ok if p["name"] != jurisdiction["name"]]
    names = sorted({p["name"] for p in prov_ok})
    dist_ok = [d for d in districts if d["status"] == "resolved"]
    raw = [x["raw"] for x in provinces + districts]
    attempted = len(provinces) + len(districts)
    unresolved = [x for x in provinces + districts if x["status"] != "resolved"]
    if not attempted and not jurisdiction:
        status = "not_stated"
    elif not prov_ok and not dist_ok:
        status = "unresolved"
    elif unresolved:
        status = "partial"
    else:
        status = "resolved" if len(names) <= 1 else "resolved_multi"
    unit = prov_ok[0] if len(names) == 1 else None
    ids = sorted({u["admin_unit_id"] for u in prov_ok + dist_ok if u["admin_unit_id"] is not None})
    return {"province": names[0] if len(names) == 1 else None, "admin_unit_id": unit["admin_unit_id"] if unit else None,
            "admin_unit_name": unit["name"] if unit else None, "provinces": names,
            "districts": [{"raw": d["raw"], "name": d["name"], "admin_unit_id": d["admin_unit_id"], "status": d["status"]} for d in districts],
            "admin_unit_ids": ids, "geography_status": status,
            "geography_text": raw}
