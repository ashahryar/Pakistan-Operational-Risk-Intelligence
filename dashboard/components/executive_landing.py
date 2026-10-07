"""Task 40 -- the executive landing content of Home: purpose, honest data freshness, real KPIs, evidence coverage and risk availability.

Rules: a missing value is shown as "n/a", never 0; a NULL risk score is "abstained", never "low risk"; nothing here is labelled live or real-time
(the platform processes published bulletins in batches); there is no invented health or flood index.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

NA = "n/a"


def fmt(v, suffix: str = "") -> str:
    """Thousands-separated number, or n/a. Zero is a real value and is shown as 0."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return NA
    return f"{float(v):,.0f}{suffix}" if float(v) == int(float(v)) else f"{float(v):,.1f}{suffix}"


def latest(df: pd.DataFrame, col: str) -> Optional[str]:
    if df is None or df.empty or col not in df or df[col].dropna().empty:
        return None
    return pd.to_datetime(df[col]).max().strftime("%d %b %Y")


def risk_availability(rows: list[dict]) -> dict:
    """Counts over the latest risk row of every area (API /risk/latest). Pure; tested."""
    total = len(rows)
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["risk_status"]] = by_status.get(r["risk_status"], 0) + 1
    scored = sum(1 for r in rows if r.get("risk_score") is not None)
    insufficient = by_status.get("INSUFFICIENT_DATA", 0)
    latest_date = max((r["risk_date"] for r in rows), default=None)
    return {"areas": total, "latest_date": latest_date, "with_usable_signal": total - insufficient, "insufficient_data": insufficient, "scored": scored,
            "abstained": total - scored, "by_status": dict(sorted(by_status.items()))}


def render_intro() -> None:
    st.title("🇵🇰 Pakistan Operational Risk Intelligence")
    st.markdown(
        "Collects flood and disaster bulletins from NDMA, PDMA and PMD, validates them, places them on one administrative geography and "
        "serves **operational risk information together with the evidence behind it**. Where evidence is insufficient the platform "
        "**abstains instead of guessing**: a missing score is not a low risk.")
    st.caption("Decision support only; not an official warning. Data are published bulletins processed in batches (not a live feed).")


def render_ndma_kpis(summary: pd.DataFrame, casualties: pd.DataFrame) -> None:
    st.subheader("Disaster impact (NDMA situation reports)")
    s = summary.iloc[0] if summary is not None and not summary.empty else {}
    c = st.columns(5)
    c[0].metric("Deaths", fmt(s.get("total_deaths") if len(s) else None))
    c[1].metric("Injured", fmt(s.get("total_injured") if len(s) else None))
    c[2].metric("Houses damaged", fmt(s.get("total_houses_damaged") if len(s) else None))
    c[3].metric("Persons rescued", fmt(s.get("total_persons_rescued") if len(s) else None))
    c[4].metric("Provinces reporting", fmt(s.get("provinces_affected") if len(s) else None))
    first = pd.to_datetime(casualties["report_date"]).min().strftime("%d %b %Y") if casualties is not None and not casualties.empty else NA
    st.caption(f"NDMA reports are cumulative; each figure is the peak reported value per province, summed (reports {first} to {latest(casualties, 'report_date') or NA}). "
               "Rescue figures are cumulative in the same way.")


def _freshness_cells(fresh: Optional[dict], domain: str, fallback: Optional[str]) -> tuple[str, str]:
    """(latest, status) from the API freshness row; without it, the date derived from the loaded data and an explicit 'unknown' status."""
    from dashboard.utils.freshness import describe          # local import: the helper imports streamlit/the API client
    row = (fresh or {}).get(domain)
    if not row:
        return fallback or NA, "freshness unavailable"
    d = describe(row)
    latest_text = pd.to_datetime(d["latest"]).strftime("%d %b %Y") if d["latest"] else NA
    status = {"current": "current", "stale": f"stale ({d['age_days']} days old)", "source_unavailable": "source unavailable: no newer ingestion",
              "no_data": "no data available"}.get(d["state"], "unknown")
    return latest_text, status


