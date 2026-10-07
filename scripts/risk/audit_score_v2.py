"""Task 36 -- EVIDENCE AUDIT for an operational risk score v2, over the real local Gold datasets (no database writes, deterministic, idempotent).

For every signal domain: rows, geography resolution, date range, continuity, prior-history depth, whether a defensible normalization exists, how many observations are
ELIGIBLE under the evidence contract (config/risk_score_v2.yaml, pipeline/risk/scoring_v2.py), why the rest are not, and what the contract would need to produce a score.
Then every (admin unit, date) cell is assessed and the outcome is decided mechanically:
  A  at least one cell satisfies every requirement INCLUDING evidence-based weights  -> those cells would be scored
  B  none does                                                                        -> risk_score stays NULL; the framework and this audit are the deliverable
Writes data/analytics/risk/score_v2_audit.json. Usage: python scripts/risk/audit_score_v2.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.risk import scoring_v2 as S  # noqa: E402
from pipeline.risk.config import load_config, load_score_config  # noqa: E402
from pipeline.risk.coverage import coverage_matrix  # noqa: E402
from pipeline.risk.normalization import history_before, percentile_rank_strict  # noqa: E402
from pipeline.risk.signals import extract_signals  # noqa: E402
from scripts.risk import run_risk_engine as RUN  # noqa: E402

OUT = PROJECT_ROOT / "data" / "analytics" / "risk" / "score_v2_audit.json"
DOMAINS = ("rainfall", "weather", "gauge", "air_quality", "hazard_alert", "disaster_event")


def _gaps(dates: list[str]) -> tuple[int, int]:
    """(span in days, longest gap between consecutive distinct observation dates)."""
    ds = sorted({dt.date.fromisoformat(d[:10]) for d in dates})
    if len(ds) < 2:
        return (1 if ds else 0), 0
    return (ds[-1] - ds[0]).days + 1, max((b - a).days for a, b in zip(ds, ds[1:]))


def build_observations(gold: dict, cfg: dict, caveated: set[int]) -> tuple[dict, list[dict], dict]:
    """-> ({(unit, date): [observation]}, unresolved observations, per-(unit,domain) series)."""
    sig = extract_signals(gold, cfg)
    min_hist = cfg["normalization"]["min_history_observations"]
    series: dict[tuple, dict[str, float]] = defaultdict(dict)
    for domain, obs in sig["numeric"].items():
        for (unit, date), o in obs.items():
            series[(unit, domain)][date] = o["raw_value"]
    cells: dict[tuple, list[dict]] = defaultdict(list)
    for domain, obs in sig["numeric"].items():
        for (unit, date), o in sorted(obs.items()):
            hist = history_before(series[(unit, domain)], date)
            cells[(unit, date)].append({"domain": domain, "unit": unit, "cell_date": date, "obs_date": date, "value": o["raw_value"],
                                        "normalized": percentile_rank_strict(o["raw_value"], hist, min_hist[domain]), "history_count": len(hist),
                                        "geography_status": "resolved", "geography_caveat": unit in caveated, "source": o["source"],
                                        "source_record_ids": o["source_record_ids"]})
    for a in sig["alerts"]:
        d = a["start"]
        cells[(a["unit"], d)].append({"domain": "hazard_alert", "unit": a["unit"], "cell_date": d, "obs_date": d, "value": 1.0, "normalized": None, "history_count": 0,
                                      "geography_status": "resolved", "geography_caveat": a["unit"] in caveated, "source": a["source"], "source_record_ids": [a["alert_id"]]})
    for unit, dates in sig["events"].items():
        for d, eid in zip(dates, sig["event_ids"][unit]):
            cells[(unit, d)].append({"domain": "disaster_event", "unit": unit, "cell_date": d, "obs_date": d, "value": 1.0, "normalized": None, "history_count": 0,
                                     "geography_status": "resolved", "geography_caveat": unit in caveated, "source": "ndma", "source_record_ids": [eid]})
    unresolved = [{"domain": u["domain"], "unit": None, "cell_date": u.get("date"), "obs_date": u.get("date"), "value": u.get("raw_value", 1.0), "normalized": None,
                   "history_count": 0, "geography_status": u.get("resolution_status") or "unresolved", "geography_caveat": False, "source": None, "source_record_ids": []}
                  for u in sig["unresolved"]]
    return cells, unresolved, series


def run(gold: dict | None = None, info: dict | None = None) -> dict:
    cfg, sc = load_config(), load_score_config()
    if gold is None:
        gold = {k: RUN._read(v) for k, v in RUN.FILES.items()}
        info = RUN._unit_info()
        RUN._apply_gauge_geography(gold, info)
    caveated = RUN._caveated(info or {})
    cells, unresolved, series = build_observations(gold, cfg, caveated)
    cov = coverage_matrix(gold)

    per_domain = {d: Counter() for d in DOMAINS}
    reasons: dict[str, Counter] = {d: Counter() for d in DOMAINS}
    abst, score_cells, groups_hist, prov_total, prov_ok = Counter(), 0, Counter(), 0, 0
    for key in sorted(cells):
        res = S.assess_cell(cells[key], sc)
        for a in res["contributing_signals"] + res["excluded_signals"]:
            per_domain[a["domain"]][a["eligibility"]] += 1
            reasons[a["domain"]][(a["eligibility"], a["reason"])] += 1
            prov_total += 1
            prov_ok += bool(a["provenance"]["source_record_ids"])
        for r in res["abstention_reasons"]:
            abst[r] += 1
        groups_hist[res["contributing_group_count"]] += 1
        score_cells += res["risk_score"] is not None
    for u in unresolved:
        a = S.assess_signal(u, sc)
        if a["domain"] in per_domain:
            per_domain[a["domain"]][a["eligibility"]] += 1
            reasons[a["domain"]][(a["eligibility"], a["reason"])] += 1

    domains = {}
    for d in DOMAINS:
        c = cov.get(d, {})
        units = {u for (u, dom) in series if dom == d}
        longest_series = max((len(series[(u, d)]) for u in units), default=0)
        dates = [x for (u, dom), s in series.items() if dom == d for x in s]
        span, gap = _gaps(dates)
        numeric = d in sc["numeric_domains"]
        elig = per_domain[d][S.ELIGIBLE]
        if d in sc.get("contextual_domains", {}):
            decision, why = "CONTEXTUAL", sc["contextual_domains"][d]
        elif not numeric:
            decision, why = "EXCLUDED", "no defensible numeric normalization"
        elif elig == 0:
            top = reasons[d].most_common(1)
            decision, why = "NO_ELIGIBLE_OBSERVATION", (top[0][0][1] if top else "no observation")
        else:
            decision, why = "ELIGIBLE_OBSERVATIONS_EXIST", "individual observations satisfy the contract; aggregation is still blocked (see outcome)"
        domains[d] = {"rows": c.get("total_source_observations"), "resolved_rows": c.get("resolved_observations"), "resolved_pct": c.get("resolved_pct"),
                      "distinct_geographies_resolved": c.get("distinct_geographies_resolved"), "date_min": c.get("date_min"), "date_max": c.get("date_max"),
                      "distinct_dates": c.get("distinct_dates"), "observation_span_days": span, "longest_gap_days": gap,
                      "units_with_series": len(units), "longest_unit_history_observations": longest_series,
                      "history_needed_for_score": sc["min_history_for_score"], "historical_reference_available": longest_series >= sc["min_history_for_score"] + 1,
                      "normalization": S.NORMALIZATION_METHOD if numeric else None, "independence_group": sc["independence_groups"].get(d),
                      "eligibility_counts": dict(sorted(per_domain[d].items())),
                      "top_reasons": [{"eligibility": e, "reason": r, "count": n} for (e, r), n in sorted(reasons[d].items(), key=lambda kv: (-kv[1], kv[0]))[:4]],
                      "decision": decision, "decision_reason": why}
    eligible_cells = sum(n for k, n in groups_hist.items() if k >= 1)
    two_group_cells = sum(n for k, n in groups_hist.items() if k >= sc["required_independent_groups"])
    weights = S.validate_weights(sc)
    outcome = "A" if score_cells > 0 else "B"
    return {"audit_version": "1.0.0", "score_version": sc["score_version"], "scoring_enabled": bool(sc["enabled"]), "evidence_based_weights_defined": sorted(weights),
            "outcome": outcome, "numeric_score_enabled": score_cells > 0, "cells_assessed": len(cells), "cells_scored": score_cells,
            "cells_abstained": len(cells) - score_cells, "cells_with_at_least_one_eligible_signal_group": eligible_cells,
            "cells_with_required_independent_groups": two_group_cells, "required_independent_groups": sc["required_independent_groups"],
            "contributing_group_histogram": {str(k): v for k, v in sorted(groups_hist.items())}, "abstention_reason_counts": dict(sorted(abst.items())),
            "domains": domains, "provenance_coverage": {"assessed_signals": prov_total, "with_source_record_ids": prov_ok,
                                                         "pct": round(100 * prov_ok / prov_total, 2) if prov_total else None},
            "excluded_inputs": {"documents_rag": "documentary evidence is never a numeric input", "ml_predictions": "Task 33 baseline forecasts are BASELINE_ONLY, not validated ML; contextual only",
                                "reservoir": "not attributable to an admin unit", "gauge_secondary_candidates": "no authoritative eligible station mapping (Task 24): gauge is UNRESOLVED_GEOGRAPHY",
                                "provisional_thresholds": "status cut points are PROVISIONAL and are not treated as ground truth"},
            "conclusion": ("A numeric score is NOT defensible yet: no evidence-based weights exist, and " + (
                f"only {two_group_cells} of {len(cells)} cells even have {sc['required_independent_groups']} independent eligible signal groups." if score_cells == 0 else "see cells_scored.")
                           if outcome == "B" else "scored cells exist")}


def main() -> int:
    report = run()
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "domains"}, indent=2))
    for d, x in report["domains"].items():
        print(f"{d:15} rows={x['rows']} resolved={x['resolved_pct']}% geos={x['distinct_geographies_resolved']} {x['date_min']}..{x['date_max']} dates={x['distinct_dates']} "
              f"max_hist={x['longest_unit_history_observations']} elig={x['eligibility_counts']} -> {x['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
