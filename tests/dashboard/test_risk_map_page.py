"""Task 27 -- page-level behaviour of dashboard/pages/6_Risk_Map.py via Streamlit's AppTest (no browser, no network).
The page is exercised with the API either unreachable or answering canned payloads; it must never show a traceback."""

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

import streamlit as st  # noqa: E402

from dashboard.api_client import ApiResult, RiskApiClient  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[2] / "dashboard" / "pages" / "6_Risk_Map.py")
SQUARE = {"type": "Polygon", "coordinates": [[[70, 30], [71, 30], [71, 31], [70, 31], [70, 30]]]}


def props(uid, name, status, level=2, province="Punjab"):
    return {"admin_unit_id": uid, "admin_unit_name": name, "admin_level": level, "province": province, "risk_status": status,
            "risk_score": None, "risk_confidence": "MEDIUM" if status else None, "risk_basis": "THRESHOLD_BASED" if status else None,
            "risk_date": "2026-09-16" if status else None, "top_risk_domain": "rainfall" if status else None,
            "data_coverage_pct": 33.33 if status else None, "calculation_version": "risk-engine-1.0.0" if status else None}


MAP = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": 1, "geometry": SQUARE, "properties": props(1, "Lahore", "HIGH")},
    {"type": "Feature", "id": 2, "geometry": SQUARE, "properties": props(2, "Multan", "CRITICAL")},
    {"type": "Feature", "id": 3, "geometry": SQUARE, "properties": props(3, "Boundary only", None)},
    {"type": "Feature", "id": 4, "geometry": None, "properties": props(4, "Mangla", "INSUFFICIENT_DATA")}]}


def risk_row(uid, name, status, date="2026-09-16"):
    return {"admin_unit_id": uid, "admin_unit_name": name, "admin_level": 2, "province": "Punjab", "risk_date": date,
            "risk_status": status, "risk_basis": "THRESHOLD_BASED", "risk_score": None, "risk_confidence": "MEDIUM",
            "signals": {"rainfall": 0.9, "weather": None, "gauge": None, "air_quality": None, "hazard_alert": None, "disaster_event": None},
            "active_signal_count": 1, "observed_signal_count": 1, "missing_signal_count": 5, "top_risk_domain": "rainfall",
            "top_risk_contribution": 0.9, "data_coverage_pct": 33.33, "source_count": 1, "source_record_count": 1,
            "calculation_version": "risk-engine-1.0.0", "threshold_status": "PROVISIONAL"}


ROWS = [risk_row(1, "Lahore", "HIGH"), risk_row(2, "Multan", "CRITICAL"), risk_row(4, "Mangla", "INSUFFICIENT_DATA"),
        risk_row(1, "Lahore", "LOW", "2026-09-01")]


@pytest.fixture(autouse=True)
def fresh_caches():
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def canned(monkeypatch):
    def fake_get(self, path, params=None):
        if path == "/api/v1/geography/admin-units":
            return ApiResult(True, data=[{"id": 2, "name": "Punjab", "level": 1, "province": "Punjab", "has_geometry": True, "boundary_source": "x"}])
        if path == "/api/v1/risk":
            rows = ROWS
            if params and params.get("date"):
                rows = [r for r in rows if r["risk_date"] == params["date"]]
            if params and params.get("admin_unit_id"):
                rows = [r for r in rows if r["admin_unit_id"] == params["admin_unit_id"]]
            return ApiResult(True, data=rows)
        if path == "/api/v1/risk/latest":
            return ApiResult(True, data=[r for r in ROWS if r["risk_date"] == "2026-09-16" and r["admin_unit_id"] == params["admin_unit_id"]])
        if path == "/api/v1/risk/map":
            return ApiResult(True, data=MAP)
        return ApiResult(False, error_kind="server_error", message="unexpected path")
    monkeypatch.setattr(RiskApiClient, "_get", fake_get)


def metrics(at):
    return {m.label: m.value for m in at.metric}


def test_page_degrades_gracefully_when_the_api_is_unreachable(monkeypatch):
    monkeypatch.setenv("PORI_API_URL", "http://127.0.0.1:9")            # nothing listens here
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception                                              # no Python traceback reaches the user
    assert any("Could not load data" in e.value for e in at.error)
    assert any("uvicorn" in c.value for c in at.caption)


def test_page_shows_503_message_without_a_traceback(monkeypatch):
    monkeypatch.setattr(RiskApiClient, "_get", lambda self, path, params=None: ApiResult(False, error_kind="unavailable",
                        message="The API reported that its database is unavailable (HTTP 503).", status_code=503))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception and any("database is unavailable" in e.value for e in at.error)


def test_page_renders_summary_map_detail_and_unmapped_section(monkeypatch):
    canned(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception and not at.error
    m = metrics(at)
    assert m["Areas returned"] == "4" and m["Areas with risk"] == "3" and m["Areas without geometry"] == "1"
    assert (m["HIGH"], m["CRITICAL"], m["INSUFFICIENT_DATA"]) == ("1", "1", "1")
    headers = [s.value for s in at.subheader]
    assert "Area detail" in headers and "Risk records without mapped boundary" in headers
    area_box = next(b for b in at.selectbox if b.label == "Select an area")
    assert "Boundary only (Punjab)" in area_box.options and "Mangla (Punjab) — no boundary" in area_box.options
    assert any("No risk record" in i.value for i in at.info)            # first option has a boundary but no risk row
    area_box.select("Lahore (Punjab)")
    at.run()
    assert not at.exception
    text_blocks = " ".join(md.value for md in at.markdown)
    assert "Risk score: Unavailable" in text_blocks and "risk-engine-1.0.0" in text_blocks
    unmapped = [df for df in at.dataframe if "admin_unit_name" in df.value.columns and list(df.value["admin_unit_name"]) == ["Mangla"]]
    assert unmapped, "the risk record without a boundary must be listed"


def test_filters_exist_and_a_specific_date_changes_the_scope(monkeypatch):
    canned(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    labels = [s.label for s in at.selectbox]
    assert labels[:4] == ["Administrative level", "Province", "Risk status", "Risk date"]
    date_box = next(s for s in at.selectbox if s.label == "Risk date")
    assert date_box.options[0] == "Latest available" and "2026-09-01" in date_box.options
    date_box.select("2026-09-01")
    at.run()
    assert not at.exception
    m = metrics(at)
    assert m["Areas with risk"] == "1" and m["HIGH"] == "0"             # Lahore was LOW on that date; others have no row
