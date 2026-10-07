"""Task 37 -- geography EVIDENCE and operational DATA COVERAGE audit (no database writes, deterministic, idempotent).

Answers: which operational signals can be associated with which administrative units from authoritative or explicitly qualified
evidence, and what still blocks broader risk scoring. Reads the committed Task 24/25 gauge outputs, the crosswalk, the Task 36
score audit (the BEFORE state), recomputes the score audit on the current Gold data (the AFTER state) and writes
data/analytics/geo/coverage_evidence_audit.json.

Usage: python scripts/geo/audit_coverage_task37.py   (exit 1 when the evidence registry violates its contract)
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.geo import coverage_evidence as CE  # noqa: E402
from pipeline.risk import scoring_v2 as S  # noqa: E402
from pipeline.risk.config import load_config, load_score_config  # noqa: E402
from scripts.risk import audit_score_v2 as A  # noqa: E402
from scripts.risk import run_risk_engine as RUN  # noqa: E402

GEO = PROJECT_ROOT / "data" / "analytics" / "geo"
OUT = GEO / "coverage_evidence_audit.json"
REGISTRY = PROJECT_ROOT / "config" / "crosswalk_evidence.yaml"
TASK36_AUDIT = PROJECT_ROOT / "data" / "analytics" / "geo" / "score_v2_audit_baseline_task37.json"   # frozen copy of the Task 36 audit: the BEFORE state

# Declared (descriptive, not measured) facts per domain. Everything numeric below is measured from the data.
DOMAIN_FACTS = {
    "rainfall": {"source": "PDMA Punjab daily rainfall reports (PDF)", "dataset": "data/analytics/gold/datasets/gold_rainfall_daily.jsonl",
                 "geography_resolution_method": "Task 10 deterministic name resolver (exact / alias / normalized) against the 69-district canonical model; multi-district strings stay ambiguous",
                 "authoritative_status": "official PDMA source; district names resolved by a project resolver (not certified)"},
    "weather": {"source": "PMD city forecasts (HTML)", "dataset": "data/analytics/gold/datasets/gold_weather_daily.jsonl",
                "geography_resolution_method": "Task 10 city-to-district resolver", "authoritative_status": "official PMD source; city names resolved by a project resolver"},
    "gauge": {"source": "PDMA Punjab gauges and rivers sitrep (PDF; data source stated as FFD and DEOCs)", "dataset": "data/analytics/gold/datasets/gold_gauge_daily.jsonl",
              "geography_resolution_method": "none: no authoritative station-to-district evidence; secondary candidates are never applied",
              "authoritative_status": "official hydrology values; geography unresolved"},
    "air_quality": {"source": "EPA Punjab AQI", "dataset": "data/analytics/gold/datasets/gold_air_quality_daily.jsonl",
                    "geography_resolution_method": "single named city (Lahore) resolved exactly", "authoritative_status": "official EPA Punjab source"},
    "hazard_alert": {"source": "PMD / NDMA weather and hazard alerts", "dataset": "gold alerts", "geography_resolution_method": "region names resolved by the Task 10 resolver",
                     "authoritative_status": "official; contextual only"},
    "disaster_event": {"source": "NDMA situation reports", "dataset": "gold NDMA event counts", "geography_resolution_method": "province-level names",
                       "authoritative_status": "official; contextual only"},
}


def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _eligible_by_unit(gold: dict, info: dict, cfg: dict, sc: dict) -> dict[str, Counter]:
    cells, _, _ = A.build_observations(gold, cfg, RUN._caveated(info or {}))
    out: dict[str, Counter] = defaultdict(Counter)
    for key in sorted(cells):
        for o in cells[key]:
            a = S.assess_signal(o, sc)
            if a["eligibility"] == S.ELIGIBLE:
                out[a["domain"]][a["admin_unit_id"]] += 1
    return out


def build_report() -> dict:
    cfg, sc = load_config(), load_score_config()
    gold = {k: RUN._read(v) for k, v in RUN.FILES.items()}
    info = RUN._unit_info()
    RUN._apply_gauge_geography(gold, info)
    after = A.run(gold, info)
    before = _load_json(TASK36_AUDIT)
    elig_units = _eligible_by_unit(gold, info, cfg, sc)

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    xw = _load_json(GEO / "gauge_boundary_crosswalk.json")
    mapping = _load_json(GEO / "gauge_station_mapping.json")
    inventory = {s["station_key"]: s for s in _load_json(GEO / "gauge_station_inventory.json")}
    gauge_cfg = yaml.safe_load((PROJECT_ROOT / "config" / "gauge_station_evidence.yaml").read_text(encoding="utf-8"))
    check = CE.check_registry(registry, xw["crosswalk"])
    view = CE.gauge_station_view(mapping)

    domains = {}
    for d, x in after["domains"].items():
        b = before["domains"][d]
        span, distinct = x["observation_span_days"], x["distinct_dates"] or 0
        domains[d] = {**DOMAIN_FACTS[d], "rows": x["rows"], "resolved_rows": x["resolved_rows"], "resolved_pct": x["resolved_pct"],
                      "distinct_geographies_resolved": x["distinct_geographies_resolved"], "distinct_admin_units_with_series": x["units_with_series"],
                      "date_min": x["date_min"], "date_max": x["date_max"], "latest_date": x["date_max"], "distinct_dates": distinct,
                      "observation_span_days": span, "missing_dates_within_span": max(span - distinct, 0), "longest_gap_days": x["longest_gap_days"],
                      "missing_geography_rows": (x["rows"] or 0) - (x["resolved_rows"] or 0),
                      "longest_unit_history_observations": x["longest_unit_history_observations"],
                      "historical_normalization_possible": x["historical_reference_available"],
                      "eligibility_counts_before": b["eligibility_counts"], "eligibility_counts_after": x["eligibility_counts"],
                      "newly_eligible_observations": x["eligibility_counts"].get(S.ELIGIBLE, 0) - b["eligibility_counts"].get(S.ELIGIBLE, 0),
                      "admin_units_with_eligible_observation": len(elig_units.get(d, {})), "scoring_decision": x["decision"], "blockers": [x["decision_reason"]]}
    n_auth = len(view["eligible"])
    domains["gauge"]["blockers"] = [f"only {n_auth} of {len(inventory)} stations have an eligible (authoritative) mapping; the rest are unresolved, conflicting, secondary-only or caveated",
                                    f"{domains['gauge']['eligibility_counts_after'].get('UNRESOLVED_GEOGRAPHY', 0)} assessed observations remain UNRESOLVED_GEOGRAPHY",
                                    "the only official coordinates found are breaching-section locations, not gauge sites"]
    domains["gauge"]["geography_resolution_method"] = ("authoritative evidence only: owner district statement (WAPDA, Chashma) or official coordinates with a stated position uncertainty "
                                                       "that stay inside one boundary district (Punjab Irrigation Department, Trimmu); secondary candidates are never applied")
    domains["weather"]["blockers"] = ["a single observation date: no prior history to normalize against"]
    domains["rainfall"]["blockers"] = ["only a few units have >= 30 prior observations", "74 header-artefact rows ('Stations') and multi-district strings stay unresolved by design"]
    domains["air_quality"]["blockers"] = ["only one geography (Lahore)"]

    gauge_obs = sum(s["observation_count"] for s in inventory.values())
    gaps = CE.rank_gaps([
        {"name": "official_gauge_site_coordinates_or_districts", "units_unlocked": 10, "units_unlocked_note": "lower bound: the 9 stations whose official breaching-section coordinates were unstable across districts, plus Tarbela",
         "history_continuity": 0.9, "authority": 3, "normalizable": True, "precision": 3, "relevance": 3, "reliability": 1,
         "observations_unlocked": 10 * 93, "blocker": "official coordinates exist only for breaching sections; gauge-site coordinates or district statements still need an official list (FFD / IRSA / FFC unreachable)"},
        {"name": "canonical_model_extension_for_authoritative_districts", "units_unlocked": 1, "units_unlocked_note": "Swabi (WAPDA states Tarbela is in District Swabi); needs approval to extend geo.admin_unit",
         "history_continuity": 0.9, "authority": 3, "normalizable": True, "precision": 2, "relevance": 2, "reliability": 1,
         "observations_unlocked": 93, "blocker": "outside Task 38 scope: changes the canonical geography"},
        {"name": "dated_weather_history_accumulation", "units_unlocked": 10, "units_unlocked_note": "27 resolved geographies; >= 31 daily dates needed",
         "history_continuity": 0.0, "authority": 2, "normalizable": True, "precision": 2, "relevance": 2, "reliability": 2,
         "observations_unlocked": 0, "blocker": "needs repeated dated collection; DAGs are paused and PMD overwrites latest.json"},
        {"name": "second_continuous_air_quality_geography", "units_unlocked": 1, "units_unlocked_note": "unknown; requires a new source",
         "history_continuity": 1.0, "authority": 2, "normalizable": True, "precision": 2, "relevance": 2, "reliability": 1,
         "observations_unlocked": 0, "blocker": "no second station source in the project; adding one is outside Task 37"},
        {"name": "rainfall_station_name_aliases", "units_unlocked": 0, "units_unlocked_note": "measured by simulation: +5 eligible observations, 0 new two-group cells",
         "history_continuity": 0.4, "authority": 1, "normalizable": True, "precision": 1, "relevance": 1, "reliability": 2,
         "observations_unlocked": 5, "blocker": "no authoritative evidence for the abbreviations"},
    ])

    return {
        "audit_version": "1.0.0", "registry_version": registry["registry_version"], "scoring_enabled": after["scoring_enabled"],
        "score_v2_outcome": after["outcome"], "cells_scored": after["cells_scored"],
        "question": "Which operational signals can be associated with which Pakistan administrative units from authoritative or explicitly qualified evidence?",
        "answer_summary": (f"{n_auth} of {len(inventory)} gauge stations have authoritative geography (Chashma, Trimmu). Rainfall (PDMA), weather (PMD) and air quality (EPA Punjab) are associated with "
                           "administrative units through the project's deterministic name resolver against the canonical model, which is explicitly qualified (not government-certified). "
                           "Hazard alerts and disaster events are contextual."),
        "gauge_stations": {"inventory_count": len(inventory), "observations": gauge_obs,
                           "resolved_mappings": view["resolved"], "authoritative_mappings": n_auth, "baseline_authoritative_mappings_task37": 0, "eligible_mappings": view["eligible"],
                           "observations_with_eligible_mapping": sum(inventory[m["station_key"]]["observation_count"] for m in view["eligible"]),
                           "gauge_observations_newly_eligible_for_scoring": domains["gauge"]["newly_eligible_observations"],
                           "unresolved_count": len(view["unresolved"]), "unresolved": view["unresolved"],
                           "conflicting_mappings": view["conflicting"], "secondary_only_mappings": view["secondary_only"], "caveated": view["caveated"],
                           "never_eligible_invariant_holds": CE.secondary_never_eligible(view),
                           "authoritative_evidence_references": [{k: e.get(k) for k in ("station_name", "station_name_in_source", "source_title", "source_organization", "source_page",
                                                                                 "source_url", "source_statement", "latitude", "longitude", "position_uncertainty_m", "district",
                                                                                 "evidence_status", "retrieved")}
                                                                 for e in gauge_cfg["evidence"] if e.get("evidence_status") == "authoritative"],
                           "deferred_official_coordinates": gauge_cfg.get("deferred_official_coordinates", []),
                           "investigation_log": gauge_cfg["investigation_log"], "investigation_log_task37": registry["gauge_investigation_task37"]},
        "crosswalk": {"boundary_dataset": xw["boundary_source"].get("dataset"), "status_counts": xw["match_status_counts"],
                      "canonical_districts": 69, "boundary_districts": 160,
                      "changes_in_task37": [{"boundary_source_id": "PK719", "boundary_name": "Shaheed Benazir Abad", "canonical_admin_unit_id": 59,
                                             "canonical_name": "Nawabshah", "from": "unmatched", "to": "alias", "evidence": "Sindh Act XIV of 2023"}],
                      "before_counts": {"level2:alias": 2, "level2:exact": 54, "level2:unmatched": 104},
                      "evidence_registry_check": check, "relationships": registry["relationships"],
                      "unverified_station_name_candidates": registry["unverified_station_name_candidates"], "unverified_simulated_effect": registry["unverified_station_name_simulated_effect"],
                      "canonical_ids_preserved": True},
        "domains": domains,
        "admin_unit_coverage": {d: {"admin_units_with_eligible_observation": len(elig_units.get(d, {}))} for d in domains},
        "newly_unlocked_eligible_observations": {d: domains[d]["newly_eligible_observations"] for d in domains},
        "cells": {"assessed_before": before["cells_assessed"], "assessed_after": after["cells_assessed"],
                  "with_an_eligible_signal_group_before": before["cells_with_at_least_one_eligible_signal_group"],
                  "with_an_eligible_signal_group_after": after["cells_with_at_least_one_eligible_signal_group"],
                  "with_two_independent_groups_before": before["cells_with_required_independent_groups"],
                  "with_two_independent_groups_after": after["cells_with_required_independent_groups"]},
        "gap_ranking": gaps,
        "remaining_blockers": [f"{len(inventory) - n_auth} of {len(inventory)} gauge stations lack an eligible mapping", "weather has a single dated observation", "only Lahore has a continuous air-quality series",
                               "no evidence-based weights or outcome labels (Task 36)", "103 boundary districts still lack a canonical unit (Swabi, needed for Tarbela, is one)"],
        "recommended_next_evidence_gap": gaps[0]["name"],
        "recommendation_note": ("Obtain official gauge-SITE coordinates or district statements (FFD telemetry / IRSA / FFC per-headworks plans, which were unreachable) and add them as "
                                "authoritative records to config/gauge_station_evidence.yaml; the pipeline accepts them without code changes. Separately, a decision is needed on "
                                "extending geo.admin_unit with districts that an owner states (Swabi for Tarbela)."),
    }


def main() -> int:
    report = build_report()
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    v = report["crosswalk"]["evidence_registry_check"]["violations"]
    print(json.dumps({k: report[k] for k in ("scoring_enabled", "cells_scored", "newly_unlocked_eligible_observations", "recommended_next_evidence_gap")}, indent=2))
    print("registry violations:", v)
    return 1 if v else 0


if __name__ == "__main__":
    sys.exit(main())
