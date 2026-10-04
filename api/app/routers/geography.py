from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from api.app.schemas.geography import AdminUnit, AdminUnitSummary, BoundarySummary
from api.app.services.geography import list_admin_unit_summaries, list_admin_units, list_boundaries

router = APIRouter(prefix="/api/v1/geography", tags=["geography"])


@router.get("", response_model=list[AdminUnit])
def get_geography(
    level: Optional[int] = Query(None, ge=0, le=6, description="Admin level: 0=country, 1=province, 2=district"),
    limit: int = Query(500, ge=1, le=2000),
):
    return list_admin_units(level=level, limit=limit)


@router.get("/admin-units", response_model=list[AdminUnitSummary])
def get_admin_units(level: Optional[int] = Query(None, ge=0, le=2), province: Optional[str] = None,
                    limit: int = Query(500, ge=1, le=2000)):
    """Canonical PORI admin units with geometry availability."""
    return list_admin_unit_summaries(level=level, province=province, limit=limit)


@router.get("/boundaries", response_model=list[BoundarySummary])
def get_boundaries(level: Optional[int] = Query(None, ge=1, le=2), province: Optional[str] = None,
                   source: Optional[str] = None, limit: int = Query(500, ge=1, le=2000)):
    """External boundary units (e.g. COD-AB) with their crosswalk status; unmatched units are listed, not hidden."""
    return list_boundaries(level=level, province=province, source=source, limit=limit)
