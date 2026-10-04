from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from api.app.schemas.ml import MlModelRun, MlPredictionsResponse
from api.app.services.geography import admin_unit_exists
from api.app.services.ml import list_models, list_predictions
from pipeline.ml.contracts import NOT_A_RISK_STATUS, STATUSES

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])

EMPTY_NOTE = "No ML prediction rows match these filters. No model result or prediction was invented."


@router.get("/predictions", response_model=MlPredictionsResponse)
def get_predictions(admin_unit_id: Optional[int] = Query(None, ge=1), date_: Optional[date] = Query(None, alias="date", description="the date predicted FOR"),
                    horizon: Optional[int] = Query(None, ge=1, le=30, description="horizon in days"),
                    status: Optional[Literal["PREDICTED", "BASELINE_ONLY", "INSUFFICIENT_DATA"]] = None,
                    include_insufficient: bool = Query(True, description="include explicit INSUFFICIENT_DATA rows"),
                    limit: int = Query(100, ge=1, le=1000)):
    """Current ML predictions (the ML prediction layer, separate from the deterministic risk engine). Each row is a forecast of an observed
    quantity with model, version, training and feature cutoffs and provenance ML_MODEL; where the requirements are not met the row says
    INSUFFICIENT_DATA with a null prediction and a reason. Read-only."""
    if admin_unit_id is not None and not admin_unit_exists(admin_unit_id):
        raise HTTPException(status_code=404, detail=f"admin_unit_id {admin_unit_id} not found in geo.admin_unit")
    rows = list_predictions(admin_unit_id, date_, horizon, status, include_insufficient, limit)
    counts = {s: sum(r["status"] == s for r in rows) for s in STATUSES}
    return {"count": len(rows), "status_counts": counts, "predictions": rows, "note": (NOT_A_RISK_STATUS if rows else EMPTY_NOTE)}


@router.get("/models", response_model=list[MlModelRun])
def get_models():
    """The current model runs: target, horizon, deployed predictor, validation against baselines, periods and metrics."""
    return list_models()
