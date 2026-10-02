"""Machine-readable explanations built ONLY from the signals that actually fed the aggregation."""

from __future__ import annotations

from typing import Any

from pipeline.risk.contracts import RiskSignal


def build_explanation(admin_unit_id: int, date: str, agg: dict[str, Any], signals: list[RiskSignal],
                      enabled_domains: list[str]) -> dict[str, Any]:
    drivers = []
    for s in sorted(signals, key=lambda s: (s.domain, s.signal_name, s.source_record_id)):
        if s.data_quality_status == "GEOGRAPHY_CAVEAT":
            reason = "excluded from status: admin unit carries a documented geography caveat"
        elif s.provisional_status:
            reason = f"source-published severity '{s.severity_label}' mapped to {s.provisional_status} by PROVISIONAL config map"
        elif s.normalized_value is not None:
            reason = "percentile rank against this unit's own strictly-prior history (PROVISIONAL cut points)"
        elif s.data_quality_status == "INSUFFICIENT_HISTORY":
            reason = "observed, but too little prior history to normalize"
        else:
            reason = "observed; no defensible baseline, so it does not contribute numerically"
        drivers.append({"domain": s.domain, "signal": s.signal_name, "value": s.raw_value, "normalized": s.normalized_value,
                        "contribution": s.contribution, "severity_label": s.severity_label,
                        "source_record_id": s.source_record_id, "reason": reason})
    return {"admin_unit_id": admin_unit_id, "date": date, "risk_status": agg["risk_status"], "risk_basis": agg["risk_basis"],
            "drivers": drivers, "missing_domains": [d for d in enabled_domains if d not in agg["_observed_domains"]],
            "data_quality": {"coverage_pct": agg["data_coverage_pct"], "risk_confidence": agg["risk_confidence"]}}
