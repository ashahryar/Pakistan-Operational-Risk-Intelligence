"""Task 26 -- tests for the geographic serving endpoints.

Two layers: (1) router/service behaviour with the service functions monkeypatched (no database), and (2) live-database
checks against the real serving tables, skipped when the database or the serving layer is unavailable."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.app.db as api_db  # noqa: E402
import api.app.routers.geography as geo_router  # noqa: E402
import api.app.routers.risk as risk_router  # noqa: E402
from api.app.main import app  # noqa: E402
from api.app.services.risk_serving import to_feature_collection  # noqa: E402
from api.tests._readonly import assert_read_only, openapi_methods, write_methods_exposed  # noqa: E402

client = TestClient(app)


def valid_geojson_feature_collection(fc: dict) -> None:
    """Structural GeoJSON (RFC 7946) validation: FeatureCollection -> Feature(geometry|null, properties)."""
    assert fc["type"] == "FeatureCollection" and isinstance(fc["features"], list)
    for f in fc["features"]:
        assert f["type"] == "Feature" and isinstance(f["properties"], dict) and "geometry" in f
        g = f["geometry"]
        if g is None:
            continue
        assert g["type"] in {"Polygon", "MultiPolygon"}
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                assert len(ring) >= 4 and ring[0] == ring[-1]
                assert all(-180 <= p[0] <= 180 and -90 <= p[1] <= 90 for p in ring)


def risk_row(**over):
    row = {"admin_unit_id": 2, "admin_unit_name": "Punjab", "admin_level": 1, "province": "Punjab", "risk_date": date(2026, 9, 16),
           "risk_status": "LOW", "risk_basis": "THRESHOLD_BASED", "risk_score": None, "risk_confidence": "MEDIUM",
           "top_risk_domain": "rainfall", "data_coverage_pct": 33.33, "calculation_version": "risk-engine-1.0.0",
           "geometry": None}
    row.update(over)
    return row


# --------------------------------------------------------------------------- no database
def test_geography_new_endpoints_pass_filters_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(geo_router, "list_admin_unit_summaries", lambda level=None, province=None, limit=500: seen.update(a=(level, province, limit)) or [])
    monkeypatch.setattr(geo_router, "list_boundaries", lambda level=None, province=None, source=None, limit=500: seen.update(b=(level, province, source, limit)) or [])
    assert client.get("/api/v1/geography/admin-units?level=2&province=Punjab&limit=5").json() == []
    assert client.get("/api/v1/geography/boundaries?level=2&province=Sindh&source=x&limit=7").json() == []
    assert seen == {"a": (2, "Punjab", 5), "b": (2, "Sindh", "x", 7)}


def test_admin_unit_summary_shape(monkeypatch):
    row = {"id": 1, "name": "Lahore", "level": 2, "province": "Punjab", "has_geometry": True, "boundary_source": "COD-AB"}
    monkeypatch.setattr(geo_router, "list_admin_unit_summaries", lambda **k: [row])
    assert client.get("/api/v1/geography/admin-units").json() == [row]


def test_invalid_queries_are_rejected_with_422():
    assert client.get("/api/v1/risk?date=2026-13-45").status_code == 422
    assert client.get("/api/v1/risk?risk_status=EXTREME").status_code == 422
    assert client.get("/api/v1/risk?limit=0").status_code == 422
    assert client.get("/api/v1/risk?admin_unit_id=abc").status_code == 422
    assert client.get("/api/v1/risk/map?level=7").status_code == 422
    assert client.get("/api/v1/geography/boundaries?level=0").status_code == 422


def test_unknown_admin_unit_is_404(monkeypatch):
    monkeypatch.setattr(risk_router, "admin_unit_exists", lambda i: False)
    assert client.get("/api/v1/risk?admin_unit_id=424242").status_code == 404
    assert client.get("/api/v1/risk/latest?admin_unit_id=424242").status_code == 404


def test_empty_results_are_200_empty(monkeypatch):
    monkeypatch.setattr(risk_router, "list_risk", lambda *a, **k: [])
    monkeypatch.setattr(risk_router, "list_latest_risk", lambda *a, **k: [])
    monkeypatch.setattr(risk_router, "risk_map_rows", lambda *a, **k: [])
    assert client.get("/api/v1/risk?date=1999-01-01").json() == []
    assert client.get("/api/v1/risk/latest").json() == []
    assert client.get("/api/v1/risk/map").json() == {"type": "FeatureCollection", "features": []}


def test_database_error_is_a_503_not_a_silent_empty(monkeypatch):
    class Boom:
        def connect(self):
            raise ConnectionError("db down")
    monkeypatch.setattr(api_db, "engine", Boom())
    r = client.get("/api/v1/risk/latest")
    assert r.status_code == 503 and "Database query failed" in r.json()["detail"]
    assert client.get("/api/v1/risk/map").status_code == 503


def test_null_risk_score_and_null_geometry_are_preserved_in_geojson():
    fc = to_feature_collection([risk_row(), risk_row(admin_unit_id=3, risk_score=None, geometry={"type": "Polygon", "coordinates": [[[70, 30], [71, 30], [71, 31], [70, 31], [70, 30]]]})])
    valid_geojson_feature_collection(fc)
    assert fc["features"][0]["geometry"] is None and fc["features"][0]["properties"]["risk_score"] is None
    assert fc["features"][1]["properties"]["risk_date"] == "2026-09-16"
    assert set(fc["features"][0]["properties"]) == {"admin_unit_id", "admin_unit_name", "admin_level", "province", "risk_status", "risk_score",
                                                    "risk_confidence", "risk_basis", "risk_date", "top_risk_domain", "data_coverage_pct",
                                                    "calculation_version"}      # no internal metadata


def test_geojson_validator_rejects_a_bad_collection():
    with pytest.raises(AssertionError):
        valid_geojson_feature_collection({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon", "coordinates": [[[0, 0], [1, 1], [2, 2]]]}}]})


def test_api_exposes_no_write_methods_for_geography_or_risk():
    # OpenAPI + real HTTP (app.routes is empty of APIRoute objects in this FastAPI version -- see api/tests/_readonly.py)
    assert_read_only(app, client, ("/api/v1/geography", "/api/v1/risk"),
                     {"/api/v1/geography", "/api/v1/geography/admin-units", "/api/v1/geography/boundaries", "/api/v1/risk",
                      "/api/v1/risk/latest", "/api/v1/risk/map"})


def test_the_read_only_check_is_not_vacuous():
    """The checker must fail when a write endpoint exists (proves the test can fail), and see real routes."""
    from fastapi import FastAPI

    bad = FastAPI()

    @bad.post("/api/v1/risk/evil")
    def evil():
        return {}

    assert write_methods_exposed(bad, ("/api/v1/risk",)) == {"/api/v1/risk/evil": {"post"}}
    with pytest.raises(AssertionError):
        assert_read_only(bad, TestClient(bad), ("/api/v1/risk",), {"/api/v1/risk/evil"})
    assert sum(1 for p in openapi_methods(app, ("/api/v1/",))) >= 9          # the real app exposes many paths
    assert not [r for r in app.routes if type(r).__name__ == "APIRoute"]     # documents why app.routes cannot be used


def test_openapi_lists_the_new_paths():
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/api/v1/geography/admin-units", "/api/v1/geography/boundaries", "/api/v1/risk/latest", "/api/v1/risk/map", "/api/v1/risk"):
        assert p in paths and set(paths[p]) == {"get"}


# --------------------------------------------------------------------------- live database
def _live() -> bool:
    try:
        from sqlalchemy import text

        from config.database import engine
        with engine.connect() as conn:
            return conn.execute(text("SELECT to_regclass('geo.operational_risk_map') IS NOT NULL AND to_regclass('risk.operational_risk') IS NOT NULL")).scalar_one()
    except Exception:
        return False


live = pytest.mark.skipif(not _live(), reason="database / serving layer not available")


@live
def test_live_health_still_works():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": True}


@live
def test_live_admin_units_and_boundaries():
    units = client.get("/api/v1/geography/admin-units").json()
    assert {u["level"] for u in units} == {0, 1, 2} and any(u["has_geometry"] for u in units) and any(not u["has_geometry"] for u in units)
    assert all(not u["has_geometry"] for u in units if u["name"] in {"Mangla", "Kamra"})            # caveated, no boundary
    b = client.get("/api/v1/geography/boundaries?level=2&limit=2000").json()
    assert len(b) == 160 and sum(1 for x in b if x["match_status"] == "unmatched") == 104 and all("geometry" not in x for x in b)
    assert all(x["pori_admin_unit_id"] is None for x in b if x["match_status"] == "unmatched")
    assert len(client.get("/api/v1/geography/boundaries?level=1").json()) == 7
    assert client.get("/api/v1/geography/boundaries?source=nope").json() == []


@live
def test_live_latest_risk_is_one_row_per_unit_with_max_date():
    latest = client.get("/api/v1/risk/latest?limit=2000").json()
    assert len({r["admin_unit_id"] for r in latest}) == len(latest) > 0
    for r in latest[:10]:
        rows = client.get(f"/api/v1/risk?admin_unit_id={r['admin_unit_id']}&limit=2000").json()
        assert max(x["risk_date"] for x in rows) == r["risk_date"]
    assert all(r["risk_score"] is None for r in latest)


@live
def test_live_date_filter_and_pagination():
    day = client.get("/api/v1/risk?date=2026-09-16&limit=2000").json()
    assert day and all(r["risk_date"] == "2026-09-16" for r in day)
    assert client.get("/api/v1/risk?date=1999-01-01").json() == []
    first = client.get("/api/v1/risk?limit=3").json()
    assert len(first) == 3 and client.get("/api/v1/risk?limit=3&offset=3").json() != first
    assert all(r["risk_status"] == "HIGH" for r in client.get("/api/v1/risk?risk_status=HIGH&limit=2000").json())


@live
def test_live_risk_map_is_valid_geojson_and_preserves_risk_without_geometry():
    fc = client.get("/api/v1/risk/map").json()
    valid_geojson_feature_collection(fc)
    feats = fc["features"]
    assert any(f["geometry"] is not None for f in feats)
    no_geom = [f for f in feats if f["geometry"] is None]
    assert no_geom and all(f["properties"]["risk_status"] is not None for f in no_geom)      # risk preserved, geometry NULL
    assert all(f["properties"]["risk_score"] is None for f in feats)
    only = client.get("/api/v1/risk/map?only_with_risk=true&level=1&include_geometry=false").json()
    assert only["features"] and all(f["geometry"] is None and f["properties"]["admin_level"] == 1 for f in only["features"])
    assert client.get("/api/v1/risk/map?province=Nowhere").json()["features"] == []
