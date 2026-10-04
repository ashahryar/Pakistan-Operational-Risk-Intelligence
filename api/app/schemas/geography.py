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


class AdminUnitSummary(BaseModel):
    """Canonical geo.admin_unit row plus whether a matched boundary geometry exists (Task 26)."""

    id: int
    name: str
    level: int
    province: Optional[str]
    has_geometry: bool
    boundary_source: Optional[str]


class BoundarySummary(BaseModel):
    """geo.boundary_admin_unit row (geometry is NOT included here -- use /api/v1/risk/map for GeoJSON)."""

    boundary_id: int
    source_feature_id: str
    name: str
    level: int
    province: Optional[str]
    source: str
    source_version: str
    geometry_valid: bool
    match_status: Optional[str]
    pori_admin_unit_id: Optional[int]
    pori_admin_unit_name: Optional[str]