def render_coverage(rainfall: pd.DataFrame, weather: pd.DataFrame, casualties: pd.DataFrame, evidence: dict, risk: dict, fresh: Optional[dict] = None) -> None:
    st.subheader("Data and evidence coverage")
    gauge = evidence or {}
    gs = gauge.get("summary", {})
    states = gs.get("state_counts", {})
    gauge_latest = max((s["date_max"] for s in gauge.get("stations", []) if s.get("date_max")), default=None)
    cells = {
        "ndma": _freshness_cells(fresh, "ndma", latest(casualties, "report_date")),
        "pdma_rainfall": _freshness_cells(fresh, "pdma_rainfall", latest(rainfall, "report_date")),
        "pmd_weather": _freshness_cells(fresh, "pmd_weather", latest(weather, "scraped_at")),
        "pdma_gauge": _freshness_cells(fresh, "pdma_gauge", pd.to_datetime(gauge_latest).strftime("%d %b %Y") if gauge_latest else None),
        "risk": _freshness_cells(fresh, "risk", pd.to_datetime(risk["latest_date"]).strftime("%d %b %Y") if risk and risk.get("latest_date") else None),
    }
    rows = [
        {"Domain": "NDMA sitreps (province)", "Records": fmt(len(casualties)) if casualties is not None else NA, "Latest available": cells["ndma"][0],
         "Status": cells["ndma"][1], "Geography": "province level"},
        {"Domain": "PDMA rainfall", "Records": fmt(len(rainfall)) if rainfall is not None else NA, "Latest available": cells["pdma_rainfall"][0],
         "Status": cells["pdma_rainfall"][1], "Geography": "station names resolved to districts by a deterministic resolver; some stay unresolved"},
        {"Domain": "PMD weather forecasts", "Records": fmt(len(weather)) if weather is not None else NA, "Latest available": cells["pmd_weather"][0],
         "Status": cells["pmd_weather"][1], "Geography": "one dated snapshot: no weather history"},
        {"Domain": "River gauges (PDMA)", "Records": fmt(gs.get("observations")), "Latest available": cells["pdma_gauge"][0], "Status": cells["pdma_gauge"][1],
         "Geography": f"{states.get('ELIGIBLE', 0)} of {gs.get('stations', 0)} stations mapped to a district from official evidence; "
                      f"{states.get('CONFLICTING_GEOGRAPHY', 0)} conflicting, {states.get('SECONDARY_ONLY', 0)} secondary-only, {states.get('UNRESOLVED', 0)} unresolved"
                      if gs else "evidence endpoint unavailable"},
        {"Domain": "Operational risk rows (latest per area)", "Records": fmt(risk.get("areas")) if risk else NA, "Latest available": cells["risk"][0],
         "Status": cells["risk"][1] + ("; computed by hand after ingestion, may lag" if risk else ""),
         "Geography": f"{risk.get('with_usable_signal', 0)} areas with a usable signal; {risk.get('insufficient_data', 0)} insufficient data" if risk else "risk API unavailable"},
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Latest available is the newest date in the data itself (report date, observation time or scrape time, depending on the domain). "
               "Status compares it with today and with the state of the ingesting DAG.")


def render_risk_availability(risk: dict, risk_date: Optional[str]) -> None:
    st.subheader("Risk availability")
    if not risk:
        st.info("The risk API is not reachable, so risk availability cannot be shown. Start it with `docker compose up -d api`.")
        return
    c = st.columns(4)
    c[0].metric("Areas with a risk record", fmt(risk["areas"]))
    c[1].metric("With a usable signal", fmt(risk["with_usable_signal"]))
    c[2].metric("Numeric scores", fmt(risk["scored"]))
    c[3].metric("Score abstained", fmt(risk["abstained"]))
    st.caption(f"Latest risk date {risk_date or NA}. Statuses ({', '.join(f'{k} {v}' for k, v in risk['by_status'].items())}) compare observed signals with "
               "**provisional** thresholds. A numeric score needs at least two independent eligible signal groups with evidence-based weights, which do not exist yet: "
               "so no score is produced. INSUFFICIENT_DATA means no usable signal, which is not the same as low risk. See the Risk Map and Operational Intelligence pages.")


def render_navigation() -> None:
    st.subheader("Where to go next")
    st.markdown(
        "- **Risk Map** - provisional status per area, with abstention and evidence shown explicitly\n"
        "- **Operational Intelligence** - ask the reports, analyse risk for an area, or let the read-only agent combine them\n"
        "- **NDMA Casualties / Damage, PMD Weather, PDMA Rainfall, PDMA Rivers** - the source data pages")
