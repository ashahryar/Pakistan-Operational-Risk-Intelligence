from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from api.app.schemas.geography import AdminUnit
from api.app.services.geography import list_admin_units

router = APIRouter(prefix="/api/v1/geography", tags=["geography"])


@router.get("", response_model=list[AdminUnit])
def get_geography(
    level: Optional[int] = Query(None, ge=0, le=6, description="Admin level: 0=country, 1=province, 2=district"),
    limit: int = Query(500, ge=1, le=2000),
):
    return list_admin_units(level=level, limit=limit)
