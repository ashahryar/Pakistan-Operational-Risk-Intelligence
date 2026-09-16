"""
api/tests/test_api.py

Task 16A (Phase 1 / ADR-0001) -- tests for the FastAPI foundation.
No live database is used or required: every service-layer function is
monkeypatched to return synthetic rows shaped exactly like the real
table schemas, so these tests exercise real request routing,
validation (Pydantic response_model), and query-param handling without
needing a running Postgres instance -- matching how the rest of this
repo's tests avoid live DB dependencies (tests/parsers/,
tests/geo/, etc.).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.app.main import app  # noqa: E402
import api.app.routers.geography as geography_router  # noqa: E402
import api.app.routers.weather as weather_router  # noqa: E402
import api.app.routers.disasters as disasters_router  # noqa: E402
import api.app.routers.risk as risk_router  # noqa: E402

client = TestClient(app)


def test_health_endpoint_reports_degraded_when_db_unreachable(monkeypatch):
    import api.app.routers.health as health_router

    class FailingEngine:
        def connect(self):
            raise ConnectionError("simulated DB down")

    monkeypatch.setattr(health_router, "engine", FailingEngine())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] is False


def test_geography_endpoint_returns_real_shaped_rows(monkeypatch):
    fake_rows = [
        {
            "id": 1, "level": 1, "name": "Punjab", "parent_id": None,
            "pcode": "PK1", "country": "Pakistan", "latitude": 31.5, "longitude": 74.3,
            "source": "geo_locations",
        }
    ]
    monkeypatch.setattr(geography_router, "list_admin_units", lambda level=None, limit=500: fake_rows)

    response = client.get("/api/v1/geography")

    assert response.status_code == 200
    assert response.json() == fake_rows


def test_geography_endpoint_passes_through_level_query_param(monkeypatch):
    captured = {}

    def fake_list_admin_units(level=None, limit=500):
        captured["level"] = level
        captured["limit"] = limit
        return []

    monkeypatch.setattr(geography_router, "list_admin_units", fake_list_admin_units)

    client.get("/api/v1/geography?level=2&limit=10")

    assert captured == {"level": 2, "limit": 10}


def test_geography_endpoint_rejects_an_out_of_range_level():
    response = client.get("/api/v1/geography?level=99")
    assert response.status_code == 422  # FastAPI/Pydantic validation error


def test_weather_endpoint_returns_real_shaped_rows(monkeypatch):
    fake_rows = [
        {
            "city": "Lahore", "district": "Lahore", "province": "Punjab",
            "temperature": "34", "humidity": "45",
            "forecast_day_1": "Sunny", "forecast_day_2": "Sunny", "forecast_day_3": "Sunny",
            "category": "Hot", "scraped_at": "2026-09-16T10:00:00",
        }
    ]
    monkeypatch.setattr(weather_router, "list_latest_weather", lambda city=None, limit=200: fake_rows)

    response = client.get("/api/v1/weather")

    assert response.status_code == 200
    assert response.json()[0]["city"] == "Lahore"


def test_disasters_endpoint_returns_real_shaped_rows(monkeypatch):
    fake_rows = [{"report_date": "2026-09-01", "province": "Sindh", "deaths": 3, "injured": 7}]
    monkeypatch.setattr(disasters_router, "list_casualties", lambda province=None, limit=200: fake_rows)

    response = client.get("/api/v1/disasters")

    assert response.status_code == 200
    assert response.json()[0]["province"] == "Sindh"


def test_risk_endpoint_returns_empty_list_honestly(monkeypatch):
    """The real, current behavior: operational_risk has no working
    loader (see api/app/services/risk.py), so an empty list is the
    correct response -- this test locks in that this is a genuinely
    empty *result*, not a broken endpoint (200, not 500/503)."""
    monkeypatch.setattr(risk_router, "list_risk_records", lambda limit=200: [])

    response = client.get("/api/v1/risk")

    assert response.status_code == 200
    assert response.json() == []


def test_openapi_schema_is_generated_without_error():
    """A cheap but real smoke test: if any router/schema is malformed,
    FastAPI's OpenAPI generation raises -- this catches that class of
    bug without needing a live DB."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/health" in schema["paths"]
    assert "/api/v1/geography" in schema["paths"]
    assert "/api/v1/weather" in schema["paths"]
    assert "/api/v1/disasters" in schema["paths"]
    assert "/api/v1/risk" in schema["paths"]
