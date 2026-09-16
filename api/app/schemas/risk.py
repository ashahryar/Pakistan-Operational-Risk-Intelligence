from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RiskRecord(BaseModel):
    """Mirrors operational_risk's real DDL columns exactly (see
    scripts/database/create_risk_tables.py). NOTE (Task 16A audit
    finding, docs/architecture/CODEBASE_AUDIT.md): the only script that
    ever wrote to this table (scripts/risk_engine/risk_engine.py) is
    confirmed BROKEN against this exact schema and has never
    successfully run -- so this endpoint, while real and not
    fabricated, is expected to return an empty list until that loader
    is fixed in a future task. It is not faked to look populated."""

    district: Optional[str]
    province: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    weather_risk: Optional[float]
    disaster_risk: Optional[float]
    overall_risk: Optional[float]
    risk_level: Optional[str]
    recommendation: Optional[str]
