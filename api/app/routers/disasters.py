from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from api.app.schemas.disasters import CasualtyReport
from api.app.services.disasters import list_casualties

router = APIRouter(prefix="/api/v1/disasters", tags=["disasters"])


@router.get("", response_model=list[CasualtyReport])
def get_disasters(
    province: Optional[str] = Query(None, description="Filter to a single province"),
    limit: int = Query(200, ge=1, le=2000),
):
    return list_casualties(province=province, limit=limit)
