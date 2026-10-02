"""Operational risk engine (Task 23): Gold signals -> normalization -> aggregation -> status +
explanation. Deterministic (no wall clock, no randomness), leakage-safe (a cell for date T only
ever sees observations dated <= T, and baselines only strictly before T), and honest about
missing data (missing != 0, unresolved geography is never mapped, no fabricated score).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from pipeline.risk.aggregation import aggregate_cell
from pipeline.risk.config import enabled_geographic_domains
from pipeline.risk.contracts import RiskSignal
from pipeline.risk.coverage import coverage_matrix
from pipeline.risk.explanations import build_explanation
from pipeline.risk.normalization import binary_signal, count_in_window, history_before, percentile_rank_strict
from pipeline.risk.signals import extract_signals


def ml_fields(unit: int, date: str, predictions: list[dict], station_unit: dict[str, int],
              qualifying: set[str], caveated_units: set[int]) -> dict[str, Any]:
    """Task 22 ML is a reference-only signal, never part of status. Eligible only if the station
    qualified, its geography resolved (and is not caveated), and the prediction was made at or
    before the cell date (no target/future leakage). Persistence remains the reference model."""
    base = {"ml_forecast_available": False, "ml_forecast_value": None, "ml_reference_model": "persistence",
            "ml_forecast_confidence": None, "ml_unavailable_reason": "no_eligible_prediction"}
    for p in predictions:
        station = p.get("station")
        if station_unit.get(station) != unit:
            continue
        if station not in qualifying:
            base["ml_unavailable_reason"] = "station_not_a_qualifying_model_station"
        elif unit in caveated_units:
            base["ml_unavailable_reason"] = "geography_caveat_excludes_unit"
        elif p.get("based_on_date") != date:
            base["ml_unavailable_reason"] = "prediction_not_made_on_cell_date"
        else:
            return {**base, "ml_forecast_available": True, "ml_unavailable_reason": None,
                    "ml_forecast_value": p.get("predicted_discharge_avg_linear_regression"),
                    "ml_model": "linear_regression",
                    "ml_note": "Task 22 models did not beat persistence (negative skill); informational only"}
    return base


def run_engine(gold: dict[str, list[dict]], cfg: dict[str, Any], unit_info: Optional[dict[int, dict]] = None,
               caveated_units: Optional[set[int]] = None, ml_predictions: Optional[list[dict]] = None,
               ml_qualifying: Optional[set[str]] = None) -> dict[str, Any]:
    unit_info = unit_info or {}
    caveated = caveated_units or set()
    domains = enabled_geographic_domains(cfg)
    sig = extract_signals(gold, cfg)
    min_hist = cfg["normalization"]["min_history_observations"]
    cut_map = {k.lower(): v for k, v in (cfg.get("provisional_alert_severity_map") or {}).items()}
    window = int(cfg.get("disaster_event", {}).get("trailing_window_days", 30))

    series: dict[tuple, dict[str, float]] = defaultdict(dict)
    for domain, obs in sig["numeric"].items():
        for (unit, date), o in obs.items():
            series[(unit, domain)][date] = o["raw_value"]

    grid: dict[int, set[str]] = defaultdict(set)
    for obs in sig["numeric"].values():
        for (unit, date) in obs:
            grid[unit].add(date)
    for a in sig["alerts"]:
        grid[a["unit"]].add(a["start"])
        if a["end"] != a["start"]:
            grid[a["unit"]].add(a["end"])
    for unit, dates in sig["events"].items():
        grid[unit].update(dates)

    rows, explanations = [], []
    all_dates = set()
    station_unit = {r["station_name"]: r["admin_unit_id"] for r in gold.get("gauge", [])
                    if r.get("resolution_status") == "resolved" and r.get("admin_unit_id")}
    for unit in sorted(grid):
        for date in sorted(grid[unit]):
            signals: list[RiskSignal] = []
            caveat = unit in caveated
            for domain, obs in sig["numeric"].items():
                o = obs.get((unit, date))
                if o is None:
                    continue
                hist = history_before(series[(unit, domain)], date)
                norm = percentile_rank_strict(o["raw_value"], hist, min_hist[domain])
                quality = "GEOGRAPHY_CAVEAT" if caveat else ("OBSERVED" if norm is not None else "INSUFFICIENT_HISTORY")
                contribution = None if caveat else norm
                signals.append(RiskSignal(unit, date, domain, o["signal_name"], o["raw_value"], norm, "higher_is_more_risk",
                                          contribution, o["source"], ";".join(o["source_record_ids"]), o["basis"], quality,
                                          None, None, len(hist)))
            for a in sig["alerts"]:
                if a["unit"] == unit and a["start"] <= date <= a["end"]:
                    label = a["severity"]
                    mapped = cut_map.get(str(label).lower()) if label else None
                    signals.append(RiskSignal(unit, date, "hazard_alert", f"active_alert:{a['hazard_type']}", binary_signal(True), None,
                                              "presence", None, a["source"], a["alert_id"], "source_observed",
                                              "GEOGRAPHY_CAVEAT" if caveat else "OBSERVED", label, None if caveat else mapped))
            if cfg.get("disaster_event", {}).get("trailing_window_days") and unit in sig["events"]:
                n = count_in_window(sig["events"][unit], date, window)
                if n > 0:
                    # Only events inside the window ending at T are referenced -- never a later event's id.
                    in_window = [eid for eid, ed in zip(sig["event_ids"][unit], sig["events"][unit])
                                 if count_in_window([ed], date, window)]
                    signals.append(RiskSignal(unit, date, "disaster_event", f"event_records_trailing_{window}d", float(n), None, "count",
                                              None, "ndma", ";".join(sorted(in_window)), "source_observed",
                                              "GEOGRAPHY_CAVEAT" if caveat else "OBSERVED_NO_BASELINE"))
            agg = aggregate_cell(signals, cfg, domains)
            info = unit_info.get(unit, {})
            by_domain = {d: [s for s in signals if s.domain == d] for d in domains}
            usable = {d: [s for s in ss if s.data_quality_status != "GEOGRAPHY_CAVEAT"] for d, ss in by_domain.items()}
            state = {}
            for d in domains:
                ss = by_domain[d]
                state[d] = "MISSING" if not ss else ss[0].data_quality_status
            norm_of = lambda d: max((s.normalized_value for s in usable.get(d, []) if s.normalized_value is not None), default=None)  # noqa: E731
            weather_norms = [v for v in (norm_of("rainfall"), norm_of("weather")) if v is not None]
            alert_labels = sorted({str(s.severity_label) for s in usable.get("hazard_alert", []) if s.severity_label})
            row = {
                "dataset": "gold_operational_risk", "admin_unit_id": unit, "admin_unit_name": info.get("name"),
                "admin_level": info.get("level"), "province": info.get("province"), "date": date,
                "risk_status": agg["risk_status"], "risk_basis": agg["risk_basis"], "risk_score": None,
                "risk_confidence": agg["risk_confidence"],
                "weather_signal": norm_of("weather"), "rainfall_signal": norm_of("rainfall"), "gauge_signal": norm_of("gauge"),
                "air_quality_signal": norm_of("air_quality"),
                "hazard_alert_signal": 1.0 if usable.get("hazard_alert") else None,
                "disaster_event_signal": usable["disaster_event"][0].raw_value if usable.get("disaster_event") else None,
                "signal_states": state,
                "active_signal_count": agg["active_signal_count"], "observed_signal_count": agg["observed_signal_count"],
                "missing_signal_count": agg["missing_signal_count"],
                "top_risk_domain": agg["top_risk_domain"], "top_risk_contribution": agg["top_risk_contribution"],
                "data_coverage_pct": agg["data_coverage_pct"],
                "source_count": len({s.source for s in signals}),
                "source_record_count": sum(len(s.source_record_id.split(";")) for s in signals),
                "business_signals": {
                    "WEATHER_DISRUPTION_SIGNAL": max(weather_norms) if weather_norms else None,
                    "FLOOD_HYDROLOGY_SIGNAL": norm_of("gauge"), "AIR_QUALITY_SIGNAL": norm_of("air_quality"),
                    "ACTIVE_HAZARD_SIGNAL": {"present": bool(usable.get("hazard_alert")), "source_severity_labels": alert_labels},
                    "RECENT_DISASTER_SIGNAL": {"records_in_window": row_count(usable)},
                    "DATA_CONFIDENCE": agg["risk_confidence"]},
                **ml_fields(unit, date, ml_predictions or [], station_unit, ml_qualifying or set(), caveated),
                "calculation_version": cfg["calculation_version"], "engine_version": cfg["engine_version"],
                "threshold_status": cfg.get("threshold_status", "PROVISIONAL"),
            }
            rows.append(row)
            all_dates.add(date)
            explanations.append(build_explanation(unit, date, agg, signals, domains))

    return {"rows": rows, "explanations": explanations, "unresolved": sig["unresolved"],
            "coverage": coverage_matrix(gold),
            "reservoir_context": [{k: r.get(k) for k in ("reservoir_name", "observed_at", "water_level", "live_storage",
                                                         "combined_live_storage", "observation_time_basis")}
                                  | {"geography": "not_attributable_to_an_admin_unit"} for r in gold.get("reservoir", [])],
            "calculation_version": cfg["calculation_version"]}


def row_count(by_domain: dict[str, list[RiskSignal]]) -> Optional[int]:
    ss = by_domain.get("disaster_event") or []
    return int(ss[0].raw_value) if ss else None
