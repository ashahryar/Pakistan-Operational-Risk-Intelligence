"""dashboard/sections/weather_views.py -- PMD weather analytics (Task 42).

Only ONE dated PMD collection exists (the source overwrites its snapshot and is currently unavailable), so there is no weather history: this module draws comparisons
within that snapshot (which cities are hottest, how temperature relates to humidity, which conditions are forecast) and names the snapshot date on every chart.
It never draws a trend and never presents the snapshot as current weather.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.ui import components as C
from dashboard.ui import tokens
from dashboard.ui.charts import ranked_bar, style_fig

SOURCE = "PMD city forecast snapshot"


def snapshot_date(df: pd.DataFrame):
    d = pd.to_datetime(df["scraped_at"], errors="coerce").dropna()
    return d.max() if len(d) else None


def normalise_province(col: pd.Series) -> pd.Series:
    """A city whose province could not be resolved arrives as NULL or the literal 'Unknown'; both are 'Unresolved' (never assigned a province)."""
    s = col.astype("string").str.strip()
    return s.where(s.notna() & (s != "") & (s.str.lower() != "unknown"), "Unresolved").astype(object)


def condition_counts(df: pd.DataFrame, col: str = "day1_forecast", top: int = 8) -> pd.DataFrame:
    s = df[col].dropna().astype(str).str.strip()
    s = s[s != ""]
    return s.value_counts().head(top).rename_axis("condition").reset_index(name="cities")


def render(df: pd.DataFrame) -> None:
    C.section("Weather snapshot analytics", "Comparisons within the latest successful PMD snapshot. This is not a current forecast and there is no history to trend.")
    if df is None or df.empty:
        C.empty_state("No PMD observations available", "The forecast table returned no rows.")
        return
    when = snapshot_date(df)
    asof = f"{when:%d %b %Y}" if when is not None else "unknown date"
    d = df.copy()
    d["max_temperature"] = pd.to_numeric(d["max_temperature"], errors="coerce")
    d["humidity"] = pd.to_numeric(d["humidity"], errors="coerce")
    d["province"] = normalise_province(d["province"])
    C.kpis([("Cities in the snapshot", int(d["city"].nunique())), ("Snapshot date", asof, "latest successful PMD collection"),
            ("Hottest city", (d.loc[d["max_temperature"].idxmax(), "city"] if d["max_temperature"].notna().any() else None),
             f"{d['max_temperature'].max():.0f} °C" if d["max_temperature"].notna().any() else None),
            ("Cities with unresolved province", int((d["province"] == "Unresolved").sum()), "not assigned to a province")])

    left, right = st.columns(2)
    with left:
        fig = ranked_bar(d, "city", "max_temperature", title=f"Forecast temperature by city ({asof})", unit="°C", source=SOURCE, as_of=asof, n=15)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="wx_rank")
        else:
            C.empty_state("No temperatures in the snapshot", "")
    with right:
        sc = d.dropna(subset=["max_temperature", "humidity"])
        if sc.empty:
            C.empty_state("No temperature and humidity pairs", "")
        else:
            fig = go.Figure(go.Scatter(x=sc["humidity"], y=sc["max_temperature"], mode="markers", text=sc["city"], customdata=sc["province"],
                                       marker=dict(size=9, color=tokens.PALETTE["primary"], line=dict(color=tokens.PALETTE["bg"], width=1)),
                                       hovertemplate="<b>%{text}</b> · %{customdata}<br>%{y:.0f} °C · %{x:.0f} % humidity<br>snapshot " + asof + "<br><i>" + SOURCE + "</i><extra></extra>"))
            st.plotly_chart(style_fig(fig, "Which cities are hot and humid? (each point is a city)", 400, xtitle="Relative humidity (%)", ytitle="Temperature (°C)",
                                      source=f"Source: {SOURCE} · {asof}"), width="stretch", key="wx_scatter")

    cc = condition_counts(d)
    if not cc.empty:
        fig = go.Figure(go.Bar(x=cc["cities"], y=cc["condition"], orientation="h", marker_color=tokens.PALETTE["primary"], text=cc["cities"], textposition="outside", cliponaxis=False,
                               hovertemplate="<b>%{y}</b><br>%{x} cities, day-1 forecast<br>" + asof + "<br><i>" + SOURCE + "</i><extra></extra>"))
        fig.update_layout(yaxis=dict(autorange="reversed"), showlegend=False)
        st.plotly_chart(style_fig(fig, "Day-1 forecast conditions across cities", 300, xtitle="Cities", ytitle="", source=f"Source: {SOURCE} · {asof}"), width="stretch", key="wx_cond")
