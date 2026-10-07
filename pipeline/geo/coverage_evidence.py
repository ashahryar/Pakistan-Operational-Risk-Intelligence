"""Task 37 -- pure checks over the geography EVIDENCE: crosswalk relationships, gauge mapping states, coverage gap ranking.

No I/O, no clock, no database. Nothing here creates a mapping: it validates that every applied relationship is evidence-backed and
that no weaker state (UNVERIFIED, CONFLICTING, UNMATCHED, secondary-only) leaked into an applied/eligible result.
"""

from __future__ import annotations

from typing import Optional

MATCH_STATES = ("EXACT", "ALIAS", "UNMATCHED", "CONFLICTING", "UNVERIFIED")
APPLIED_STATES = ("EXACT", "ALIAS")
PROVENANCE_FIELDS = ("evidence_type", "evidence_source", "qualification", "status")
NEW_ALIAS_FIELDS = ("source_url", "evidence_date", "retrieved", "evidence_quote")     # required for an alias added with real evidence


def validate_relationship(rec: dict) -> list[str]:
    """Return the list of contract violations of one registry record (empty = valid)."""
    errs: list[str] = []
    state = rec.get("match_state")
    if state not in MATCH_STATES:
        errs.append(f"unknown match_state {state!r}")
    for f in PROVENANCE_FIELDS:
        if not str(rec.get(f) or "").strip():
            errs.append(f"missing {f}")
    applied = str(rec.get("status", "")).startswith("applied")
    if applied and state not in APPLIED_STATES:
        errs.append(f"{state} relationship must never be applied")
    if state in ("UNVERIFIED", "CONFLICTING", "UNMATCHED") and applied:
        errs.append("weak state marked applied")
    if rec.get("status") == "applied":                  # applied WITH new evidence: full provenance required
        for f in NEW_ALIAS_FIELDS:
            if not str(rec.get(f) or "").strip():
                errs.append(f"applied alias missing {f}")
        if rec.get("evidence_type") == "none_recorded":
            errs.append("a newly applied alias needs real evidence")
    return errs


def check_registry(registry: dict, crosswalk_rows: list[dict]) -> dict:
    """Cross-check the registry against the machine crosswalk. Returns counts and violations."""
    by_bid = {c["boundary_source_id"]: c for c in crosswalk_rows}
    violations: list[str] = []
    for rec in registry.get("relationships", []):
        for e in validate_relationship(rec):
            violations.append(f"{rec.get('canonical_name')}: {e}")
        bid = rec.get("boundary_source_id")
        if rec.get("status") == "applied" and bid in by_bid:
            c = by_bid[bid]
            if c["match_status"] != "alias" or c["pori_admin_unit_name"] != rec["canonical_name"]:
                violations.append(f"{rec['canonical_name']}: registry says applied but crosswalk has {c['match_status']}/{c['pori_admin_unit_name']}")
            if rec.get("canonical_admin_unit_id") is not None and c["pori_admin_unit_id"] != rec["canonical_admin_unit_id"]:
                violations.append(f"{rec['canonical_name']}: canonical id changed ({c['pori_admin_unit_id']} != {rec['canonical_admin_unit_id']})")
        if rec.get("match_state") in ("UNVERIFIED", "CONFLICTING") and bid in by_bid and by_bid[bid]["match_status"] in ("exact", "alias"):
            violations.append(f"{rec['canonical_name']}: weak state leaked into the crosswalk as {by_bid[bid]['match_status']}")
    states: dict[str, int] = {}
    for rec in registry.get("relationships", []):
        states[rec.get("match_state")] = states.get(rec.get("match_state"), 0) + 1
    return {"relationships": len(registry.get("relationships", [])), "state_counts": dict(sorted(states.items())), "violations": violations}


def crosswalk_unit_ids_preserved(before_rows: list[dict], after_rows: list[dict]) -> bool:
    """A canonical id that was matched before must be matched to the same id after (ids are never altered)."""
    after = {c["boundary_source_id"]: c["pori_admin_unit_id"] for c in after_rows}
    return all(after.get(c["boundary_source_id"]) == c["pori_admin_unit_id"] for c in before_rows if c.get("pori_admin_unit_id") is not None)


def gauge_station_view(mapping: list[dict]) -> dict:
    """Group the Task 24/25 station mapping into the Task 37 vocabulary. Eligibility is read, never changed."""
    out = {"resolved": [], "unresolved": [], "conflicting": [], "secondary_only": [], "caveated": [], "eligible": []}
    for m in mapping:
        s = m["mapping_status"]
        row = {"station_key": m["station_key"], "station_name": m["station_name"], "mapping_status": s,
               "candidate_admin_unit": m.get("admin_unit_name"), "evidence_records": len(m.get("evidence") or []),
               "ineligibility_reason": m.get("ineligibility_reason")}
        if m.get("eligible_for_admin_risk"):
            out["eligible"].append(row)
        if s in ("resolved_authoritative", "resolved_coordinate", "resolved_source_reported"):
            out["resolved"].append(row)
        elif s == "ambiguous":
            out["conflicting"].append({**row, "conflict_status": "CONFLICTING",
                                       "claimed_districts": sorted({e["district"] for e in m["evidence"] if e.get("district")})})
        elif s == "caveated":
            out["caveated"].append(row)
        elif s == "resolved_inferred":
            out["secondary_only"].append(row)
        else:
            out["unresolved"].append(row)
    return out


def secondary_never_eligible(view: dict) -> bool:
    ids = {r["station_key"] for r in view["eligible"]}
    return not any(r["station_key"] in ids for k in ("secondary_only", "conflicting", "caveated", "unresolved") for r in view[k])


def rank_gaps(candidates: list[dict]) -> list[dict]:
    """Rank evidence gaps. Each candidate: name, units_unlocked, history_continuity (0-1), authority (0-3), normalizable (bool),
    precision (0-3), relevance (0-3), reliability (0-3), observations_unlocked. The score is a transparent sum of NON-weighted
    ordinal terms (documented in the status doc); raw row count is deliberately not an input. Ties break by name."""
    ranked = []
    for c in candidates:
        score = (min(c["units_unlocked"], 10) / 10 * 3 + c["history_continuity"] * 3 + c["authority"] + (3 if c["normalizable"] else 0)
                 + c["precision"] + c["relevance"] + c["reliability"])
        ranked.append({**c, "gap_score": round(score, 3)})
    ranked.sort(key=lambda r: (-r["gap_score"], r["name"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


_: Optional[int] = None
