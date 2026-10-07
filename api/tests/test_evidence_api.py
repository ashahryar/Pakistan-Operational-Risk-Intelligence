"""Task 40 -- /api/v1/evidence/gauge-stations: read-only, committed-evidence view; an administrative unit only for ELIGIBLE stations."""

from fastapi.testclient import TestClient

from api.app.main import app

import pytest

from api.app.services import evidence as ev

client = TestClient(app)


@pytest.fixture(autouse=True)
def snapshot_mode(monkeypatch):
    """Deterministic: the live observation merge is exercised separately with controlled rows."""
    def unreadable():
        raise RuntimeError("database not used in this test")
    monkeypatch.setattr(ev, "_live_observations", unreadable)


def test_summary_and_states_match_the_committed_evidence():
    r = client.get("/api/v1/evidence/gauge-stations")
    assert r.status_code == 200
    d = r.json()
    assert d["summary"]["stations"] == d["count"] == 41 and d["summary"]["observations"] == 3686
    assert d["summary"]["state_counts"] == {"CAVEATED": 1, "CONFLICTING_GEOGRAPHY": 2, "ELIGIBLE": 2, "SECONDARY_ONLY": 3, "UNRESOLVED": 33}
    assert d["summary"]["observations_with_eligible_mapping"] == 186


def test_only_eligible_stations_expose_an_administrative_unit():
    stations = client.get("/api/v1/evidence/gauge-stations").json()["stations"]
    eligible = {s["station_name"]: s["admin_unit_name"] for s in stations if s["evidence_state"] == "ELIGIBLE"}
    assert eligible == {"Chashma": "Mianwali", "Trimmu": "Jhang"}
    assert all(s["admin_unit_name"] is None and s["admin_unit_id"] is None and s["geography_derivation"] is None for s in stations if s["evidence_state"] != "ELIGIBLE")
    assert all(s["admin_unit_id"] for s in stations if s["evidence_state"] == "ELIGIBLE")
    by = {s["station_name"]: s for s in stations}
    assert by["Tarbela"]["evidence_state"] == "CONFLICTING_GEOGRAPHY" and by["Tarbela"]["candidate_districts"] == ["Haripur", "Swabi"] and not by["Tarbela"]["eligible_for_admin_risk"]
    assert by["Marala"]["evidence_state"] == "SECONDARY_ONLY" and by["Marala"]["admin_unit_name"] is None


def test_filter_and_invalid_filter_and_read_only():
    assert client.get("/api/v1/evidence/gauge-stations?evidence_state=UNRESOLVED").json()["count"] == 33
    assert client.get("/api/v1/evidence/gauge-stations?evidence_state=BOGUS").status_code == 422
    for verb in (client.post, client.put, client.delete, client.patch):
        assert verb("/api/v1/evidence/gauge-stations").status_code == 405


def test_live_observations_replace_the_frozen_snapshot_dates_and_counts(monkeypatch):
    from datetime import date
    base = client.get("/api/v1/evidence/gauge-stations").json()
    assert base["summary"]["observations_source"] == "evidence_snapshot" and base["summary"]["latest_observation"] == "2026-09-15"
    chashma = next(s for s in base["stations"] if s["station_name"] == "Chashma")
    live = {chashma["match_key"]: {"days": 200, "dmin": date(2026, 6, 15), "dmax": date(2026, 10, 7)}}
    monkeypatch.setattr(ev, "_live_observations", lambda: live)
    d = client.get("/api/v1/evidence/gauge-stations").json()
    by = {s["station_name"]: s for s in d["stations"]}
    assert by["Chashma"]["observations"] == 200 and by["Chashma"]["date_max"] == "2026-10-07"
    assert by["Aik"]["date_max"] == "2026-09-15"                       # a station with no live row keeps its snapshot values
    assert d["summary"]["observations_source"] == "database" and d["summary"]["latest_observation"] == "2026-10-07"
    assert d["summary"]["observations_with_eligible_mapping"] == 200 + by["Trimmu"]["observations"]
    assert client.get("/api/v1/evidence/gauge-stations").json()["summary"]["observations"] == d["summary"]["observations"]      # no hidden state between requests


def test_the_geography_states_are_untouched_by_live_data(monkeypatch):
    monkeypatch.setattr(ev, "_live_observations", lambda: {})
    d = client.get("/api/v1/evidence/gauge-stations").json()
    assert d["summary"]["state_counts"] == {"CAVEATED": 1, "CONFLICTING_GEOGRAPHY": 2, "ELIGIBLE": 2, "SECONDARY_ONLY": 3, "UNRESOLVED": 33}
