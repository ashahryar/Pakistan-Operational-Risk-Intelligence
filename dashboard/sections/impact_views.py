"""dashboard/sections/impact_views.py -- NDMA impact analytics (Task 42).

NDMA situation reports are CUMULATIVE: every report restates the running total. This module keeps the two ideas visibly apart:
  * "Cumulative reported" = each province's latest reported running total (a province's last reported value is carried forward to later dates; nothing is interpolated).
  * "Added by each report" = the increment between a province's consecutive reports (dashboard/utils/ndma_cumulative.py).
A national cumulative line is the sum of the provinces' latest cumulative figures as of that date, never the sum of the reports themselves.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.ui import components as C
from dashboard.ui import tokens
from dashboard.ui.charts import SERIES, animated_bars, heatmap, range_buttons, ranked_bar, style_fig, time_series

SOURCE = "NDMA situation reports"


def cumulative_long(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Per province and report date: the running total of the increments (= the cumulative figure the reports state). A province that has not reported the
    measure yet stays missing (never 0); on dates a province did not report, its last reported total is carried forward."""
    d = df[["report_date", "province", col]].copy()
    d["report_date"] = pd.to_datetime(d["report_date"])
    d = d.sort_values(["province", "report_date"])
    has = d.groupby("province")[col].transform(lambda s: s.notna().cumsum()) > 0
    d["cumulative"] = d.groupby("province")[col].transform(lambda s: s.fillna(0).cumsum()).where(has)
    grid = d.pivot_table(index="report_date", columns="province", values="cumulative", aggfunc="max").sort_index().ffill()
    return grid.stack().rename("cumulative").reset_index()


def national_cumulative(long: pd.DataFrame) -> pd.DataFrame:
    return long.groupby("report_date", as_index=False)["cumulative"].sum()


def weekly_increment_matrix(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Province x week matrix of what the reports of that week added (sum of increments). A cell with no report in that week is empty, never 0."""
    d = df[["report_date", "province", col]].copy()
    d["week"] = pd.to_datetime(d["report_date"]).dt.to_period("W").dt.start_time.dt.strftime("%d %b")
    order = list(dict.fromkeys(pd.to_datetime(d["report_date"]).dt.to_period("W").dt.start_time.sort_values().dt.strftime("%d %b")))
    m = d.pivot_table(index="province", columns="week", values=col, aggfunc=lambda s: s.sum(min_count=1)).reindex(columns=order)
    return m.loc[m.fillna(0).sum(axis=1).sort_values(ascending=False).index]


def weekly_checkpoints(long: pd.DataFrame) -> pd.DataFrame:
    """The last report date of each ISO week: a legitimate downsample for animation (the frame IS a real report date)."""
    dates = pd.Series(sorted(long["report_date"].unique()))
    last = dates.groupby(dates.dt.to_period("W")).max()
    return long[long["report_date"].isin(last.values)]


def render(df: pd.DataFrame, measures: dict[str, tuple[str, str]], *, noun: str, key: str) -> None:
    """measures: label -> (column, unit). Shows latest cumulative by province, cumulative trend, per-report increments and a Play/Pause progression."""
    C.section(f"{noun}: cumulative reporting and what each report added",
              "NDMA reports are cumulative. The first three views separate the running total from the change between reports; they are never added together.")
    if df is None or df.empty:
        C.empty_state("No NDMA data available", "The NDMA tables returned no rows, so there is nothing to chart.")
        return
    label = st.radio("Measure", list(measures), horizontal=True, key=f"{key}_measure")
    col, unit = measures[label]
    if df[col].dropna().empty:
        C.empty_state(f"{label}: not reported", "No report states a value for this measure. Blank means not reported, not zero.")
        return
    long = cumulative_long(df, col)
    latest_date = long["report_date"].max()
    latest = long[long["report_date"] == latest_date].dropna(subset=["cumulative"])
    asof = f"{latest_date:%d %b %Y}"

    left, right = st.columns([2, 3])
    with left:
        fig = ranked_bar(latest, "province", "cumulative", title=f"Cumulative {label.lower()} by province", unit=unit, source=SOURCE, as_of=asof, n=10)
        if fig is None:
            C.empty_state("No province has reported this measure", "")
        else:
            st.plotly_chart(fig, width="stretch", key=f"{key}_rank")
    with right:
        nat = national_cumulative(long.dropna(subset=["cumulative"]))
        fig = time_series(nat, "report_date", {f"Cumulative {label.lower()} (sum of provinces' latest totals)": "cumulative"}, title=f"Cumulative {label.lower()}, national",
                          unit=unit, source=SOURCE, slider=True, fill=True)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key=f"{key}_cum")

    inc = df.assign(report_date=pd.to_datetime(df["report_date"])).groupby("report_date", as_index=False)[col].sum(min_count=1).dropna(subset=[col])
    bars = go.Figure(go.Bar(x=inc["report_date"], y=inc[col], marker_color=SERIES[1],
                            hovertemplate=f"<b>Added by this report</b><br>%{{x|%d %b %Y}}<br>%{{y:,.0f}} {unit}<br><i>{SOURCE}</i><extra></extra>"))
    span = int((inc["report_date"].max() - inc["report_date"].min()).days) if len(inc) else 0
    bars.update_xaxes(type="date", tickformat="%d %b", rangeselector=dict(buttons=range_buttons(span), bgcolor=tokens.PALETTE["elevated"], activecolor=tokens.PALETTE["primary"],
                                                                              font=dict(color=tokens.PALETTE["text"], size=12)))
    st.plotly_chart(style_fig(bars, f"{label}: added by each report (increment, not a total)", 300, ytitle=unit,
                              source=f"Source: {SOURCE} · increments between a province's consecutive cumulative reports"), width="stretch", key=f"{key}_inc")

    hm = weekly_increment_matrix(df, col)
    fig_hm = heatmap(hm, title=f"{label} added per week, by province", unit=unit, source=SOURCE, xlabel="Week starting", ylabel="")
    if fig_hm is not None:
        st.plotly_chart(fig_hm, width="stretch", key=f"{key}_heat")

    weekly = weekly_checkpoints(long.dropna(subset=["cumulative"]))
    anim = animated_bars(weekly, "province", "cumulative", "report_date", title=f"How cumulative {label.lower()} built up (weekly checkpoints)", unit=unit, source=SOURCE, top=7)
    if anim is None:
        C.notice("info", "Progression not animated", "There are too many or too few checkpoints to animate honestly; the static views above show the full history.")
    else:
        st.plotly_chart(anim, width="stretch", key=f"{key}_anim")
        st.caption("Each frame is the last report of a week and shows each province's cumulative figure as of that report. Press Play to step through; nothing moves on its own.")
