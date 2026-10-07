"""Task 36 -- operational risk score v2 FOUNDATION: an auditable evidence contract between signal observations and a numeric score (pure; no I/O, no clock).

Layers (kept apart on purpose):
  1. observation   what was observed: domain, value, date, geography, source, history
  2. normalization percentile rank vs the unit's own strictly prior history (already computed by the engine); never invented here
  3. eligibility   ELIGIBLE | INSUFFICIENT_DATA | UNRESOLVED_GEOGRAPHY | INVALID | OUT_OF_SCOPE, with a reason
  4. contribution  only ELIGIBLE signals contribute; one signal per independence group (no summing of correlated domains)
  5. aggregation   a weighted mean of group contributions x 100, ONLY if every contributing group has an evidence-referenced weight and enough independent groups
                   contribute. Otherwise risk_score is None with explicit reasons. No default weights exist, so with the shipped config no score is produced.
The score, when it exists, is a provisional operational SIGNAL-INTENSITY index (0-100), not a probability, not calibrated, not a loss estimate, not ML.
Documents / RAG, ML forecasts, gauge-to-district guesses and unresolved geography are never inputs: they are not representable in an observation.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

ELIGIBLE = "ELIGIBLE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
UNRESOLVED_GEOGRAPHY = "UNRESOLVED_GEOGRAPHY"
INVALID = "INVALID"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
ELIGIBILITIES = (ELIGIBLE, INSUFFICIENT_DATA, UNRESOLVED_GEOGRAPHY, INVALID, OUT_OF_SCOPE)

SCORED = "SCORED"
ABSTAINED = "ABSTAINED"
NORMALIZATION_METHOD = "percentile_rank_strict_prior"

R_NO_ELIGIBLE = "NO_ELIGIBLE_SIGNAL"
R_TOO_FEW_GROUPS = "TOO_FEW_INDEPENDENT_SIGNAL_GROUPS"
R_NO_WEIGHTS = "NO_EVIDENCE_BASED_WEIGHTS"
R_DISABLED = "SCORE_V2_DISABLED"
ABSTENTION_TEXT = {
    R_NO_ELIGIBLE: "no signal satisfies the evidence contract for this area and date",
    R_TOO_FEW_GROUPS: "fewer independent signal groups contribute than the contract requires",
    R_NO_WEIGHTS: "no evidence-based weights exist for the contributing signal groups, so no defensible aggregate can be computed",
    R_DISABLED: "numeric scoring is disabled in config/risk_score_v2.yaml",
}


# The shipped contract, mirrored from config/risk_score_v2.yaml (the API image has no YAML parser; tests/risk/test_score_v2.py asserts the two are identical).
SERVING_CONFIG: dict = {
    "score_version": "operational-score-v2-foundation-1.0.0", "enabled": False,
    "scale": {"min": 0, "max": 100, "direction": "higher = higher operational signal intensity relative to the unit's own prior history; NOT a probability and NOT a loss estimate"},
    "min_history_for_score": 30, "required_independent_groups": 2,
    "independence_groups": {"rainfall": "hydromet_event", "gauge": "hydromet_event", "hazard_alert": "hydromet_event", "disaster_event": "hydromet_event",
                            "weather": "temperature", "air_quality": "air_quality"},
    "numeric_domains": ["rainfall", "weather", "gauge", "air_quality"],
    "contextual_domains": {"hazard_alert": "source severity labels are mapped to statuses by PROVISIONAL engine cut points; there is no normalization reference, so the alert stays contextual",
                           "disaster_event": "routine NDMA sitrep record counts with no baseline (engine: normalize=false); overlaps the hydromet event group"},
    "non_negative_domains": ["rainfall", "gauge", "air_quality"], "weights": {},
}


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def assess_signal(obs: dict, cfg: dict) -> dict:
    """Eligibility + contribution of ONE observation. `obs`: domain, unit, cell_date, obs_date, value, normalized, history_count, geography_status ('resolved' or other),
    geography_caveat (bool), source, source_record_ids. Returns the full audit record; `contribution` is set only when ELIGIBLE."""
    domain = obs.get("domain")
    rec = {"domain": domain, "source": obs.get("source"), "observation_date": obs.get("obs_date"), "cell_date": obs.get("cell_date"), "admin_unit_id": obs.get("unit"),
           "value": obs.get("value"), "normalization": {"method": NORMALIZATION_METHOD, "reference": "same unit, strictly earlier observations",
                                                         "history_count": obs.get("history_count"), "min_history": cfg["min_history_for_score"]},
           "normalized": obs.get("normalized"), "contribution": None, "eligibility": None, "reason": None, "independence_group": cfg["independence_groups"].get(domain),
           "provenance": {"source_record_ids": list(obs.get("source_record_ids") or []), "geography_status": obs.get("geography_status")}}

    def out(code: str, reason: str) -> dict:
        rec["eligibility"], rec["reason"] = code, reason
        return rec

    if domain not in cfg["independence_groups"]:
        return out(OUT_OF_SCOPE, "domain is not part of the operational signal set")
    if domain in cfg.get("contextual_domains", {}):
        return out(OUT_OF_SCOPE, "contextual domain: " + cfg["contextual_domains"][domain])
    if domain not in cfg["numeric_domains"]:
        return out(OUT_OF_SCOPE, "no defensible numeric normalization for this domain")
    if obs.get("geography_status") != "resolved" or obs.get("unit") is None or obs.get("geography_caveat"):
        return out(UNRESOLVED_GEOGRAPHY, "geography is unresolved, ambiguous or caveated; it is never mapped or guessed")
    v = obs.get("value")
    if v is not None and not _finite(v):
        return out(INVALID, "the observed value is not a finite number")
    if _finite(v) and domain in cfg.get("non_negative_domains", []) and v < 0:
        return out(INVALID, "a negative value is impossible for this domain (never clipped)")
    if v is None:
        return out(INSUFFICIENT_DATA, "no observation (a missing value is never treated as zero)")
    if obs.get("obs_date") != obs.get("cell_date"):
        return out(INSUFFICIENT_DATA, "the observation is not dated on the cell date (no carry-forward)")
    n = obs.get("normalized")
    if n is not None and (not _finite(n) or not 0.0 <= n <= 1.0):
        return out(INVALID, "the normalized value is outside [0, 1]")
    if n is None or (obs.get("history_count") or 0) < cfg["min_history_for_score"]:
        return out(INSUFFICIENT_DATA, f"fewer than {cfg['min_history_for_score']} prior observations of this unit and domain: no defensible normalization")
    rec["contribution"] = float(n)
    return out(ELIGIBLE, "satisfies the evidence contract")


def validate_weights(cfg: dict) -> dict:
    """Weights are accepted only with a positive number and a non-empty evidence reference."""
    ok = {}
    for group, w in (cfg.get("weights") or {}).items():
        if _finite((w or {}).get("weight")) and w["weight"] > 0 and str(w.get("evidence_reference") or "").strip():
            ok[group] = w
    return ok


def assess_cell(observations: Sequence[dict], cfg: dict) -> dict:
    """The score contract of one (admin unit, date) cell. Deterministic; the same observations always give the same result."""
    assessed = [assess_signal(o, cfg) for o in observations]
    eligible = [a for a in assessed if a["eligibility"] == ELIGIBLE]
    by_group: dict[str, list[dict]] = {}
    for a in eligible:
        by_group.setdefault(a["independence_group"], []).append(a)
    contributing, excluded = [], [a for a in assessed if a["eligibility"] != ELIGIBLE]
    for group in sorted(by_group):
        members = sorted(by_group[group], key=lambda a: (-a["contribution"], a["domain"]))
        contributing.append(members[0])                           # one signal per independence group: never summed
        for extra in members[1:]:
            excluded.append({**extra, "eligibility": OUT_OF_SCOPE, "contribution": None,
                             "reason": f"overlaps the '{group}' group already represented by '{members[0]['domain']}' (no summing of correlated domains)"})
    excluded.sort(key=lambda a: (str(a["domain"]), a["eligibility"], str(a["observation_date"])))     # deterministic whatever the input order
    weights = validate_weights(cfg)
    reasons = []
    if not contributing:
        reasons.append(R_NO_ELIGIBLE)
    elif len(contributing) < cfg["required_independent_groups"]:
        reasons.append(R_TOO_FEW_GROUPS)
    if contributing and any(c["independence_group"] not in weights for c in contributing):
        reasons.append(R_NO_WEIGHTS)
    if not cfg.get("enabled"):
        reasons.append(R_DISABLED)
    score: Optional[float] = None
    if not reasons:
        total = sum(weights[c["independence_group"]]["weight"] for c in contributing)
        score = round(100.0 * sum(weights[c["independence_group"]]["weight"] * c["contribution"] for c in contributing) / total, 4)
        assert 0.0 <= score <= 100.0
    return {"risk_score": score, "score_status": SCORED if score is not None else ABSTAINED, "score_version": cfg["score_version"],
            "eligible_signal_count": len(eligible), "contributing_group_count": len(contributing), "required_signal_count": cfg["required_independent_groups"],
            "contributing_signals": contributing, "excluded_signals": excluded, "abstention_reason": reasons[0] if reasons else None, "abstention_reasons": reasons,
            "abstention_text": ABSTENTION_TEXT[reasons[0]] if reasons else None,
            "score_provenance": {"aggregation": "weighted mean of independence-group contributions x 100" if score is not None else None,
                                 "weights": {c["independence_group"]: weights[c["independence_group"]] for c in contributing} if score is not None else {},
                                 "interpretation": "provisional operational signal-intensity index; not a probability, not calibrated, not ML"}}


def abstain_from_stored_row(row: dict, cfg: dict) -> dict:
    """The API representation for a STORED risk row. The stored row carries no per-signal history counts, so eligibility is NOT re-derived here; what holds for every row
    is the configuration-level fact: the score is abstained while no evidence-based weights exist (or scoring is disabled). Never fabricates a score."""
    if row.get("risk_score") is not None:
        return {"score_status": SCORED, "score_version": cfg["score_version"], "abstention_reason": None, "abstention_text": None, "contributing_signals": None}
    reasons = ([R_NO_WEIGHTS] if not validate_weights(cfg) else []) + ([R_DISABLED] if not cfg.get("enabled") else [])
    reason = reasons[0] if reasons else "NOT_COMPUTED_FOR_THIS_ROW"
    states = row.get("signals") or {}
    excluded = []
    for domain in cfg["independence_groups"]:
        if domain in cfg.get("contextual_domains", {}):
            excluded.append({"domain": domain, "eligibility": OUT_OF_SCOPE, "reason": "contextual domain"})
    observed = sorted(d for d, v in states.items() if v is not None)
    numeric = [d for d in cfg["numeric_domains"]]
    return {"score_status": ABSTAINED, "score_version": cfg["score_version"], "abstention_reason": reason,
            "abstention_text": ABSTENTION_TEXT.get(reason, "the score was not computed for this row"), "required_signal_count": cfg["required_independent_groups"],
            "contributing_signals": [], "excluded_signals": excluded, "observed_domains": observed,
            "evidence_available": observed, "evidence_missing": sorted(d for d in numeric if d not in observed),
            "evidence_required": evidence_required(cfg),
            "interpretation": INTERPRETATION}


INTERPRETATION = ("risk_status summarises the observed signals against PROVISIONAL thresholds. A null risk_score means no defensible numeric aggregate exists for this row; "
                  "it does NOT mean low risk or no risk. INSUFFICIENT_DATA means no usable signal was observed.")


def evidence_required(cfg: dict) -> list[str]:
    """What a numeric score would need (read from the contract, never invented)."""
    return [f"at least {cfg['required_independent_groups']} independent eligible signal groups for the same area and date "
            f"({', '.join(sorted(set(cfg['independence_groups'].values())))})",
            f"at least {cfg['min_history_for_score']} prior observations of each contributing signal for the same area",
            "a resolved, non-caveated geography backed by authoritative evidence",
            "a positive weight with a non-empty evidence reference for each contributing group (none exist)",
            "scoring enabled in config/risk_score_v2.yaml (currently disabled)"]
