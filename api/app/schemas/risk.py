from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RiskRecord(BaseModel):
    """Mirrors the legacy operational_risk table's DDL columns (Task 16A). That table is unpopulated and its only writer is
    broken (docs/architecture/CODEBASE_AUDIT.md); since Task 26 no endpoint serves it. Kept for reference only."""

    district: Optional[str]
    province: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    weather_risk: Optional[float]
    disaster_risk: Optional[float]
    overall_risk: Optional[float]
    risk_level: Optional[str]
    recommendation: Optional[str]


class RiskSignals(BaseModel):
    rainfall: Optional[float]
    weather: Optional[float]
    gauge: Optional[float]
    air_quality: Optional[float]
    hazard_alert: Optional[float]
    disaster_event: Optional[float]


class OperationalRisk(BaseModel):
    """risk.operational_risk serving row (Task 26). risk_score is NULL in engine v1.0.0 and stays null."""

    admin_unit_id: int
    admin_unit_name: Optional[str]
    admin_level: Optional[int]
    province: Optional[str]
    risk_date: str
    risk_status: str
    risk_basis: Optional[str]
    risk_score: Optional[float]
    risk_confidence: Optional[str]
    signals: RiskSignals
    active_signal_count: Optional[int]
    observed_signal_count: Optional[int]
    missing_signal_count: Optional[int]
    top_risk_domain: Optional[str]
    top_risk_contribution: Optional[float]
    data_coverage_pct: Optional[float]
    source_count: Optional[int]
    source_record_count: Optional[int]
    calculation_version: str
    threshold_status: Optional[str]
