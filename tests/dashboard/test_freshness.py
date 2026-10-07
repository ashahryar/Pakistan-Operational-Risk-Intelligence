"""Task 41 -- freshness: the API reads the latest date from the data, the dashboard helper words it honestly (no hard-coded dates; the clock is injected)."""

from datetime import date, datetime

import pytest

pytest.importorskip("streamlit")

from api.app.services import freshness as api_fresh  # noqa: E402
from dashboard.utils.freshness import STALE_AFTER_DAYS, describe  # noqa: E402

TODAY = date(2026, 6, 10)


def row(domain="ndma", latest="2026-06-09", **kw):
    base = {"domain": domain, "label": domain, "date_kind": "report_date", "latest_data_date": latest, "rows": 5, "last_ingestion_at": "2026-06-09T10:00:00",
            "ingestion": "scheduled", "last_run_state": "success", "source_state": "available", "note": None}
    return {**base, **kw}


def test_current_data():
    d = describe(row(), TODAY)
    assert d["state"] == "current" and d["latest"] == "2026-06-09" and d["age_days"] == 1
    assert ("Latest available", "2026-06-09") in d["fields"] and ("Last successful ingestion", "2026-06-09") in d["fields"] and ("Source status", "Available") in d["fields"]


def test_stale_data_uses_the_domain_threshold():
    limit = STALE_AFTER_DAYS["pdma_gauge"]
    at_limit = describe(row("pdma_gauge", "2026-06-08"), TODAY)
    over = describe(row("pdma_gauge", "2026-06-07"), TODAY)
    assert limit == 2 and at_limit["state"] == "current" and over["state"] == "stale" and "3 days old" in over["headline"]


def test_unavailable_source_is_not_presented_as_current_data():
    d = describe(row("pmd_weather", "2026-06-09", source_state="unavailable", ingestion="disabled", date_kind="scraped_at"), TODAY)
    assert d["state"] == "source_unavailable" and "Source currently unavailable" in d["headline"] and "no newer successful ingestion" in d["headline"]
    assert "Latest available: 2026-06-09" in d["headline"] and d["source_status"] == "unavailable"
    assert "live" not in d["headline"].lower() and "current" not in d["state"]


def test_no_data_and_missing_domain_are_na_not_zero_or_a_made_up_date():
    nd = describe(row(latest=None, last_ingestion_at=None), TODAY)
    assert nd["state"] == "no_data" and nd["latest"] is None and nd["age_days"] is None and nd["fields"][0] == ("Latest available", "n/a") and "Last successful ingestion" not in dict(nd["fields"])
    unk = describe(None, TODAY)
    assert unk["state"] == "unknown" and unk["latest"] is None and unk["fields"] == []


def test_only_supported_fields_are_shown():
    d = describe(row(last_ingestion_at=None, source_state="unknown"), TODAY)
    assert [k for k, _ in d["fields"]] == ["Latest available"]


def test_the_date_kind_is_named_never_substituted():
    assert "(report date)" in describe(row(), TODAY)["headline"]
    assert "(observation time)" in describe(row("pdma_gauge", "2026-06-09", date_kind="observation_datetime"), TODAY)["headline"]
    assert "(scrape time)" in describe(row("pmd_weather", "2026-06-09", date_kind="scraped_at"), TODAY)["headline"]


