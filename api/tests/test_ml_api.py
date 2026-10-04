"""Task 33 -- GET /api/v1/ml/predictions and /api/v1/ml/models with a patched database (no network, no model). The API only serves stored rows."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.app.routers.ml as ml_router  # noqa: E402
import api.app.services.ml as ml_service  # noqa: E402
from api.app.main import app  # noqa: E402
from api.tests._readonly import assert_read_only  # noqa: E402

client = TestClient(app)


def row(uid, status="BASELINE_ONLY", horizon=1, prediction=126.0, pdate=date(2026, 9, 16)):
    insufficient = status == "INSUFFICIENT_DATA"
    return {"model_run_id": f"air_quality_index-h{horizon}-abc", "entity_type": "admin_unit", "entity_id": str(uid), "admin_unit_id": uid, "horizon_days": horizon,
            "prediction_date": pdate, "feature_cutoff": date(2026, 9, 15), "target": "air_quality_index", "unit": "AQI",
            "prediction": None if insufficient else prediction, "status": status, "reason": "no air_quality observations exist for this area" if insufficient else None,
            "model_name": None if insufficient else "persistence", "model_version": None if insufficient else "1.0.0+abc",
            "model_type": "none" if insufficient else "baseline", "training_cutoff": None if insufficient else date(2026, 7, 26),
            "provenance": {"provenance": "ML_MODEL", "validated_against_baseline": False}}


ROWS = [row(30), row(30, horizon=3, prediction=135.4), row(2, "INSUFFICIENT_DATA"), row(46, "INSUFFICIENT_DATA", horizon=3)]


class Db:
    def __init__(self, rows=ROWS):
        self.rows, self.sql = rows, []

    def __call__(self, sql, params=None):
        s = " ".join(sql.split())
        self.sql.append(s)
        if "FROM ml.model_runs" in s:
            return [{"model_run_id": "air_quality_index-h1-abc", "target": "air_quality_index", "domain": "air_quality", "unit": "AQI", "horizon_days": 1,
                     "model_name": "persistence", "model_version": "1.0.0+abc", "model_type": "baseline", "status": "BASELINE_ONLY", "validated_against_baseline": False,
                     "as_of": date(2026, 9, 15), "feature_cutoff": date(2026, 9, 15), "training_cutoff": date(2026, 7, 26), "train_start": date(2025, 10, 15),
                     "train_end": date(2026, 6, 6), "validation_start": date(2026, 6, 8), "validation_end": date(2026, 7, 26), "test_start": date(2026, 7, 28),
                     "test_end": date(2026, 9, 15), "n_train": 235, "n_validation": 49, "n_test": 50, "metrics": {"best_baseline": "persistence"}}]
        out = list(self.rows)
        if params["u"] is not None:
            out = [r for r in out if r["admin_unit_id"] == params["u"]]
        if params["d"] is not None:
            out = [r for r in out if r["prediction_date"] == params["d"]]
        if params["h"] is not None:
            out = [r for r in out if r["horizon_days"] == params["h"]]
        if params["s"] is not None:
            out = [r for r in out if r["status"] == params["s"]]
        if not params["inc"]:
            out = [r for r in out if r["status"] != "INSUFFICIENT_DATA"]
        return out[: params["limit"]]


@pytest.fixture
def db(monkeypatch):
    d = Db()
    monkeypatch.setattr(ml_service, "fetch_all", d)
    monkeypatch.setattr(ml_router, "admin_unit_exists", lambda i: i != 999)
    return d


def test_predictions_follow_the_contract(db):
    r = client.get("/api/v1/ml/predictions", params={"admin_unit_id": 30})
    assert r.status_code == 200
    b = r.json()
    assert b["count"] == 2 and b["status_counts"] == {"PREDICTED": 0, "BASELINE_ONLY": 2, "INSUFFICIENT_DATA": 0} and "not a current risk classification" in b["note"]
    p = b["predictions"][0]
    for k in ("admin_unit_id", "prediction_date", "horizon_days", "target", "prediction", "model_name", "model_version", "training_cutoff", "feature_cutoff", "status", "provenance"):
        assert k in p
    assert p["prediction_date"] == "2026-09-16" and p["feature_cutoff"] == "2026-09-15" and p["training_cutoff"] == "2026-07-26" and p["prediction"] == 126.0
    assert p["provenance"]["provenance"] == "ML_MODEL" and p["model_type"] == "baseline" and "risk_score" not in p and "risk_status" not in p


def test_insufficient_data_is_explicit_with_a_null_prediction_and_a_reason(db):
    b = client.get("/api/v1/ml/predictions", params={"admin_unit_id": 2}).json()
    p = b["predictions"][0]
    assert p["status"] == "INSUFFICIENT_DATA" and p["prediction"] is None and p["model_type"] == "none" and "no air_quality observations" in p["reason"]
    assert b["status_counts"]["INSUFFICIENT_DATA"] == 1


def test_filters_horizon_date_status_and_insufficient_toggle(db):
    assert client.get("/api/v1/ml/predictions", params={"horizon": 3}).json()["count"] == 2
    assert client.get("/api/v1/ml/predictions", params={"date": "2026-09-16"}).json()["count"] == 4
    assert client.get("/api/v1/ml/predictions", params={"date": "2026-09-17"}).json()["count"] == 0
    assert client.get("/api/v1/ml/predictions", params={"status": "INSUFFICIENT_DATA"}).json()["count"] == 2
    assert client.get("/api/v1/ml/predictions", params={"include_insufficient": "false"}).json()["count"] == 2
    assert client.get("/api/v1/ml/predictions", params={"limit": 1}).json()["count"] == 1


def test_no_matching_rows_is_an_explicit_empty_response_not_an_invention(db):
    b = client.get("/api/v1/ml/predictions", params={"admin_unit_id": 30, "horizon": 7}).json()
    assert b["count"] == 0 and b["predictions"] == [] and "No model result or prediction was invented" in b["note"]


@pytest.mark.parametrize("params", [{"admin_unit_id": 0}, {"horizon": 0}, {"horizon": 31}, {"horizon": "x"}, {"date": "nope"}, {"status": "MAYBE"}, {"limit": 0}, {"limit": 5000}])
def test_invalid_parameters_are_422(db, params):
    assert client.get("/api/v1/ml/predictions", params=params).status_code == 422


def test_unknown_unit_is_404(db):
    assert client.get("/api/v1/ml/predictions", params={"admin_unit_id": 999}).status_code == 404


def test_models_endpoint_lists_the_runs_with_periods_and_validation(db):
    b = client.get("/api/v1/ml/models").json()
    assert len(b) == 1 and b[0]["status"] == "BASELINE_ONLY" and b[0]["validated_against_baseline"] is False
    assert (b[0]["train_end"], b[0]["validation_end"], b[0]["test_end"], b[0]["n_test"]) == ("2026-06-06", "2026-07-26", "2026-09-15", 50)


def test_the_ml_api_is_read_only_and_only_selects(db):
    assert_read_only(app, client, ("/api/v1/ml",), {"/api/v1/ml/predictions", "/api/v1/ml/models"})
    for verb in ("post", "put", "patch", "delete"):
        for path in ("/api/v1/ml/predictions", "/api/v1/ml/models"):
            assert getattr(client, verb)(path).status_code == 405
    client.get("/api/v1/ml/predictions")
    assert all(s.startswith("SELECT") for s in db.sql)
