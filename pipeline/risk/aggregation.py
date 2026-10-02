"""Cell-level aggregation: signals -> status / basis / confidence. No score is produced unless
config score.enabled (no evidence-based weights exist, so it is off and the score stays null)."""

from __future__ import annotations

from typing import Any, Optional

from pipeline.risk.contracts import STATUS_RANK, RiskSignal


def status_from_normalized(value: Optional[float], cutpoints: dict[str, float]) -> Optional[str]:
    if value is None:
        return None
    if value >= cutpoints["CRITICAL"]:
        return "CRITICAL"
    if value >= cutpoints["HIGH"]:
        return "HIGH"
    if value >= cutpoints["MODERATE"]:
        return "MODERATE"
    return "LOW"


def aggregate_cell(signals: list[RiskSignal], cfg: dict[str, Any], enabled_domains: list[str]) -> dict[str, Any]:
    contributing = [s for s in signals if s.data_quality_status != "GEOGRAPHY_CAVEAT"]
    observed_domains = sorted({s.domain for s in signals})
    coverage_pct = round(100 * len(observed_domains) / len(enabled_domains), 2) if enabled_domains else 0.0
    cut = cfg["provisional_status_cutpoints"]

    candidates = []                                            # (status, signal)
    min_status_hist = cfg["normalization"].get("min_history_for_status", 0)
    for s in contributing:
        numeric_ok = s.normalized_value is not None and (s.history_count or 0) >= min_status_hist
        st = s.provisional_status or (status_from_normalized(s.normalized_value, cut) if numeric_ok else None)
        if st:
            candidates.append((st, s))
    numeric_domains = {s.domain for _, s in candidates if s.normalized_value is not None}

    if not signals:
        status, basis, driver = "NO_SIGNAL", "INSUFFICIENT_DATA", None
    elif not candidates:
        status, basis, driver = "INSUFFICIENT_DATA", "OBSERVED_SIGNAL_ONLY", None
    else:
        status, driver = max(candidates, key=lambda c: (STATUS_RANK[c[0]], c[1].domain, c[1].signal_name))
        if driver.provisional_status:
            basis = "ALERT_DRIVEN"
        elif len(numeric_domains) >= 2:
            basis = "MULTI_SIGNAL"
        else:
            basis = "THRESHOLD_BASED"

    normalized_domains = len(numeric_domains)
    hi, med = cfg["confidence"]["high"], cfg["confidence"]["medium"]
    if status in ("NO_SIGNAL", "INSUFFICIENT_DATA"):
        confidence = "INSUFFICIENT"
    elif normalized_domains >= hi["min_normalized_domains"] and coverage_pct >= hi["min_coverage_pct"]:
        confidence = "HIGH"
    elif (normalized_domains >= med["min_normalized_domains"] or driver is not None) and coverage_pct >= med["min_coverage_pct"]:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    with_contrib = [s for s in contributing if s.contribution is not None]
    # An INSUFFICIENT/NO_SIGNAL cell must not advertise a "top risk driver": its normalized values stay
    # visible per domain and in the explanation, but nothing is promoted to a headline driver.
    top = max(with_contrib, key=lambda s: (s.contribution, s.domain)) if with_contrib and driver is not None else None
    return {
        "risk_status": status, "risk_basis": basis, "risk_score": None, "risk_confidence": confidence,
        "observed_signal_count": len(observed_domains), "active_signal_count": len(with_contrib),
        "missing_signal_count": len(enabled_domains) - len(observed_domains), "data_coverage_pct": coverage_pct,
        "top_risk_domain": top.domain if top else None, "top_risk_contribution": top.contribution if top else None,
        "_driver": driver, "_observed_domains": observed_domains,
    }
