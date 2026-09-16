from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from api.app.schemas.weather import WeatherObservation
from api.app.services.weather import list_latest_weather

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])


@router.get("", response_model=list[WeatherObservation])
def get_weather(
    city: Optional[str] = Query(None, description="Filter to a single city"),
    limit: int = Query(200, ge=1, le=2000),
):
    return list_latest_weather(city=city, limit=limit)