# --- ingestion -> API -> dashboard, with controlled fixtures (no real clock, no real database)
class FakeDb:
    """A tiny stand-in for api.app.db.fetch_all over one mutable table set."""

    def __init__(self):
        self.max = {"ndma_casualties": date(2026, 6, 1), "pdma_rainfall_readings": date(2026, 5, 1), "pdma_gauge_readings": datetime(2026, 6, 8, 12),
                    "pdma_daily_reports": None, "pmd_daily_forecast": datetime(2026, 2, 12)}
        self.paused = {"ndma_pipeline": False, "pdma_pipeline": False, "pmd_pipeline": True}
        self.runs = {"ndma_pipeline": "success", "pdma_pipeline": "success", "pmd_pipeline": "failed"}

    def __call__(self, query, params=None):
        q = " ".join(query.split())
        if q.startswith("SELECT is_paused FROM dag"):
            return [{"is_paused": self.paused[params["d"]]}]
        if q.startswith("SELECT state, end_date FROM dag_run"):
            return [{"state": self.runs[params["d"]], "end_date": datetime(2026, 6, 9, 5)}]
        if "FROM risk.operational_risk" in q:
            return [{"latest": date(2026, 5, 20), "n": 10, "ingested": datetime(2026, 5, 20, 8)}]
        if "FROM risk.latest_operational_risk" in q:
            return [{"n": 0}]
        for table, value in self.max.items():
            if f"FROM {table}" in q:
                return [{"latest": value, "n": 0 if value is None else 7, "ingested": None if value is None else datetime(2026, 6, 9, 9)}]
        raise AssertionError(q)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(api_fresh, "fetch_all", db)
    return db


def by_domain(payload):
    return {d["domain"]: d for d in payload["domains"]}


def test_a_new_database_row_moves_the_latest_date_the_dashboard_selects(fake_db):
    before = by_domain(api_fresh.freshness())["ndma"]
    assert before["latest_data_date"] == "2026-06-01"
    fake_db.max["ndma_casualties"] = date(2026, 6, 9)                       # the DAG ingests a newer report
    after = by_domain(api_fresh.freshness())["ndma"]
    assert after["latest_data_date"] == "2026-06-09"                         # nothing is cached in the API: the very next request sees it
    assert describe(before, TODAY)["state"] == "stale" and describe(after, TODAY)["state"] == "current"
    assert describe(after, TODAY)["latest"] == "2026-06-09"


def test_each_domain_reports_its_own_date_kind_and_source_state(fake_db):
    d = by_domain(api_fresh.freshness())
    assert d["pdma_gauge"]["date_kind"] == "observation_datetime" and d["pdma_gauge"]["latest_data_date"] == "2026-06-08T12:00:00"
    assert d["pmd_weather"]["date_kind"] == "scraped_at"
    assert d["pmd_weather"]["ingestion"] == "disabled" and d["pmd_weather"]["source_state"] == "unavailable" and "HTTP 500" in d["pmd_weather"]["note"]
    assert d["ndma"]["ingestion"] == "scheduled" and d["ndma"]["source_state"] == "available"
    assert describe(d["pmd_weather"], TODAY)["state"] == "source_unavailable"      # never "current", whatever the age


def test_a_domain_without_rows_has_no_date_and_the_dashboard_says_no_data(fake_db):
    d = by_domain(api_fresh.freshness())["pdma_daily"]
    assert d["latest_data_date"] is None and d["rows"] == 0 and d["last_ingestion_at"] is None
    assert describe(d, TODAY)["state"] == "no_data"


def test_a_failed_last_run_marks_the_source_unavailable(fake_db):
    fake_db.runs["pdma_pipeline"] = "failed"
    d = by_domain(api_fresh.freshness())
    assert d["pdma_gauge"]["source_state"] == "unavailable" and d["pdma_rainfall"]["source_state"] == "unavailable"
    fake_db.runs["pdma_pipeline"] = "success"
    assert by_domain(api_fresh.freshness())["pdma_gauge"]["source_state"] == "available"


def test_unreadable_airflow_state_is_unknown_not_guessed(monkeypatch, fake_db):
    real = fake_db

    def flaky(query, params=None):
        if "dag" in query.lower() and "FROM dag" in query:
            raise RuntimeError("no airflow tables")
        return real(query, params)

    monkeypatch.setattr(api_fresh, "fetch_all", flaky)
    d = by_domain(api_fresh.freshness())["ndma"]
    assert d["ingestion"] == "unknown" and d["source_state"] == "unknown" and d["latest_data_date"] == "2026-06-01"


def test_risk_row_says_scores_are_withheld_and_that_it_can_lag(fake_db):
    r = by_domain(api_fresh.freshness())["risk"]
    assert r["latest_data_date"] == "2026-05-20" and r["scored_areas"] == 0 and r["ingestion"] == "manual"
    assert "numeric risk score" in r["note"].lower() and "lag" in r["note"]
