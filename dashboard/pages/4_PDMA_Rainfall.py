"""
dashboard/pages/4_PDMA_Rainfall.py

PDMA Rainfall Intelligence — "Obsidian Enterprise" UI.

UI-only redesign per DESIGN.md ("Obsidian Enterprise") and the
approved reference layout. NOTHING below changes: get_rainfall(),
data cleaning, dedup logic, sidebar filter widgets/logic, filtering
logic, any KPI/summary calculation, chart data/x/y/color bindings,
the rainfall-status thresholds, table columns, or the CSV export
content/filename. Only presentation — CSS, layout, typography,
spacing, chart cosmetics, and card/table structure. Every variable
name is unchanged; repeated card/metric markup is now built through
small helper functions instead of duplicated HTML strings, per the
"do not duplicate CSS / reusable helper functions" instruction.

Not implemented (flagged rather than faked): the reference screenshot
shows a top nav ("Executive Summary / Station Monitoring / Trends /
Alerts") and bell/gear/profile icons. This script is a single
continuous page, not a multi-view app, and there is no distinct
"Alerts" content beyond the existing status indicator — adding
non-functional nav links or icons would be decorative dead UI, so
they were left out, exactly as with the other redesigned pages in
this project.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    AUTO_REFRESH = True
except Exception:
    AUTO_REFRESH = False

from dashboard.db import get_rainfall

# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="PDMA Rainfall Intelligence",
    page_icon="🌧",
    layout="wide",
)

# ==========================================================
# AUTO REFRESH
# ==========================================================

if AUTO_REFRESH:
    st_autorefresh(
        interval=60000,
        key="rainfall_refresh",
    )

# ==========================================================
# OBSIDIAN ENTERPRISE DESIGN SYSTEM (CSS)
# Tokens sourced from DESIGN.md ("Obsidian Enterprise")
# ==========================================================

st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>

:root{

    --ob-bg: #111111;
    --ob-bg-sidebar: #1a1a1a;
    --ob-card: #202020;
    --ob-border: #303030;
    --ob-border-hover: #454545;

    --ob-text: #e5e2e1;
    --ob-text-muted: #b5b5b5;
    --ob-text-dim: #8e9192;

    --ob-white: #ffffff;

    --ob-success: #22c55e;
    --ob-warning: #f59e0b;
    --ob-danger: #ef4444;
    --ob-info: #93c5fd;

    --ob-radius: 4px;

    --ob-sp-xs: 4px;
    --ob-sp-sm: 8px;
    --ob-sp-md: 16px;
    --ob-sp-lg: 24px;
    --ob-sp-xl: 48px;

    --ob-font-heading: 'Inter', sans-serif;
    --ob-font-body: 'IBM Plex Sans', sans-serif;
    --ob-font-mono: 'JetBrains Mono', ui-monospace, monospace;

}

html, body, [class*="css"]{
    font-family: var(--ob-font-body);
    color: var(--ob-text);
}

.block-container{
    max-width: 1600px;
    padding-top: var(--ob-sp-lg);
    padding-bottom: var(--ob-sp-xl);
    padding-left: var(--ob-sp-lg);
    padding-right: var(--ob-sp-lg);
}

hr{
    border-color: var(--ob-border) !important;
    opacity: 1 !important;
    margin-top: var(--ob-sp-lg) !important;
    margin-bottom: var(--ob-sp-lg) !important;
}

h1, h2, h3, h4, h5{
    font-family: var(--ob-font-heading);
    color: var(--ob-white);
    letter-spacing: -0.02em;
}

/* ---------------------------------------------------------
   HEADER
   --------------------------------------------------------- */

.ob-header{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ob-sp-md);
    flex-wrap: wrap;
}

.ob-title-block{ display: flex; align-items: center; gap: var(--ob-sp-md); }
.ob-title-icon{ font-size: 26px; line-height: 1; }

.ob-main-title{
    font-family: var(--ob-font-heading);
    font-size: 24px;
    font-weight: 700;
    color: var(--ob-white);
    margin: 0;
}

.ob-subtitle{
    font-family: var(--ob-font-body);
    font-size: 13px;
    color: var(--ob-text-muted);
    margin-top: 2px;
}

.ob-live-badge{
    display: inline-flex;
    align-items: center;
    gap: var(--ob-sp-sm);
    padding: 6px 14px;
    border-radius: var(--ob-radius);
    background: transparent;
    border: 1px solid var(--ob-border);
    color: var(--ob-white);
    font-family: var(--ob-font-mono);
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
}

.ob-live-badge .dot{
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--ob-success);
    box-shadow: 0 0 0 0 rgba(34,197,94,.5);
    animation: ob-pulse 1.8s infinite;
}

@keyframes ob-pulse{
    0%   { box-shadow: 0 0 0 0 rgba(34,197,94,.5); }
    70%  { box-shadow: 0 0 0 7px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}

/* ---------------------------------------------------------
   CARD PRIMITIVE (shared shell)
   --------------------------------------------------------- */

.ob-card{
    background: var(--ob-card);
    border: 1px solid var(--ob-border);
    border-radius: var(--ob-radius);
    padding: var(--ob-sp-lg);
    transition: border-color .15s ease;
}

.ob-card:hover{ border-color: var(--ob-border-hover); }

.ob-card-header{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--ob-sp-md);
}

.ob-card-title{
    display: flex;
    align-items: center;
    gap: var(--ob-sp-sm);
    font-family: var(--ob-font-heading);
    font-size: 15px;
    font-weight: 700;
    color: var(--ob-white);
}

.ob-card-title .icon{ opacity: .85; }

/* ---------------------------------------------------------
   METRIC TILES (KPIs)
   --------------------------------------------------------- */

.ob-tile{
    background: var(--ob-card);
    border: 1px solid var(--ob-border);
    border-radius: var(--ob-radius);
    padding: var(--ob-sp-md) var(--ob-sp-lg);
    height: 108px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 6px;
    transition: border-color .15s ease, transform .15s ease;
}

.ob-tile:hover{ border-color: var(--ob-border-hover); transform: translateY(-2px); }

.ob-tile-label{
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: var(--ob-font-body);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--ob-text-muted);
}

.ob-tile-value{
    font-family: var(--ob-font-mono);
    font-size: 26px;
    font-weight: 600;
    color: var(--ob-white);
    line-height: 1.15;
}

.ob-tile-value .unit{
    font-size: 14px;
    color: var(--ob-text-muted);
    font-weight: 500;
    margin-left: 4px;
}

.ob-tile-note{
    font-family: var(--ob-font-mono);
    font-size: 11.5px;
    color: var(--ob-text-dim);
}

/* ---------------------------------------------------------
   STATUS / HIGHLIGHT CARDS (dot indicator, not full-color fill)
   --------------------------------------------------------- */

.ob-status-card{
    background: var(--ob-card);
    border: 1px solid var(--ob-border);
    border-radius: var(--ob-radius);
    padding: var(--ob-sp-lg);
    height: 100%;
}

.ob-status-title{
    display: flex;
    align-items: center;
    gap: var(--ob-sp-sm);
    font-family: var(--ob-font-body);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--ob-text-muted);
    margin-bottom: var(--ob-sp-sm);
}

.ob-status-dot{
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0;
}

.ob-status-value{
    font-family: var(--ob-font-heading);
    font-size: 20px;
    font-weight: 700;
    color: var(--ob-white);
    margin-bottom: 6px;
}

.ob-status-sub{
    font-family: var(--ob-font-mono);
    font-size: 12.5px;
    color: var(--ob-text-muted);
    line-height: 1.6;
}

/* ---------------------------------------------------------
   CHART CONTAINERS
   --------------------------------------------------------- */

div[data-testid="stPlotlyChart"]{
    background: var(--ob-card);
    border: 1px solid var(--ob-border);
    border-radius: var(--ob-radius);
    padding: var(--ob-sp-md);
}

/* ---------------------------------------------------------
   TABLES (JetBrains Mono numerics, right-aligned per spec)
   --------------------------------------------------------- */

div[data-testid="stDataFrame"]{
    border: 1px solid var(--ob-border);
    border-radius: var(--ob-radius);
    overflow: hidden;
}

div[data-testid="stDataFrame"] table{
    font-family: var(--ob-font-mono);
    font-size: 12.5px;
}

div[data-testid="stDataFrame"] thead tr th{
    background: var(--ob-bg-sidebar) !important;
    color: var(--ob-text-muted) !important;
    font-family: var(--ob-font-body);
    font-weight: 600;
    font-size: 11px;
    letter-spacing: .04em;
    text-transform: uppercase;
    position: sticky;
    top: 0;
    z-index: 2;
}

/* ---------------------------------------------------------
   SIDEBAR
   --------------------------------------------------------- */

section[data-testid="stSidebar"]{
    background: var(--ob-bg-sidebar);
    border-right: 1px solid var(--ob-border);
}

section[data-testid="stSidebar"] .block-container{
    padding-top: var(--ob-sp-lg);
    padding-left: var(--ob-sp-md);
    padding-right: var(--ob-sp-md);
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3{
    font-family: var(--ob-font-body);
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--ob-text-muted);
}

section[data-testid="stSidebar"] label{
    font-family: var(--ob-font-body);
    font-size: 12.5px !important;
    color: var(--ob-text) !important;
}

section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
section[data-testid="stSidebar"] div[data-baseweb="base-input"]{
    border-radius: var(--ob-radius) !important;
    background: var(--ob-bg) !important;
    border: 1px solid var(--ob-border) !important;
    color: var(--ob-text) !important;
}

section[data-testid="stSidebar"] div[data-baseweb="tag"]{
    background: var(--ob-border) !important;
    border-radius: var(--ob-radius) !important;
    font-family: var(--ob-font-mono);
    font-size: 11.5px;
}

/* ---------------------------------------------------------
   NATIVE ELEMENT OVERRIDES
   --------------------------------------------------------- */

div[data-testid="stMetric"]{
    background: var(--ob-card);
    border: 1px solid var(--ob-border);
    border-radius: var(--ob-radius);
    padding: var(--ob-sp-sm) var(--ob-sp-md);
}

div[data-testid="stMetric"] label{ color: var(--ob-text-muted) !important; font-family: var(--ob-font-body); }
div[data-testid="stMetric"] [data-testid="stMetricValue"]{
    color: var(--ob-white) !important;
    font-family: var(--ob-font-mono) !important;
}

div[data-testid="stAlert"]{
    background: var(--ob-card);
    border: 1px solid var(--ob-border);
    border-radius: var(--ob-radius);
}

.stButton > button{
    border-radius: var(--ob-radius);
    background: transparent;
    border: 1px solid var(--ob-border);
    color: var(--ob-white);
    font-family: var(--ob-font-body);
    font-weight: 600;
    font-size: 13px;
}

.stButton > button:hover{
    border-color: var(--ob-white);
}

.stDownloadButton > button{
    border-radius: var(--ob-radius);
    background: var(--ob-white);
    border: 1px solid var(--ob-white);
    color: #111111;
    font-family: var(--ob-font-body);
    font-weight: 700;
    font-size: 13px;
}

.stDownloadButton > button:hover{
    background: #e5e2e1;
}

/* ---------------------------------------------------------
   RESPONSIVE
   --------------------------------------------------------- */

@media (max-width: 1024px){
    .ob-main-title{ font-size: 19px; }
    .ob-header{ flex-direction: column; align-items: flex-start; }
    .ob-tile{ height: auto; min-height: 92px; }
}

</style>
""",
    unsafe_allow_html=True,
)

