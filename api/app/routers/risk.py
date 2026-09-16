from __future__ import annotations

from fastapi import APIRouter, Query

from api.app.schemas.risk import RiskRecord
from api.app.services.risk import list_risk_records

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.get("", response_model=list[RiskRecord])
def get_risk(limit: int = Query(200, ge=1, le=2000)):
    """
    See api/app/services/risk.py's docstring: this table is currently
    unpopulated (its loader is broken), so an empty list is the
    honest, expected response today -- not a bug in this endpoint.
    """
    return list_risk_records(limit=limit)
