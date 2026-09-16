from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AdminUnit(BaseModel):
    """Mirrors geo.admin_unit's real columns exactly (Task 10/11,
    ADR-0001) -- no field here is invented or renamed."""

    id: int
    level: int
    name: str
    parent_id: Optional[int]
    pcode: Optional[str]
    country: str
    latitude: Optional[float]
    longitude: Optional[float]
    source: str
