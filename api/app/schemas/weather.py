from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WeatherObservation(BaseModel):
    """Mirrors pmd_daily_forecast's real columns exactly -- no field
    here is invented or renamed."""

    city: str
    district: Optional[str]
    province: Optional[str]
    temperature: Optional[float]
    humidity: Optional[float]
    forecast_day_1: Optional[str]
    forecast_day_2: Optional[str]
    forecast_day_3: Optional[str]
    category: Optional[str]
    scraped_at: Optional[datetime]
