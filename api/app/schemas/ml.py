from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class MlPrediction(BaseModel):
    model_run_id: str
    entity_type: str
    entity_id: str
    admin_unit_id: Optional[int]
    horizon_days: int
    prediction_date: str                 # the date the prediction is FOR
    feature_cutoff: str                  # last observation date the features could use
    target: str
    unit: Optional[str]
    prediction: Optional[float]          # null when status is INSUFFICIENT_DATA
    status: str                          # PREDICTED | BASELINE_ONLY | INSUFFICIENT_DATA
    reason: Optional[str]
    model_name: Optional[str]
    model_version: Optional[str]
    model_type: str                      # ml | baseline | none
    training_cutoff: Optional[str]
    provenance: dict[str, Any]           # provenance = ML_MODEL


class MlPredictionsResponse(BaseModel):
    count: int
    status_counts: dict[str, int]
    predictions: list[MlPrediction]
    note: str


class MlModelRun(BaseModel):
    model_run_id: str
    target: str
    domain: str
    unit: Optional[str]
    horizon_days: int
    model_name: str
    model_version: str
    model_type: str
    status: str
    validated_against_baseline: bool
    as_of: str
    feature_cutoff: str
    training_cutoff: Optional[str]
    train_start: Optional[str] = None
    train_end: Optional[str] = None
    validation_start: Optional[str] = None
    validation_end: Optional[str] = None
    test_start: Optional[str] = None
    test_end: Optional[str] = None
    n_train: Optional[int] = None
    n_validation: Optional[int] = None
    n_test: Optional[int] = None
    metrics: Optional[dict[str, Any]] = None
