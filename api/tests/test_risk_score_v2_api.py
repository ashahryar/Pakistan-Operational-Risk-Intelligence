"""Task 36 -- the additive `score_v2` block on the risk serving rows: backward compatible, read-only, abstained, never a fabricated score."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

import api.app.routers.risk as risk_router
from api.app.main import app
from api.app.services.risk_serving import _shape
from api.tests.test_serving_api import risk_row

client = TestClient(app)


def full_row(**over):
    base = risk_row(rainfall_signal=0.9, weather_signal=None, gauge_signal=None, air_quality_signal=0.7, hazard_alert_signal=1.0, disaster_event_signal=3,
                    risk_date=date(2026, 9, 16), risk_confidence="MEDIUM", active_signal_count=2, observed_signal_count=3, missing_signal_count=3,
                    top_risk_contribution=0.9, source_count=2, source_record_count=4, threshold_status="PROVISIONAL")
    base.update(over)
    return base


def test_shaped_row_keeps_every_existing_field_and_adds_an_abstained_score_block():
    r = _shape(full_row())
    assert r["risk_score"] is None and r["risk_status"] == "LOW" and r["calculation_version"] == "risk-engine-1.0.0" and r["signals"]["rainfall"] == 0.9
    s = r["score_v2"]
    assert s["score_status"] == "ABSTAINED" and s["abstention_reason"] == "NO_EVIDENCE_BASED_WEIGHTS" and s["score_version"] == "operational-score-v2-foundation-1.0.0"
    assert s["contributing_signals"] == [] and {e["domain"] for e in s["excluded_signals"]} == {"hazard_alert", "disaster_event"}


def test_endpoint_serves_the_block_and_stays_backward_compatible(monkeypatch):
    monkeypatch.setattr(risk_router, "admin_unit_exists", lambda i: True)
    import api.app.services.risk_serving as svc
    monkeypatch.setattr(svc, "fetch_all", lambda q, p=None: [full_row()])
    r = client.get("/api/v1/risk/latest?admin_unit_id=2")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["risk_score"] is None and row["score_v2"]["score_status"] == "ABSTAINED" and row["score_v2"]["abstention_text"]
    assert {"admin_unit_id", "risk_date", "risk_status", "risk_basis", "risk_confidence", "signals", "calculation_version"} <= set(row)
    for verb in ("post", "put", "patch", "delete"):
        assert getattr(client, verb)("/api/v1/risk/latest").status_code == 405


def test_a_stored_score_would_be_passed_through_not_recomputed():
    assert _shape(full_row(risk_score=41.5))["score_v2"]["score_status"] == "SCORED"
