from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from api.app.schemas.risk import OperationalRisk
from api.app.services.geography import admin_unit_exists
from api.app.services.risk_serving import list_latest_risk, list_risk, risk_map_rows, to_feature_collection

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])

RiskStatus = Literal["NO_SIGNAL", "INSUFFICIENT_DATA", "LOW", "MODERATE", "HIGH", "CRITICAL"]


def _check_unit(admin_unit_id: Optional[int]) -> None:
    if admin_unit_id is not None and not admin_unit_exists(admin_unit_id):
        raise HTTPException(status_code=404, detail=f"admin_unit_id {admin_unit_id} not found in geo.admin_unit")


@router.get("/latest", response_model=list[OperationalRisk])
def get_latest_risk(province: Optional[str] = None, admin_unit_id: Optional[int] = Query(None, ge=1),
                    risk_status: Optional[RiskStatus] = None, limit: int = Query(500, ge=1, le=2000)):
    """Latest available risk row per canonical admin unit (the unit's own maximum date, not today's date)."""
    _check_unit(admin_unit_id)
    return list_latest_risk(province, admin_unit_id, risk_status, limit)


@router.get("/map")
def get_risk_map(level: Optional[int] = Query(None, ge=1, le=2, description="1=province, 2=district"),
                 province: Optional[str] = None, risk_status: Optional[RiskStatus] = None,
                 only_with_risk: bool = False, include_geometry: bool = True):
    """GeoJSON FeatureCollection: boundary geometry (null if the unit has no matched boundary) + latest risk properties."""
    return to_feature_collection(risk_map_rows(level, province, risk_status, only_with_risk, include_geometry))


@router.get("", response_model=list[OperationalRisk])
def get_risk(date_: Optional[date] = Query(None, alias="date"), province: Optional[str] = None,
             admin_unit_id: Optional[int] = Query(None, ge=1), risk_status: Optional[RiskStatus] = None,
             limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    """Risk rows from the Task 23 engine (risk_score is null in v1.0.0). Replaces the Task 16A legacy-table response."""
    _check_unit(admin_unit_id)
    return list_risk(date_, province, admin_unit_id, risk_status, limit, offset)
