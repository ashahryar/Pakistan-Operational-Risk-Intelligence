from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class CasualtyReport(BaseModel):
    """Mirrors ndma_casualties's real columns exactly -- no field here
    is invented or renamed."""

    report_date: Optional[date]
    province: str
    deaths: Optional[int]
    injured: Optional[int]
