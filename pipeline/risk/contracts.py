"""Typed contracts shared by the risk engine modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

RISK_STATES = ("NO_SIGNAL", "INSUFFICIENT_DATA", "LOW", "MODERATE", "HIGH", "CRITICAL")
STATUS_RANK = {s: i for i, s in enumerate(RISK_STATES)}
RISK_BASES = ("INSUFFICIENT_DATA", "OBSERVED_SIGNAL_ONLY", "THRESHOLD_BASED", "MULTI_SIGNAL", "ALERT_DRIVEN")
DOMAINS = ("rainfall", "weather", "gauge", "air_quality", "hazard_alert", "disaster_event")


@dataclass(frozen=True)
class RiskSignal:
    admin_unit_id: int
    date: str
    domain: str
    signal_name: str
    raw_value: Optional[float]
    normalized_value: Optional[float]
    direction: str                      # 'higher_is_more_risk' | 'presence' | 'count'
    contribution: Optional[float]       # == normalized_value (unweighted: no evidence-based weights)
    source: str
    source_record_id: str
    observation_time_basis: str
    data_quality_status: str            # OBSERVED | OBSERVED_NO_BASELINE | INSUFFICIENT_HISTORY | GEOGRAPHY_CAVEAT
    severity_label: Optional[str] = None
    provisional_status: Optional[str] = None
    history_count: Optional[int] = None   # prior observations behind normalized_value
