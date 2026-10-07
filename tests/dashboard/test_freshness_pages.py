"""Task 41 -- page-level regressions: freshness is shown on every data page, the Risk Map survives a stale helper module, no invented score or level is shown.
The AppTest cases run against the real database and API (skipped when they are not reachable), like test_pages_smoke."""

import re
from pathlib import Path

import pytest

from tests.dashboard.test_pages_smoke import ROOT, _api_up, _open

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

live = pytest.mark.skipif(not (_open("localhost", 5433) and _api_up()), reason="PostgreSQL and the API are not both reachable")
DASH = Path(ROOT) / "dashboard"

FRESH = re.compile(r"Latest available · \d{2} \w{3} \d{4}|Stale · latest successful snapshot \d{2} \w{3} \d{4}|Source unavailable — latest successful snapshot: \d{2} \w{3} \d{4}|No observations available|Freshness unavailable")


def _text(at):
    return " ".join([c.value for c in at.caption] + [w.value for w in at.warning] + [m.value for m in at.markdown])


@live
@pytest.mark.parametrize("page", ["pages/1_NDMA_Casualties.py", "pages/2_NDMA_Damage.py", "pages/3_PMD_Weather.py", "pages/4_PDMA_Rainfall.py",
                                  "pages/5_PDMA_Rivers.py", "pages/6_Risk_Map.py"])
def test_every_data_page_states_the_latest_available_date_in_its_header(page):
    at = AppTest.from_file(str(DASH / page), default_timeout=180).run()
    assert not at.exception
    assert FRESH.search(_text(at)), f"{page}: no freshness chip"


@live
def test_pmd_page_says_the_source_is_unavailable_instead_of_calling_old_data_current():
    at = AppTest.from_file(str(DASH / "pages" / "3_PMD_Weather.py"), default_timeout=180).run()
    text = _text(at)
    assert re.search(r"Source unavailable — latest successful snapshot: \d{2} \w{3} \d{4}", text) and "PMD sources answered HTTP 500" in text
    assert "LIVE" not in text


@live
def test_home_freshness_table_states_each_source_and_no_missing_value_is_zero():
    at = AppTest.from_file(str(DASH / "Home.py"), default_timeout=180).run()
    assert not at.exception
    table = next(d.value for d in at.dataframe if "Last successful ingestion" in d.value.columns)
    assert list(table.columns) == ["Source", "Date kind", "Latest available", "Last successful ingestion", "State"]
    assert not (table["Latest available"].astype(str) == "0").any()
    pmd = table[table["Source"].str.startswith("PMD")].iloc[0]
    assert "Source unavailable" in pmd["State"] and pmd["Latest available"] != "n/a"
    risk = table[table["Source"].str.startswith("Operational risk")].iloc[0]
    assert risk["Date kind"] == "risk date"
    labels = {m.label: m.value for m in at.metric}
    assert labels["Numeric scores"] == "0" and "Score abstained" in labels


@live
def test_risk_map_regression_a_stale_helper_without_areas_scored_is_a_message_not_a_keyerror(monkeypatch):
    """Task 39/40 crash: KeyError 'areas_scored' from a long-running process that kept an older helper module."""
    import dashboard.utils.risk_map_helpers as h
    real = h.summarize

    def old_summarize(*a, **k):
        s = real(*a, **k)
        s.pop("areas_scored", None)
        s.pop("areas_score_abstained", None)
        return s

    monkeypatch.setattr(h, "summarize", old_summarize)
    at = AppTest.from_file(str(DASH / "pages" / "6_Risk_Map.py"), default_timeout=180).run()
    assert not at.exception
    assert any("older code than this page" in e.value for e in at.error)


@live
def test_risk_map_survives_a_cache_hit_after_the_client_module_is_replaced():
    from tests.dashboard.test_api_cache import replaced_client_module
    AppTest.from_file(str(DASH / "pages" / "6_Risk_Map.py"), default_timeout=180).run()          # fills the cache
    with replaced_client_module():                                                              # what a long-running server does to a changed module
        at = AppTest.from_file(str(DASH / "pages" / "6_Risk_Map.py"), default_timeout=180).run()
        assert not at.exception, [e.value for e in at.exception]


# --- static guards: nothing invented comes back
def test_no_invented_score_or_weighting_in_the_disaster_views():
    for rel in ("sections/disaster.py", "charts/disaster_charts.py"):
        src = (DASH / rel).read_text(encoding="utf-8")
        assert "risk_score" not in src and "Operational Risk Score" not in src and "Risk Score" not in src, rel
        assert not re.search(r"\"deaths\"\]\s*\*\s*\d", src), f"{rel}: a weighting of deaths was reintroduced"


def test_rivers_page_never_reads_the_misaligned_level_columns():
    src = (DASH / "pages" / "5_PDMA_Rivers.py").read_text(encoding="utf-8")
    for col in ("current_level_ft", "danger_level_ft", "get_pdma_rivers"):
        assert col not in src, f"the rivers page must not read {col}"
    assert "no level, danger or flood-risk" in src


def test_no_page_claims_automatic_refresh_after_every_pipeline_run():
    for path in DASH.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "refreshes automatically after" not in src and "refreshes automatically every" not in src, path.name