# ==========================================================
# UI HELPER FUNCTIONS (presentation only — no logic)
# ==========================================================

def render_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
<div class="ob-header">
  <div class="ob-title-block">
    <div class="ob-title-icon">🌧</div>
    <div>
      <div class="ob-main-title">{title}</div>
      <div class="ob-subtitle">{subtitle}</div>
    </div>
  </div>
  <div class="ob-live-badge"><span class="dot"></span> Live</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_card_header(icon: str, title: str) -> None:
    st.markdown(
        f"""
<div class="ob-card-header">
  <div class="ob-card-title"><span class="icon">{icon}</span> {title}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_metric_tile(label: str, value: str, unit: str = "", note: str = "") -> str:
    return f"""
<div class="ob-tile">
  <div class="ob-tile-label">{label}</div>
  <div class="ob-tile-value">{value}{f'<span class="unit">{unit}</span>' if unit else ''}</div>
  {f'<div class="ob-tile-note">{note}</div>' if note else ''}
</div>
"""


def render_status_card(
    icon: str,
    label: str,
    value_html: str,
    sub_html: str = "",
    dot_color: str = "var(--ob-success)",
) -> str:
    return f"""
<div class="ob-status-card">
  <div class="ob-status-title"><span class="ob-status-dot" style="background:{dot_color};"></span>{icon} {label}</div>
  <div class="ob-status-value">{value_html}</div>
  <div class="ob-status-sub">{sub_html}</div>
</div>
"""


_STATUS_DOT_MAP = {
    "🔴 Extreme Rainfall": "var(--ob-danger)",
    "🟠 Heavy Rainfall": "#f97316",
    "🟡 Moderate Rainfall": "var(--ob-warning)",
    "🟢 Normal Rainfall": "var(--ob-success)",
}

_PLOTLY_FONT = dict(family="IBM Plex Sans, sans-serif", size=12, color="#e5e2e1")

_PLOTLY_LAYOUT_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=_PLOTLY_FONT,
)


def style_fig(fig, **layout_overrides):
    """
    Apply the shared Obsidian Enterprise chart cosmetics (dark
    transparent background, IBM Plex Sans font) on top of whatever
    layout the chart already has, then apply any per-chart overrides
    passed in. Does not touch any trace data.
    """
    fig.update_layout(**_PLOTLY_LAYOUT_BASE)
    fig.update_layout(**layout_overrides)
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")
    return fig


# ==========================================================
# HEADER
# ==========================================================

render_header(
    "Punjab Rainfall Intelligence",
    "Provincial Disaster Management Authority (PDMA) • Live Rainfall Monitoring &amp; Early Warning Intelligence",
)

st.divider()

# ==========================================================
# LOAD DATA
# ==========================================================

with st.spinner("Loading latest PDMA rainfall data..."):

    try:
        df = get_rainfall()

    except Exception as e:
        st.error(f"Database Error\n\n{e}")
        st.stop()

if df.empty:
    st.warning("No rainfall data available.")
    st.stop()

# ==========================================================
# DATA CLEANING
# ==========================================================

df = df.copy()

df["report_date"] = pd.to_datetime(
    df["report_date"],
    errors="coerce",
)

df["rainfall_mm"] = pd.to_numeric(
    df["rainfall_mm"],
    errors="coerce",
).fillna(0)

df["station"] = (
    df["station"]
    .fillna("Unknown")
    .astype(str)
    .str.strip()
)

if "scraped_at" in df.columns:

    df["scraped_at"] = pd.to_datetime(
        df["scraped_at"],
        errors="coerce",
    )

    latest_update = df["scraped_at"].max()

else:

    latest_update = df["report_date"].max()

# ==========================================================
# REMOVE DUPLICATES
# ==========================================================

sort_column = "scraped_at" if "scraped_at" in df.columns else "report_date"

df = (
    df
    .sort_values(sort_column)
    .drop_duplicates(
        subset=["station"],
        keep="last",
    )
)

# ==========================================================
# LIVE STATUS
# ==========================================================

left, right = st.columns([3, 1])

with left:

    st.markdown(
        render_status_card(
            "🛰",
            "Live Rainfall Feed",
            f"{latest_update.strftime('%d %b %Y')} &nbsp;·&nbsp; {latest_update.strftime('%I:%M:%S %p')}",
            "Dashboard refreshes automatically every 60 seconds.",
            dot_color="var(--ob-success)",
        ),
        unsafe_allow_html=True,
    )

with right:

    st.metric(
        "🌧 Reporting Stations",
        f"{df['station'].nunique():,}",
    )

st.divider()

# ==========================================================
# SIDEBAR FILTERS
# ==========================================================

st.sidebar.header("🌧 Dashboard Filters")

# ----------------------------------------------------------
# Top N Stations
# ----------------------------------------------------------

top_n = st.sidebar.slider(
    "🏆 Top Rainfall Stations",
    min_value=5,
    max_value=30,
    value=10,
)

# ----------------------------------------------------------
# Date Filter
# ----------------------------------------------------------

min_date = df["report_date"].min().date()
max_date = df["report_date"].max().date()

date_range = st.sidebar.date_input(
    "📅 Report Date",
    (min_date, max_date),
)

# ----------------------------------------------------------
# Station Filter
# ----------------------------------------------------------

station_list = sorted(
    df["station"].dropna().unique()
)

selected_station = st.sidebar.multiselect(
    "📍 Station",
    station_list,
    default=station_list,
)

# ----------------------------------------------------------
# Search Station
# ----------------------------------------------------------

search_station = st.sidebar.text_input(
    "🔍 Search Station",
    placeholder="e.g. Lahore Airport",
)

# ----------------------------------------------------------
# Rainfall Range
# ----------------------------------------------------------

min_rain = float(df["rainfall_mm"].min())
max_rain = float(df["rainfall_mm"].max())

rainfall_range = st.sidebar.slider(
    "🌧 Rainfall (mm)",
    min_value=min_rain,
    max_value=max_rain,
    value=(min_rain, max_rain),
)

# ----------------------------------------------------------
# Latest Records Only
# ----------------------------------------------------------

latest_only = st.sidebar.checkbox(
    "Show Latest Record Per Station",
    value=False,
)

st.sidebar.divider()

st.sidebar.caption(
    f"""
Stations Available : **{df['station'].nunique()}**

Total Records : **{len(df):,}**
"""
)

# ==========================================================
# APPLY FILTERS
# ==========================================================

filtered = df.copy()

# ----------------------------------------------------------
# Station Filter
# ----------------------------------------------------------

filtered = filtered[
    filtered["station"].isin(selected_station)
]

# ----------------------------------------------------------
# Date Filter
# ----------------------------------------------------------

if len(date_range) == 2:

    start = pd.to_datetime(date_range[0])
    end = pd.to_datetime(date_range[1])

    filtered = filtered[
        (filtered["report_date"] >= start)
        &
        (filtered["report_date"] <= end)
    ]

# ----------------------------------------------------------
# Search Filter
# ----------------------------------------------------------

if search_station.strip():

    filtered = filtered[
        filtered["station"].str.contains(
            search_station,
            case=False,
            na=False,
        )
    ]

# ----------------------------------------------------------
# Rainfall Filter
# ----------------------------------------------------------

filtered = filtered[
    filtered["rainfall_mm"].between(
        rainfall_range[0],
        rainfall_range[1],
    )
]

# ----------------------------------------------------------
# Latest Record Per Station
# ----------------------------------------------------------

if latest_only:

    sort_col = (
        "scraped_at"
        if "scraped_at" in filtered.columns
        else "report_date"
    )

    filtered = (
        filtered
        .sort_values(sort_col)
        .drop_duplicates(
            subset=["station"],
            keep="last",
        )
    )

# ----------------------------------------------------------
# Empty Check
# ----------------------------------------------------------

if filtered.empty:

    st.warning(
        "No rainfall records found for the selected filters."
    )

    st.stop()

filtered = (
    filtered
    .sort_values(
        ["report_date", "station"],
        ascending=[False, True],
    )
    .reset_index(drop=True)
)

st.divider()

# ==========================================================
# EXECUTIVE SUMMARY
# ==========================================================

latest_date = filtered["report_date"].max()

total_rainfall = filtered["rainfall_mm"].sum()

avg_rainfall = filtered["rainfall_mm"].mean()

max_rainfall = filtered["rainfall_mm"].max()

station_count = filtered["station"].nunique()

reading_count = len(filtered)

highest_station = filtered.loc[
    filtered["rainfall_mm"].idxmax()
]

# ----------------------------------------------------------
# RAINFALL STATUS
# ----------------------------------------------------------

if max_rainfall >= 150:
    status = "🔴 Extreme Rainfall"

elif max_rainfall >= 100:
    status = "🟠 Heavy Rainfall"

elif max_rainfall >= 50:
    status = "🟡 Moderate Rainfall"

else:
    status = "🟢 Normal Rainfall"

# ==========================================================
# LIVE EXECUTIVE PANEL
# ==========================================================

left, right = st.columns([3, 1])

with left:

    st.markdown(
        render_status_card(
            "🌧",
            "Live Rainfall Intelligence",
            latest_date.strftime("%d %b %Y"),
            f"Stations Reporting : {station_count} &nbsp;·&nbsp; "
            f"Current Status : {status}<br>"
            f"Dashboard refreshes automatically after every ETL execution.",
            dot_color=_STATUS_DOT_MAP.get(status, "var(--ob-success)"),
        ),
        unsafe_allow_html=True,
    )

with right:

    st.metric(
        "🕒 Last Report",
        latest_date.strftime("%d %b"),
        latest_date.strftime("%I:%M %p"),
    )

st.divider()

# ==========================================================
# KPI CARDS
# ==========================================================

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.markdown(
        render_metric_tile("📍 Stations", f"{station_count:,}"),
        unsafe_allow_html=True,
    )

with k2:
    st.markdown(
        render_metric_tile("📄 Readings", f"{reading_count:,}"),
        unsafe_allow_html=True,
    )

with k3:
    st.markdown(
        render_metric_tile("☔ Avg Rainfall", f"{avg_rainfall:.1f}", unit="mm"),
        unsafe_allow_html=True,
    )

with k4:
    st.markdown(
        render_metric_tile("🌊 Maximum", f"{max_rainfall:.1f}", unit="mm"),
        unsafe_allow_html=True,
    )

with k5:
    st.markdown(
        render_metric_tile("🌧 Total", f"{total_rainfall:,.1f}", unit="mm"),
        unsafe_allow_html=True,
    )

st.divider()

# ==========================================================
# EXECUTIVE HIGHLIGHTS
# ==========================================================

st.markdown("### 📌 Executive Rainfall Highlights")

c1, c2, c3 = st.columns(3)

with c1:

    st.markdown(
        render_status_card(
            "🏆",
            "Highest Rainfall",
            highest_station["station"],
            f"{highest_station['rainfall_mm']:.1f} mm &nbsp;·&nbsp; "
            f"{highest_station['report_date'].strftime('%d %b %Y')}",
            dot_color="var(--ob-success)",
        ),
        unsafe_allow_html=True,
    )

with c2:

    st.markdown(
        render_status_card(
            "📅",
            "Latest Report",
            latest_date.strftime("%d %B %Y"),
            f"Stations Reporting : {station_count}",
            dot_color="var(--ob-info)",
        ),
        unsafe_allow_html=True,
    )

with c3:

    st.markdown(
        render_status_card(
            "🌦",
            "Rainfall Status",
            status,
            f"Average Rainfall : {avg_rainfall:.1f} mm",
            dot_color=_STATUS_DOT_MAP.get(status, "var(--ob-warning)"),
        ),
        unsafe_allow_html=True,
    )

st.divider()

# ==========================================================
# RAINFALL ANALYTICS
# ==========================================================

st.markdown("### 📊 Rainfall Analytics")

left, right = st.columns(2)

# ----------------------------------------------------------
# TOP RAINFALL STATIONS
# ----------------------------------------------------------

with left:

    station_summary = (
        filtered
        .groupby("station", as_index=False)["rainfall_mm"]
        .sum()
        .sort_values(
            "rainfall_mm",
            ascending=False,
        )
        .head(top_n)
    )

    fig = px.bar(
        station_summary,
        x="rainfall_mm",
        y="station",
        orientation="h",
        color="rainfall_mm",
        text="rainfall_mm",
        color_continuous_scale="Blues",
    )

    fig.update_traces(
        texttemplate="%{text:.1f} mm",
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Rainfall : %{x:.1f} mm<extra></extra>",
    )

    fig = style_fig(
        fig,
        title="🌧 Top Rainfall Stations",
        height=520,
        margin=dict(l=15, r=15, t=55, b=15),
        coloraxis_showscale=False,
        xaxis_title="Rainfall (mm)",
        yaxis_title="",
    )

    fig.update_yaxes(
        categoryorder="total ascending",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

# ----------------------------------------------------------
# DAILY RAINFALL TREND
# ----------------------------------------------------------

with right:

    trend = (
        filtered
        .groupby(
            "report_date",
            as_index=False,
        )["rainfall_mm"]
        .sum()
    )

    fig = px.area(
        trend,
        x="report_date",
        y="rainfall_mm",
        markers=True,
    )

    fig.update_traces(
        line=dict(width=3, color="#ffffff"),
        fillcolor="rgba(255,255,255,0.08)",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Rainfall : %{y:.1f} mm<extra></extra>",
    )

    fig = style_fig(
        fig,
        title="📈 Daily Rainfall Trend",
        height=520,
        margin=dict(l=15, r=15, t=55, b=15),
        xaxis_title="Date",
        yaxis_title="Rainfall (mm)",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

st.divider()

# ==========================================================
# RAINFALL DISTRIBUTION ANALYTICS
# ==========================================================

st.markdown("### 🌧 Rainfall Distribution & Intensity")

left, right = st.columns(2)

# ----------------------------------------------------------
# HISTOGRAM
# ----------------------------------------------------------

with left:

    fig = px.histogram(
        filtered,
        x="rainfall_mm",
        nbins=30,
        color_discrete_sequence=["#ffffff"],
    )

    fig.update_traces(
        hovertemplate="<b>Rainfall</b>: %{x:.1f} mm<br><b>Stations</b>: %{y}<extra></extra>",
    )

    fig = style_fig(
        fig,
        title="Rainfall Distribution",
        height=500,
        margin=dict(l=20, r=20, t=55, b=20),
        xaxis_title="Rainfall (mm)",
        yaxis_title="Number of Stations",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

# ----------------------------------------------------------
# DONUT CHART
# ----------------------------------------------------------

with right:

    category_df = filtered.copy()

    category_df["Intensity"] = pd.cut(

        category_df["rainfall_mm"],

        bins=[-1, 10, 25, 50, 1000],

        labels=[
            "Light",
            "Moderate",
            "Heavy",
            "Extreme",
        ],
    )

    summary = (

        category_df

        .groupby(
            "Intensity",
            observed=False,
        )

        .size()

        .reset_index(name="Stations")

    )

    fig = px.pie(

        summary,

        names="Intensity",

        values="Stations",

        hole=.65,

        color="Intensity",

        color_discrete_map={

            "Light": "#22c55e",

            "Moderate": "#f59e0b",

            "Heavy": "#f97316",

            "Extreme": "#ef4444",

        },

    )

    fig.update_traces(

        textposition="inside",

        textinfo="percent+label",

        hovertemplate="<b>%{label}</b><br>%{value} Stations<extra></extra>",

    )

    fig = style_fig(

        fig,

        title="Rainfall Intensity",

        height=500,

        margin=dict(l=20, r=20, t=55, b=20),

        legend_title="",

    )

    st.plotly_chart(

        fig,

        use_container_width=True,

    )

st.divider()

# ==========================================================
# MONTHLY RAINFALL & TOP STATIONS
# ==========================================================

left, right = st.columns(2)

# ----------------------------------------------------------
# MONTHLY RAINFALL TREND
# ----------------------------------------------------------

with left:

    monthly = filtered.copy()

    monthly["Month"] = (
        monthly["report_date"]
        .dt.to_period("M")
        .astype(str)
    )

    monthly_summary = (
        monthly
        .groupby(
            "Month",
            as_index=False,
        )["rainfall_mm"]
        .sum()
    )

    fig = px.line(
        monthly_summary,
        x="Month",
        y="rainfall_mm",
        markers=True,
    )

    fig.update_traces(
        line=dict(width=4, color="#ffffff"),
        marker=dict(size=8, color="#ffffff"),
        hovertemplate="<b>%{x}</b><br>Rainfall : %{y:.1f} mm<extra></extra>",
    )

    fig = style_fig(
        fig,
        title="📅 Monthly Rainfall Trend",
        height=500,
        margin=dict(l=20, r=20, t=55, b=20),
        xaxis_title="Month",
        yaxis_title="Rainfall (mm)",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

# ----------------------------------------------------------
# TOP 10 STATIONS
# ----------------------------------------------------------

with right:

    ranking = (
        filtered
        .groupby(
            "station",
            as_index=False,
        )["rainfall_mm"]
        .sum()
        .sort_values(
            "rainfall_mm",
            ascending=False,
        )
        .head(10)
    )

    ranking.index += 1

    ranking.rename(
        columns={
            "station": "Station",
            "rainfall_mm": "Rainfall (mm)",
        },
        inplace=True,
    )

    render_card_header("🏆", "Top 10 Rainfall Stations")

    st.dataframe(
        ranking,
        hide_index=False,
        use_container_width=True,
        height=430,
        column_config={
            "Station": st.column_config.TextColumn(
                width="medium",
            ),
            "Rainfall (mm)": st.column_config.NumberColumn(
                format="%.1f",
                width="small",
            ),
        },
    )

st.divider()

# ==========================================================
# EXECUTIVE SUMMARY
# ==========================================================

st.markdown("### 📌 Rainfall Executive Summary")

a, b, c = st.columns(3)

with a:
    st.markdown(
        render_metric_tile(
            "🌧 Total Rainfall",
            f"{filtered['rainfall_mm'].sum():,.1f}",
            unit="mm",
        ),
        unsafe_allow_html=True,
    )

with b:
    st.markdown(
        render_metric_tile(
            "📊 Average Rainfall",
            f"{filtered['rainfall_mm'].mean():.1f}",
            unit="mm",
        ),
        unsafe_allow_html=True,
    )

with c:
    st.markdown(
        render_metric_tile(
            "📍 Active Stations",
            f"{filtered['station'].nunique()}",
        ),
        unsafe_allow_html=True,
    )

st.divider()

# ==========================================================
# RAW DATASET
# ==========================================================

render_card_header("📋", "Latest Rainfall Records")

table = (
    filtered
    .sort_values(
        ["report_date", "rainfall_mm"],
        ascending=[False, False],
    )
    .copy()
)

display_columns = [
    "report_date",
    "station",
    "rainfall_mm",
]

display_columns = [
    c for c in display_columns
    if c in table.columns
]

st.dataframe(
    table[display_columns],
    hide_index=True,
    use_container_width=True,
    height=520,
    column_config={
        "report_date": st.column_config.DateColumn(
            "📅 Report Date",
            format="DD MMM YYYY",
            width="small",
        ),
        "station": st.column_config.TextColumn(
            "📍 Station",
            width="medium",
        ),
        "rainfall_mm": st.column_config.NumberColumn(
            "🌧 Rainfall (mm)",
            format="%.1f",
            width="small",
        ),
    },
)

st.divider()

# ==========================================================
# DOWNLOAD SECTION
# ==========================================================

left, right = st.columns([3, 1])

with left:

    st.markdown(
        render_status_card(
            "📥",
            "Dataset Information",
            f"{len(table):,} Records",
            f"Reporting Stations : {table['station'].nunique()} &nbsp;·&nbsp; "
            f"Latest Report : {table['report_date'].max().strftime('%d %b %Y')}<br>"
            f"The exported CSV contains the currently filtered rainfall observations.",
            dot_color="var(--ob-info)",
        ),
        unsafe_allow_html=True,
    )

with right:

    st.write("")
    st.write("")

    st.download_button(
        label="⬇ Download CSV",
        data=table.to_csv(index=False).encode("utf-8"),
        file_name="pdma_rainfall.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.divider()

# ==========================================================
# FOOTER
# ==========================================================

st.markdown(
    """
<div style="text-align:center; color:var(--ob-text-dim); font-size:11.5px; font-family:var(--ob-font-body); padding-top:4px; line-height:1.7;">
<b style="color:var(--ob-text-muted);">Source:</b> Provincial Disaster Management Authority (PDMA) Punjab<br>
Dashboard refreshes automatically after each ETL/Airflow pipeline execution.<br>
Designed for Operational Risk Monitoring, Disaster Analytics and Executive Decision Support.
</div>
""",
    unsafe_allow_html=True,
)