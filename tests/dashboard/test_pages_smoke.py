"""Task 40 -- smoke test of EVERY Streamlit page against the real database and API (no stubs). Added because stubbed page tests passed while a real run crashed.
Skipped when PostgreSQL (localhost:5433) or the API (PORI_API_URL / localhost:8000) is not reachable. A page may show an error message, but never an exception."""

import os
import socket
from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

ROOT = Path(__file__).resolve().parents[2]
PAGES = ["Home.py"] + [f"pages/{p.name}" for p in sorted((ROOT / "dashboard" / "pages").glob("*.py"))]


def _open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def _api_up():
    import requests
    try:
        return requests.get(os.getenv("PORI_API_URL", "http://localhost:8000") + "/health", timeout=3).json().get("database") is True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not (_open("localhost", 5433) and _api_up()), reason="PostgreSQL and the API are not both reachable")


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_against_real_services_without_an_exception(page):
    at = AppTest.from_file(str(ROOT / "dashboard" / page), default_timeout=180).run()
    assert not at.exception, f"{page}: {[e.value for e in at.exception]}"


def test_risk_map_never_presents_a_null_score_as_zero_or_low():
    at = AppTest.from_file(str(ROOT / "dashboard" / "pages" / "6_Risk_Map.py"), default_timeout=180).run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Areas with a numeric score"] == "0" and int(metrics["Areas where the score is abstained"]) > 0
    text = " ".join(c.value for c in at.caption)
    assert "not a low risk" in text


@pytest.mark.parametrize("mode", ["Agent", "Analyze Risk", "Ask Reports"])
def test_operational_intelligence_modes_render(mode):
    at = AppTest.from_file(str(ROOT / "dashboard" / "pages" / "7_Operational_Intelligence.py"), default_timeout=120)
    at.session_state["oi_mode"] = mode
    at.run()
    assert not at.exception
    assert any(b.label.startswith(("Ask", "Ask the agent")) for b in at.button) or at.get("form_submit_button")


def test_home_shows_na_not_zero_for_missing_and_no_fake_health_or_score():
    at = AppTest.from_file(str(ROOT / "dashboard" / "Home.py"), default_timeout=180).run()
    assert not at.exception
    blob = " ".join([m.label for m in at.metric] + [c.value for c in at.caption] + [m.value for m in at.markdown])
    for forbidden in ("Platform Health", "Flood Risk Indicator", "Streaming Updates", "100/100", "Operational Risk Score"):
        assert forbidden not in blob
    labels = {m.label: m.value for m in at.metric}
    assert labels.get("Numeric scores") == "0" and "Score abstained" in labels
