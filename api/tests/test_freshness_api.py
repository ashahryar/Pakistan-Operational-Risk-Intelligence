"""Task 41 -- /api/v1/freshness: read-only, one row per domain, computed per request."""

from fastapi.testclient import TestClient

from api.app.main import app
from api.app.services import freshness as fr

client = TestClient(app)


def test_endpoint_shape_and_read_only(monkeypatch):
    monkeypatch.setattr(fr, "freshness", lambda: {"generated_at": "x", "domains": [{"domain": "ndma", "latest_data_date": None}]})
    import api.app.routers.freshness as router
    monkeypatch.setattr(router, "freshness", fr.freshness)
    r = client.get("/api/v1/freshness")
    assert r.status_code == 200 and r.json()["domains"][0]["domain"] == "ndma"
    for verb in (client.post, client.put, client.delete, client.patch):
        assert verb("/api/v1/freshness").status_code == 405


def test_domains_cover_every_dashboard_domain():
    assert set(fr.DOMAINS) == {"ndma", "pdma_rainfall", "pdma_gauge", "pdma_daily", "pmd_weather"}
    assert fr.DOMAINS["pdma_gauge"]["date_kind"] == "observation_datetime" and fr.DOMAINS["pmd_weather"]["date_kind"] == "scraped_at"
