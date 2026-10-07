"""dashboard/utils/freshness.py

Task 41 -- one place that turns an API freshness row (/api/v1/freshness) into the words a page shows, so no page implements its own date logic.

`describe()` is pure (the clock is a parameter) and returns a state:
  no_data            no row carries a date                         -> "No data available"
  source_unavailable ingestion disabled / last run failed          -> latest date is still shown, but as the last SUCCESSFUL data, with the reason
  stale              latest date older than the domain's threshold -> "Stale: ..."
  current            within the threshold
A field is shown only when the API supplied it (an unsupported field is left out, never defaulted). Nothing is called live.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.utils.api_cache import cached_api

NA = "n/a"

# Days after which a domain's latest data is flagged stale (a presentation threshold, not a risk parameter).
STALE_AFTER_DAYS = {"ndma": 7, "pdma_rainfall": 7, "pdma_gauge": 2, "pdma_daily": 3, "pmd_weather": 2, "risk": 7}
DATE_KIND = {"report_date": "report date", "observation_datetime": "observation time", "scraped_at": "scrape time", "risk_date": "risk date"}


def _as_date(v: Any) -> Optional[date]:
    if v in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "")).date()
    except ValueError:
        return None


def describe(row: Optional[dict], today: Optional[date] = None) -> dict:
    """-> {state, headline, latest, last_ingestion, age_days, source_status, note, fields}. Pure."""
    today = today or date.today()
    if not row:
        return {"state": "unknown", "headline": "Freshness unavailable (the API did not return this domain).", "latest": None, "last_ingestion": None,
                "age_days": None, "source_status": None, "note": None, "fields": []}
    latest = _as_date(row.get("latest_data_date"))
    ingested = _as_date(row.get("last_ingestion_at"))
    age = (today - latest).days if latest else None
    kind = DATE_KIND.get(row.get("date_kind"), "date")
    src = row.get("source_state")
    if latest is None:
        state, headline = "no_data", "No data available."
    elif src == "unavailable":
        state, headline = "source_unavailable", f"Latest available: {latest.isoformat()} ({kind}). Source currently unavailable: no newer successful ingestion."
    elif age is not None and age > STALE_AFTER_DAYS.get(row.get("domain"), 7):
        state, headline = "stale", f"Stale: latest available {latest.isoformat()} ({kind}), {age} days old."
    else:
        state, headline = "current", f"Latest available: {latest.isoformat()} ({kind})."
    fields = [("Latest available", latest.isoformat() if latest else NA)]
    if ingested:
        fields.append(("Last successful ingestion", ingested.isoformat()))
    if src in ("available", "unavailable"):
        fields.append(("Source status", src.capitalize()))
    return {"state": state, "headline": headline, "latest": latest.isoformat() if latest else None, "last_ingestion": ingested.isoformat() if ingested else None,
            "age_days": age, "source_status": src if src in ("available", "unavailable") else None, "note": row.get("note"), "fields": fields}


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


@cached_api(ttl=60)
def _freshness(base_url: str):
    return _client().freshness()


def freshness_rows() -> dict:
    """{domain: row}; empty when the API is unreachable (callers then show 'unavailable', not a guessed date)."""
    res = _freshness(_client().base_url)
    return {r["domain"]: r for r in (res.data or {}).get("domains", [])} if res.ok else {}


def render_freshness(domain: str, where=None) -> dict:
    """Caption/notice for one domain. Warns on stale or unavailable-source data. Returns the described dict."""
    d = describe(freshness_rows().get(domain))
    target = where if where is not None else st
    line = d["headline"] + ("  " + " · ".join(f"{k}: {v}" for k, v in d["fields"][1:]) if len(d["fields"]) > 1 else "")
    if d["state"] in ("source_unavailable", "stale", "no_data"):
        target.warning(line)
    elif d["state"] == "unknown":
        target.caption(line)
    else:
        target.caption(line)
    if d["note"]:
        target.caption(d["note"])
    return d
