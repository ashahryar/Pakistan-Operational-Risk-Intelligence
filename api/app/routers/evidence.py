from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter

from api.app.services.evidence import gauge_evidence

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@router.get("/gauge-stations")
def get_gauge_station_evidence(evidence_state: Optional[Literal["ELIGIBLE", "CONFLICTING_GEOGRAPHY", "SECONDARY_ONLY", "CAVEATED", "UNRESOLVED"]] = None):
    """River-gauge stations with the state of their geography evidence. Read-only; an administrative unit is returned only for ELIGIBLE stations."""
    data = gauge_evidence()
    stations = [s for s in data["stations"] if evidence_state is None or s["evidence_state"] == evidence_state]
    return {"summary": data["summary"], "count": len(stations), "stations": stations}
