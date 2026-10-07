"""Task 40 -- /api/v1/evidence/gauge-stations: read-only, committed-evidence view; an administrative unit only for ELIGIBLE stations."""

from fastapi.testclient import TestClient

from api.app.main import app

client = TestClient(app)


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
