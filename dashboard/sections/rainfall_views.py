"""dashboard/sections/rainfall_views.py -- PDMA rainfall analytics (Task 42).

Station names are the free-text strings printed in the reports. Some are lists of districts or table headers; they are counted as unresolved and never attributed.
Report dates are sparse (a report is not published every day), so the trend keeps its gaps and says how many dates exist; nothing is interpolated.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.ui import components as C
from dashboard.ui import tokens
from dashboard.ui.charts import animated_bars, ranked_bar, style_fig, time_series

SOURCE = "PDMA Punjab rainfall reports"
BINS = [(0, 0.0, "0 mm (reported dry)"), (0.01, 1, "Trace to 1 mm"), (1, 5, "1–5 mm"), (5, 10, "5–10 mm"), (10, 25, "10–25 mm"), (25, 50, "25–50 mm"), (50, float("inf"), "50 mm and over")]
JUNK_NAMES = {"stations", "station", "district", "districts", "unknown"}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["report_date"] = pd.to_datetime(d["report_date"], errors="coerce")
    d["rainfall_mm"] = pd.to_numeric(d["rainfall_mm"], errors="coerce")
    d["station"] = d["station"].fillna("").astype(str).str.strip()
    return d.dropna(subset=["report_date"])


def name_kind(name: str) -> str:
    """'list' (several districts in one string), 'header' (a table heading), or 'station'. Pure."""
    n = name.strip().lower()
    if n in JUNK_NAMES or not n:
        return "header"
    return "list" if ("," in n or "/" in n or " and " in n) else "station"


def intensity_counts(values: pd.Series) -> pd.DataFrame:
    """Readings per conventional intensity band. A reported 0 is a real dry reading; a missing value is not counted at all."""
    v = values.dropna()
    rows = []
    for lo, hi, label in BINS:
        if hi == 0.0:
            mask = v == 0
        elif lo == 0.01:
            mask = (v > 0) & (v < hi)
        else:
            mask = (v >= lo) & (v < hi)
        rows.append({"band": label, "readings": int(mask.sum())})
    return pd.DataFrame(rows)


def render(df: pd.DataFrame) -> None:
    C.section("Rainfall analytics", "Report-station readings from PDMA Punjab. Gaps are dates with no published report.")
    if df is None or df.empty:
        C.empty_state("No rainfall observations available", "The rainfall table returned no rows.")
        return
    d = clean(df)
    if d.empty:
        C.empty_state("No dated rainfall reports", "No row carries a report date.")
        return
    kinds = d["station"].map(name_kind)
    usable = d[(kinds == "station") & d["rainfall_mm"].notna()]
    latest_date = usable["report_date"].max() if not usable.empty else d["report_date"].max()
    asof = f"{latest_date:%d %b %Y}"

    C.kpis([("Report dates", int(d["report_date"].nunique()), f"{d['report_date'].min():%d %b %Y} to {d['report_date'].max():%d %b %Y}"),
            ("Station names", int(usable["station"].nunique()), "single-station names"),
            ("District-list names (unresolved)", int(d.loc[kinds == "list", "station"].nunique()), "several districts in one string; never attributed"),
            ("Latest report", asof)])

    per_date = usable.groupby("report_date").agg(highest=("rainfall_mm", "max"), median=("rainfall_mm", "median"), stations=("station", "nunique")).reset_index()
    fig = time_series(per_date, "report_date", {"Highest station": "highest", "Median station": "median"}, title="Rainfall per report: highest and median station", unit="mm",
                      source=SOURCE, slider=True)
    if fig is not None:
        st.plotly_chart(fig, width="stretch", key="rain_trend")

    left, right = st.columns(2)
    with left:
        last = usable[usable["report_date"] == latest_date]
        fig = ranked_bar(last, "station", "rainfall_mm", title=f"Stations in the latest report ({asof})", unit="mm", source=SOURCE, as_of=asof, n=12)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="rain_rank")
    with right:
        bands = intensity_counts(usable["rainfall_mm"])
        fig = go.Figure(go.Bar(x=bands["band"], y=bands["readings"], marker_color=tokens.PALETTE["primary"], text=bands["readings"], textposition="outside", cliponaxis=False,
                               hovertemplate="<b>%{x}</b><br>%{y} station readings<br><i>" + SOURCE + "</i><extra></extra>"))
        st.plotly_chart(style_fig(fig, "How intense are the readings? (all reports)", 340, ytitle="Station readings", source=f"Source: {SOURCE} · bands are conventional, not warning thresholds"),
                        width="stretch", key="rain_bands")

    cov = per_date.rename(columns={"stations": "Stations reporting"})
    fig = go.Figure(go.Bar(x=cov["report_date"], y=cov["Stations reporting"], marker_color=tokens.PALETTE["unavailable"],
                           hovertemplate="%{x|%d %b %Y}<br>%{y} stations reported<br><i>" + SOURCE + "</i><extra></extra>"))
    fig.update_xaxes(type="date", tickformat="%d %b")
    st.plotly_chart(style_fig(fig, "Station coverage: how many stations each report contained", 260, ytitle="Stations",
                              source=f"Source: {SOURCE} · single-station names only; district lists and table headers excluded"), width="stretch", key="rain_cov")

    dates = sorted(usable["report_date"].unique())[-60:]
    top = usable[usable["report_date"].isin(dates)]
    anim = animated_bars(top, "station", "rainfall_mm", "report_date", title="Rainfall by station, report by report", unit="mm", source=SOURCE, top=10)
    if anim is None:
        C.notice("info", "Progression not animated", "Too few or too many report dates to animate honestly.")
    else:
        st.plotly_chart(anim, width="stretch", key="rain_anim")
        st.caption("Frames are real report dates (the latest 60). A station absent from a report has no bar in that frame: nothing is filled in. Press Play to step through.")
