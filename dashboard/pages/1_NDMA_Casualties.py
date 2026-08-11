"""
dashboard/pages/1_NDMA_Casualties.py

NDMA Casualties — Business Intelligence Dashboard.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent.parent)
)

from dashboard.db import get_casualties


# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="NDMA Casualties",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================================
# COMMAND SURFACE DESIGN SYSTEM (CSS) -- unchanged theme,
# extended with responsive rules at the bottom of this block.
# ==========================================================

st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>

:root{

    --cs-bg: #121413;
    --cs-bg-lowest: #0d0e0e;
    --cs-surface: #1e2020;
    --cs-surface-high: #292a2a;

    --cs-on-surface: #e3e2e1;
    --cs-on-surface-variant: #c4c6cd;

    --cs-outline: #8e9197;
    --cs-outline-variant: #44474d;

    --cs-primary: #b5c8e5;
    --cs-primary-container: #0d2137;

    --cs-success: #79dd68;
    --cs-success-container: #007406;
    --cs-on-success-container: #92f87f;

    --cs-warning: #ffb5a0;
    --cs-warning-container: #430c00;
    --cs-on-warning-container: #f34e19;

    --cs-danger: #ffb4ab;
    --cs-danger-container: #93000a;
    --cs-on-danger-container: #ffdad6;

    --cs-radius: 4px;
    --cs-radius-lg: 8px;
    --cs-radius-pill: 999px;

    --cs-space-1: 4px;
    --cs-space-2: 8px;
    --cs-space-3: 12px;
    --cs-space-4: 16px;
    --cs-space-6: 24px;

    --cs-font-sans: 'Inter', 'Segoe UI', sans-serif;
    --cs-font-mono: 'JetBrains Mono', ui-monospace, monospace;

}

html, body, [class*="css"]{
    font-family: var(--cs-font-sans);
}

.main .block-container{
    max-width: 1600px;
    padding-top: var(--cs-space-3);
    padding-bottom: var(--cs-space-4);
}

#MainMenu{ visibility: hidden; }
footer{ visibility: hidden; }
header{ visibility: hidden; }

hr{
    margin-top: var(--cs-space-2) !important;
    margin-bottom: var(--cs-space-2) !important;
    border-color: var(--cs-outline-variant) !important;
    opacity: .5 !important;
}

/* ---------------------------------------------------------
   HEADER
   --------------------------------------------------------- */

.ndma-header{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--cs-space-4);
    flex-wrap: wrap;
}

.ndma-title-block{ display: flex; align-items: center; gap: var(--cs-space-3); }
.ndma-title-icon{ font-size: 26px; line-height: 1; }

.ndma-main-title{
    font-family: var(--cs-font-mono);
    font-size: 22px;
    font-weight: 700;
    letter-spacing: .01em;
    color: var(--cs-on-surface);
    margin: 0;
}

.ndma-subtitle{
    font-size: 12.5px;
    color: var(--cs-on-surface-variant);
    margin-top: 2px;
}

.ndma-live-badge{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: var(--cs-radius-pill);
    background: var(--cs-success-container);
    color: var(--cs-on-success-container);
    font-family: var(--cs-font-mono);
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
}

.ndma-live-badge .dot{
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--cs-success);
    box-shadow: 0 0 0 0 rgba(121,221,104,.5);
    animation: ndma-pulse 1.8s infinite;
}

@keyframes ndma-pulse{
    0%   { box-shadow: 0 0 0 0 rgba(121,221,104,.5); }
    70%  { box-shadow: 0 0 0 7px rgba(121,221,104,0); }
    100% { box-shadow: 0 0 0 0 rgba(121,221,104,0); }
}

/* ---------------------------------------------------------
   FILTER SUMMARY STRIP
   --------------------------------------------------------- */

.filter-strip{
    display: flex;
    align-items: center;
    gap: var(--cs-space-6);
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-left: 3px solid var(--cs-primary);
    border-radius: var(--cs-radius);
    padding: var(--cs-space-2) var(--cs-space-4);
    font-size: 12.5px;
    color: var(--cs-on-surface-variant);
    flex-wrap: wrap;
}

.filter-strip b{ color: var(--cs-on-surface); font-family: var(--cs-font-mono); }

/* ---------------------------------------------------------
   KPI TILES (equal height)
   --------------------------------------------------------- */

.tile{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius);
    padding: var(--cs-space-3) var(--cs-space-4);
    height: 92px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
    transition: transform .18s ease, background .18s ease;
}

.tile:hover{ transform: translateY(-2px); background: var(--cs-surface-high); }

.tile-label{
    font-family: var(--cs-font-mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
}

.tile-value{
    font-family: var(--cs-font-mono);
    font-size: 21px;
    font-weight: 700;
    color: var(--cs-on-surface);
    line-height: 1.1;
}

.tile-value.danger{ color: var(--cs-danger); }
.tile-value.warning{ color: var(--cs-warning); }
.tile-value.success{ color: var(--cs-success); }

/* ---------------------------------------------------------
   CHART CONTAINERS
   --------------------------------------------------------- */

.chart-tile-header{
    font-family: var(--cs-font-mono);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    padding: 2px 4px 8px 4px;
}

.chart-tile-header.primary{ font-size: 13.5px; color: var(--cs-on-surface); }
.chart-tile-header.secondary{ font-size: 11px; opacity: .85; }

div[data-testid="stPlotlyChart"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: var(--cs-space-3);
}

/* ---------------------------------------------------------
   TABLES (sticky header, compact)
   --------------------------------------------------------- */

.table-tile-header{
    font-family: var(--cs-font-mono);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    background: var(--cs-surface-high);
    border: 1px solid var(--cs-outline-variant);
    border-bottom: none;
    border-radius: var(--cs-radius-lg) var(--cs-radius-lg) 0 0;
    padding: 9px var(--cs-space-4);
}

div[data-testid="stDataFrame"]{
    border: 1px solid var(--cs-outline-variant);
    border-top: none;
    border-radius: 0 0 var(--cs-radius-lg) var(--cs-radius-lg);
    overflow: hidden;
}

div[data-testid="stDataFrame"] table{
    font-family: var(--cs-font-mono);
    font-size: 12.5px;
}

div[data-testid="stDataFrame"] thead tr th{
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--cs-surface-high) !important;
}

/* ---------------------------------------------------------
   EXPORT / SUMMARY CARD
   --------------------------------------------------------- */

.export-card-header{
    font-family: var(--cs-font-mono);
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    margin-bottom: var(--cs-space-2);
}

/* ---------------------------------------------------------
   SIDEBAR
   --------------------------------------------------------- */

section[data-testid="stSidebar"]{
    background: var(--cs-bg-lowest);
    border-right: 1px solid var(--cs-outline-variant);
}

section[data-testid="stSidebar"] *{
    color: var(--cs-on-surface) !important;
}

section[data-testid="stSidebar"] .block-container{
    padding-top: var(--cs-space-4);
    padding-left: var(--cs-space-3);
    padding-right: var(--cs-space-3);
}

section[data-testid="stSidebar"] h1{
    font-family: var(--cs-font-mono);
    font-size: 14px;
    letter-spacing: .04em;
}

section[data-testid="stSidebar"] h2{
    font-family: var(--cs-font-mono);
    font-size: 11.5px;
    letter-spacing: .06em;
    text-transform: uppercase;
    opacity: .8;
    margin-top: var(--cs-space-2);
}

section[data-testid="stSidebar"] label{
    font-size: 12.5px !important;
}

section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div{
    border-radius: var(--cs-radius) !important;
    background: var(--cs-surface) !important;
    border-color: var(--cs-outline-variant) !important;
}

section[data-testid="stSidebar"] div[data-testid="stMetric"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius);
    padding: var(--cs-space-2) var(--cs-space-3);
    margin-bottom: 4px;
}

/* ---------------------------------------------------------
   NATIVE ELEMENT OVERRIDES
   --------------------------------------------------------- */

div[data-testid="stMetric"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius);
    padding: var(--cs-space-2) var(--cs-space-3);
}

div[data-testid="stMetric"] label{ color: var(--cs-on-surface-variant) !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"]{ color: var(--cs-on-surface) !important; }

div[data-testid="stAlert"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: var(--cs-space-2) var(--cs-space-4);
}

.stButton > button, .stDownloadButton > button{
    border-radius: var(--cs-radius);
    font-family: var(--cs-font-mono);
    font-weight: 600;
    letter-spacing: .03em;
    text-transform: uppercase;
    font-size: 12px;
}

.stExpander{
    border: 1px solid var(--cs-outline-variant) !important;
    border-radius: var(--cs-radius-lg) !important;
    background: var(--cs-surface) !important;
}

/* ==========================================================
   MODERN STREAMLIT DATAFRAME UI
========================================================== */

/* Outer Card */

div[data-testid="stDataFrame"]{
    border:1px solid #404040 !important;
    border-radius:12px !important;
    overflow:hidden !important;
    background:#17181c !important;
    margin-top:2px !important;
    margin-bottom:8px !important;
    box-shadow:0 3px 10px rgba(0,0,0,.25);
}

/* Header Row */

div[data-testid="stDataFrame"] [role="columnheader"]{
    background:#23262f !important;
    color:#ffffff !important;
    font-weight:700 !important;
    font-size:13px !important;
    border-bottom:1px solid #454545 !important;
}

/* Body Cells */

div[data-testid="stDataFrame"] [role="gridcell"]{
    font-size:13px !important;
    color:#ECECEC !important;
    border-bottom:1px solid rgba(255,255,255,.05) !important;
}

/* Hover */

div[data-testid="stDataFrame"] [role="row"]:hover{
    background:#2a3343 !important;
}

/* Remove gap */

.table-tile-header{
    margin-bottom:0px !important;
    padding:10px 14px !important;
}

div[data-testid="stDataFrame"]{
    margin-top:-2px !important;
}

/* ---------------------------------------------------------
   COMPACT FOOTER
   --------------------------------------------------------- */

.ndma-footer{
    text-align: center;
    font-size: 11.5px;
    color: var(--cs-on-surface-variant);
    padding: var(--cs-space-2) 0 0 0;
    line-height: 1.6;
}

.ndma-footer b{ color: var(--cs-on-surface); }

/* ---------------------------------------------------------
   RESPONSIVE (base rules, unchanged)
   --------------------------------------------------------- */

@media (max-width: 1400px){
    .main .block-container{ padding-left: var(--cs-space-4); padding-right: var(--cs-space-4); }
}

@media (max-width: 1024px){
    .ndma-main-title{ font-size: 18px; }
    .ndma-header{ flex-direction: column; align-items: flex-start; }
    .tile{ height: auto; min-height: 84px; }
}

/* ---------------------------------------------------------
   RESPONSIVE -- EXTENDED (desktop / laptop / tablet / mobile)
   Only additive: no rule above this point was changed. These
   rules exist purely to prevent horizontal overflow and stack
   layout on narrower screens; the desktop multi-column layout
   above 900px is completely untouched.
   --------------------------------------------------------- */

html, body{
    overflow-x: hidden !important;
}

.main .block-container{
    overflow-x: hidden;
}

div[data-testid="stPlotlyChart"],
div[data-testid="stDataFrame"],
img{
    max-width: 100% !important;
}

.ndma-main-title,
.ndma-subtitle,
.chart-tile-header,
.table-tile-header,
.tile-value{
    overflow-wrap: break-word;
    word-break: break-word;
}

/* Tablet: stack any 2/3/4/6-column row into a single column,
   keep spacing sane, keep tiles/cards full width. */
@media (max-width: 900px){

    .main .block-container{
        padding-left: var(--cs-space-3);
        padding-right: var(--cs-space-3);
    }

    div[data-testid="stHorizontalBlock"]{
        flex-direction: column !important;
    }

    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]{
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 0 !important;
    }

    .filter-strip{
        gap: var(--cs-space-3);
    }
}

/* Mobile: tighten padding further, force inputs/buttons full width
   so the sidebar and export controls never overflow the viewport. */
@media (max-width: 560px){

    .main .block-container{
        padding-left: var(--cs-space-2);
        padding-right: var(--cs-space-2);
        padding-top: var(--cs-space-2);
    }

    .ndma-main-title{ font-size: 16px; }
    .ndma-title-icon{ font-size: 20px; }
    .ndma-subtitle{ font-size: 11px; }

    .tile{
        height: auto;
        min-height: 76px;
        padding: var(--cs-space-2) var(--cs-space-3);
    }

    .tile-value{ font-size: 18px; }

    div[data-testid="stPlotlyChart"]{
        padding: var(--cs-space-2);
    }

    section[data-testid="stSidebar"]{
        min-width: 0 !important;
        max-width: 92vw !important;
    }

    section[data-testid="stSidebar"] .stSelectbox,
    section[data-testid="stSidebar"] .stDateInput,
    section[data-testid="stSidebar"] .stTextInput,
    section[data-testid="stSidebar"] .stButton,
    section[data-testid="stSidebar"] .stDownloadButton{
        width: 100% !important;
    }

    .stButton > button,
    .stDownloadButton > button{
        width: 100% !important;
        white-space: normal !important;
    }

    .filter-strip{
        flex-direction: column;
        align-items: flex-start;
        gap: var(--cs-space-2);
    }
}

</style>
""",
    unsafe_allow_html=True,
)

# ==========================================================
# PAGE HEADER (unchanged)
# ==========================================================

st.markdown(
    """
<div class="ndma-header">

  <div class="ndma-title-block">
    <div class="ndma-title-icon">🚨</div>
    <div>
      <div class="ndma-main-title">NDMA CASUALTIES INTELLIGENCE</div>
      <div class="ndma-subtitle">Pakistan Operational Risk Intelligence Platform</div>
    </div>
  </div>

  <div class="ndma-live-badge"><span class="dot"></span> Live Dashboard</div>

</div>
""",
    unsafe_allow_html=True,
)

st.divider()

# ==========================================================
# LOAD DATABASE -- EXACTLY ONE QUERY FOR THE ENTIRE PAGE
# ==========================================================

try:

    raw_df = get_casualties()

except Exception as e:

    st.error(f"❌ Database Connection Error\n\n{e}")

    st.stop()

if raw_df.empty:

    st.warning("No NDMA casualty records available.")

    st.stop()

# ==========================================================
# DATA PREPARATION (runs once, on the single loaded dataframe)
# ==========================================================

raw_df = raw_df.copy()

raw_df["report_date"] = pd.to_datetime(
    raw_df["report_date"],
    errors="coerce",
)

raw_df["deaths"] = (
    pd.to_numeric(raw_df["deaths"], errors="coerce")
    .fillna(0)
    .astype(int)
)

raw_df["injured"] = (
    pd.to_numeric(raw_df["injured"], errors="coerce")
    .fillna(0)
    .astype(int)
)

raw_df["province"] = (
    raw_df["province"]
    .fillna("Unknown")
    .astype(str)
    .str.strip()
)

raw_df = raw_df.dropna(subset=["report_date"])

raw_df = raw_df.sort_values("report_date").reset_index(drop=True)

MIN_DATE = raw_df["report_date"].min().date()
MAX_DATE = raw_df["report_date"].max().date()
ALL_PROVINCES = sorted(raw_df["province"].dropna().unique())

AGGREGATION_PERIODS = {
    "Hourly": "H",
    "Daily": "D",
    "Weekly": "W",
    "Monthly": "M",
    "Yearly": "Y",
}

# ==========================================================
# SIDEBAR -- FILTERS (Start Date, End Date, Province,
# Aggregation, Export) -- no other controls
# ==========================================================

st.sidebar.markdown(
    """
# 🎛 Dashboard Filters

Filter and aggregate NDMA casualty data.
"""
)

start_date = st.sidebar.date_input(
    "📅 Start Date",
    value=MIN_DATE,
    min_value=MIN_DATE,
    max_value=MAX_DATE,
)

end_date = st.sidebar.date_input(
    "📅 End Date",
    value=MAX_DATE,
    min_value=MIN_DATE,
    max_value=MAX_DATE,
)

if start_date > end_date:
    st.sidebar.error("Start Date must be on or before End Date.")
    st.stop()

selected_provinces = st.sidebar.selectbox(
    "📍 Province",
    options=["All"] + ALL_PROVINCES,
)

aggregation_label = st.sidebar.selectbox(
    "⏱ Aggregation",
    options=list(AGGREGATION_PERIODS.keys()),
    index=1,
)

st.sidebar.caption(
    "Note: report_date is a date-only field in the source database "
    "(no time-of-day component), so **Hourly** aggregation renders "
    "identically to **Daily**."
)

st.sidebar.divider()

st.sidebar.markdown("## 📥 Export")

export_col1, export_col2 = st.sidebar.columns(2)

# ==========================================================
# BUILD filtered_df -- THE ONLY DATAFRAME EVERY KPI, CHART,
# TABLE, HEATMAP, TREEMAP AND RANKING BELOW READS FROM
# ==========================================================

filtered_df = raw_df[
    (raw_df["report_date"].dt.date >= start_date)
    &
    (raw_df["report_date"].dt.date <= end_date)
]

if selected_provinces != "All":
    filtered_df = filtered_df[
        filtered_df["province"] == selected_provinces
    ]

filtered_df = filtered_df.copy()

if filtered_df.empty:

    st.warning("No records found for the selected filters.")

    st.stop()

period_freq = AGGREGATION_PERIODS[aggregation_label]

filtered_df["period"] = (
    filtered_df["report_date"]
    .dt.to_period(period_freq)
    .dt.to_timestamp()
)

# ---- sidebar export buttons (operate on filtered_df only) ----

with export_col1:

    st.download_button(
        "⬇ CSV",
        filtered_df.drop(columns=["period"]).to_csv(index=False).encode("utf-8"),
        file_name="ndma_casualties_filtered.csv",
        mime="text/csv",
        use_container_width=True,
    )

with export_col2:

    import io

    excel_buffer = io.BytesIO()

    filtered_df.drop(columns=["period"]).to_excel(
        excel_buffer,
        index=False,
    )

    st.download_button(
        "⬇ Excel",
        excel_buffer.getvalue(),
        file_name="ndma_casualties_filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ==========================================================
# EXECUTIVE FILTER SUMMARY
# ==========================================================

st.markdown(
    f"""
<div class="filter-strip">
  <span>🎯 <b>{filtered_df['province'].nunique()}</b> Province(s)</span>
  <span>📄 <b>{len(filtered_df):,}</b> Records</span>
  <span>📅 <b>{start_date.strftime('%d %b %Y')}</b> → <b>{end_date.strftime('%d %b %Y')}</b></span>
  <span>⏱ Aggregation : <b>{aggregation_label}</b></span>
</div>
""",
    unsafe_allow_html=True,
)

st.divider()

# ==========================================================
# KPIs -- all computed from filtered_df only
# ==========================================================

total_deaths = int(filtered_df["deaths"].sum())

total_injured = int(filtered_df["injured"].sum())

affected_provinces = filtered_df["province"].nunique()

reports_count = len(filtered_df)

fatality_rate = round(
    (total_deaths / max(total_deaths + total_injured, 1)) * 100,
    2,
)

latest_report = filtered_df["report_date"].max()

k1, k2, k3, k4, k5, k6 = st.columns(6)

with k1:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">💀 Total Deaths</div>
  <div class="tile-value danger">{total_deaths:,}</div>
</div>
""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">🤕 Total Injured</div>
  <div class="tile-value warning">{total_injured:,}</div>
</div>
""", unsafe_allow_html=True)

with k3:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">🗺 Affected Provinces</div>
  <div class="tile-value">{affected_provinces}</div>
</div>
""", unsafe_allow_html=True)

with k4:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">📄 Reports Count</div>
  <div class="tile-value">{reports_count:,}</div>
</div>
""", unsafe_allow_html=True)

with k5:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">⚠ Fatality Rate</div>
  <div class="tile-value">{fatality_rate}%</div>
</div>
""", unsafe_allow_html=True)

with k6:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">🕒 Latest Report</div>
  <div class="tile-value success">{latest_report.strftime('%d %b %Y')}</div>
</div>
""", unsafe_allow_html=True)

st.divider()
# ==========================================================

# ==========================================================
# DERIVED AGGREGATES -- computed once, reused by every chart
# and table below (no per-chart re-filtering / re-querying)
# ==========================================================

province_summary = (
    filtered_df
    .groupby("province", as_index=False)[["deaths", "injured"]]
    .sum()
    .sort_values("deaths", ascending=False)
    .reset_index(drop=True)
)

province_summary["total_casualties"] = (
    province_summary["deaths"] + province_summary["injured"]
)

_total_deaths_all = province_summary["deaths"].sum()
_total_casualties_all = province_summary["total_casualties"].sum()

province_summary["death_share_pct"] = (
    (province_summary["deaths"] / _total_deaths_all * 100).round(1)
    if _total_deaths_all > 0 else 0.0
)

province_summary["casualty_share_pct"] = (
    (province_summary["total_casualties"] / _total_casualties_all * 100).round(1)
    if _total_casualties_all > 0 else 0.0
)

_has_provinces = not province_summary.empty

# ---- weekly matrix (Chart G is explicitly province-vs-WEEK,
# independent of whatever the sidebar Aggregation control is
# currently set to -- this is a dedicated derived view, not a
# change to the aggregation filter itself) ----

_weekly_df = filtered_df.copy()
_weekly_df["week_start"] = _weekly_df["report_date"].dt.to_period("W").dt.start_time

province_week_matrix = (
    _weekly_df
    .pivot_table(
        index="province",
        columns="week_start",
        values="deaths",
        aggfunc="sum",
        fill_value=0,
    )
)

province_week_matrix.columns = [
    f"Wk of {c.strftime('%d %b')}" for c in province_week_matrix.columns
]

# ---- shared chart theming (kept consistent with the page's
# existing dark Plotly styling) ----

_CHART_BAR_COLOR = "#b5c8e5"
_CHART_LINE_COLOR = "#ffb4ab"
_CHART_FONT = dict(family="Inter, sans-serif", size=12, color="#c4c6cd")


def _base_layout(fig, title, height=440):
    """Shared Plotly theme -- visual styling only, never touches
    trace data or aggregation logic."""

    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")
    return fig


# ==========================================================
# MONTHLY SUMMARY CARD (I)
# Reuses the KPI values already computed above (total_deaths,
# total_injured, reports_count) -- no recomputation, no new query.
# ==========================================================

st.markdown('<div class="chart-tile-header primary">🏛 Province Performance Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="chart-tile-header secondary">'
    f'Reporting window: {start_date.strftime("%d %b %Y")} → {end_date.strftime("%d %b %Y")}'
    f'</div>',
    unsafe_allow_html=True,
)

_avg_deaths_per_report = round(total_deaths / reports_count, 2) if reports_count else 0.0

ms1, ms2, ms3, ms4 = st.columns(4)

with ms1:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">💀 Total Deaths</div>
  <div class="tile-value danger">{total_deaths:,}</div>
</div>
""", unsafe_allow_html=True)

with ms2:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">🤕 Total Injured</div>
  <div class="tile-value warning">{total_injured:,}</div>
</div>
""", unsafe_allow_html=True)

with ms3:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">📄 Reports</div>
  <div class="tile-value">{reports_count:,}</div>
</div>
""", unsafe_allow_html=True)

with ms4:
    st.markdown(f"""
<div class="tile">
  <div class="tile-label">📊 Avg Deaths / Report</div>
  <div class="tile-value">{_avg_deaths_per_report}</div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ==========================================================
# A. DEATHS & INJURED TREND -- Combo Chart (Bar + Bar + Line)
# Auto-selects Monthly vs Weekly granularity from filtered_df only.
# Requires: from plotly.subplots import make_subplots  (add this
# import alongside the existing `import plotly.graph_objects as go`
# at the top of the file -- no other imports change).
# ==========================================================

_distinct_months = filtered_df["report_date"].dt.to_period("M").nunique()

_TREND_BAR_DEATHS = "#ffb4ab"
_TREND_BAR_INJURED = "#b5c8e5"
_TREND_LINE_REPORTS = "#79dd68"
_TREND_LINE_FATALITY = "#f34e19"

if _distinct_months >= 6:

    # ---- MONTHLY: only calendar months actually present in the
    # data, in chronological order -- nothing fabricated. ----

    _trend_key = filtered_df["report_date"].dt.to_period("M")

    _trend_grouped = (
        filtered_df
        .assign(_bucket=_trend_key)
        .groupby("_bucket")
        .agg(
            deaths=("deaths", "sum"),
            injured=("injured", "sum"),
            reports=("deaths", "count"),
        )
        .reset_index()
        .sort_values("_bucket")
    )

    _trend_grouped["label"] = _trend_grouped["_bucket"].dt.strftime("%b")

    _trend_title = "Deaths & Injured Trend (Monthly)"
    _trend_xaxis_title = "Month"

else:

    # ---- WEEKLY: real week-start dates present in the data only. ----

    _trend_key = filtered_df["report_date"].dt.to_period("W").dt.start_time

    _trend_grouped = (
        filtered_df
        .assign(_bucket=_trend_key)
        .groupby("_bucket")
        .agg(
            deaths=("deaths", "sum"),
            injured=("injured", "sum"),
            reports=("deaths", "count"),
        )
        .reset_index()
        .sort_values("_bucket")
    )

    _trend_grouped["label"] = "Wk " + _trend_grouped["_bucket"].dt.strftime("%d %b")

    _trend_title = "Deaths & Injured Trend (Weekly)"
    _trend_xaxis_title = "Week"

_trend_grouped["fatality_rate"] = (
    _trend_grouped["deaths"]
    / (_trend_grouped["deaths"] + _trend_grouped["injured"]).replace(0, 1)
    * 100
).round(1)

st.markdown(f'<div class="chart-tile-header primary">📈 {_trend_title}</div>', unsafe_allow_html=True)

if _trend_grouped.empty:

    st.info("No data available for the current filters.")

else:

    from plotly.subplots import make_subplots

    fig_trend = make_subplots(specs=[[{"secondary_y": True}]])

    fig_trend.add_trace(
        go.Bar(
            x=_trend_grouped["label"],
            y=_trend_grouped["deaths"],
            name="Deaths",
            marker_color=_TREND_BAR_DEATHS,
            hovertemplate="<b>%{x}</b><br>Deaths: %{y}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig_trend.add_trace(
        go.Bar(
            x=_trend_grouped["label"],
            y=_trend_grouped["injured"],
            name="Injured",
            marker_color=_TREND_BAR_INJURED,
            hovertemplate="<b>%{x}</b><br>Injured: %{y}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig_trend.add_trace(
        go.Scatter(
            x=_trend_grouped["label"],
            y=_trend_grouped["reports"],
            name="Reports",
            mode="lines+markers",
            line=dict(color=_TREND_LINE_REPORTS, width=3),
            marker=dict(size=7),
            hovertemplate="<b>%{x}</b><br>Reports: %{y}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig_trend.add_trace(
        go.Scatter(
            x=_trend_grouped["label"],
            y=_trend_grouped["fatality_rate"],
            name="Fatality Rate (%)",
            mode="lines+markers",
            line=dict(color=_TREND_LINE_FATALITY, width=2, dash="dash"),
            marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>Fatality Rate: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )

    fig_trend.update_layout(
        barmode="group",
        template="plotly_dark",
        height=440,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        margin=dict(l=10, r=10, t=50, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )

    fig_trend.update_xaxes(
        title_text=_trend_xaxis_title,
        gridcolor="rgba(255,255,255,0.06)",
    )

    fig_trend.update_yaxes(
        title_text="People",
        gridcolor="rgba(255,255,255,0.06)",
        secondary_y=False,
    )

    fig_trend.update_yaxes(
        title_text="Reports / Fatality Rate (%)",
        showgrid=False,
        secondary_y=True,
    )

    st.plotly_chart(fig_trend, use_container_width=True)

st.divider()

# ==========================================================
# B. GROUPED BAR -- Deaths vs Injured by province
# C. DONUT CHART -- Province contribution to total casualties
# ==========================================================

bc_left, bc_right = st.columns(2)

with bc_left:

    st.markdown('<div class="chart-tile-header primary">⚖ Deaths vs Injured by Province</div>', unsafe_allow_html=True)

    if not _has_provinces:
        st.info("No province data for the current filters.")
    else:
        fig_grouped = go.Figure()

        fig_grouped.add_trace(go.Bar(
            x=province_summary["province"], y=province_summary["deaths"],
            name="Deaths", marker_color=_CHART_LINE_COLOR,
        ))
        fig_grouped.add_trace(go.Bar(
            x=province_summary["province"], y=province_summary["injured"],
            name="Injured", marker_color=_CHART_BAR_COLOR,
        ))
        fig_grouped.update_layout(
            barmode="group",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )

        st.plotly_chart(_base_layout(fig_grouped, "", height=420), use_container_width=True)

with bc_right:

    st.markdown('<div class="chart-tile-header primary">📐 Province Contribution to Total Casualties</div>', unsafe_allow_html=True)

    if not _has_provinces or _total_casualties_all <= 0:

        st.info("No casualty data available for the current filters.")

    else:

        # ---- Deterministic color palette assembled only from colors
        # already used elsewhere on this page (--cs-* design tokens
        # and the _CHART_BAR_COLOR / _CHART_LINE_COLOR constants
        # defined above) -- no random/new hues introduced. No existing
        # explicit province->color mapping was found anywhere in the
        # file, so this is applied only to this donut chart. ----

        _DONUT_COLORS = [
            "#b5c8e5",  # --cs-primary            (= _CHART_BAR_COLOR)
            "#79dd68",  # --cs-success
            "#ffb4ab",  # --cs-danger              (= _CHART_LINE_COLOR)
            "#ffb5a0",  # --cs-warning
            "#92f87f",  # --cs-on-success-container
            "#f34e19",  # --cs-on-warning-container
            "#ffdad6",  # --cs-on-danger-container
            "#8e9197",  # --cs-outline (neutral fallback)
        ]

        donut_df = (
            province_summary
            .sort_values("total_casualties", ascending=False)
            .reset_index(drop=True)
        )

        donut_colors = [
            _DONUT_COLORS[i % len(_DONUT_COLORS)]
            for i in range(len(donut_df))
        ]

        fig_donut = go.Figure(
            data=[
                go.Pie(
                    labels=donut_df["province"],
                    values=donut_df["total_casualties"],
                    hole=0.58,
                    sort=False,
                    marker=dict(
                        colors=donut_colors,
                        line=dict(color="#121413", width=2),
                    ),
                    textinfo="percent",
                    texttemplate="%{percent:.1%}",
                    textposition="inside",
                    insidetextorientation="radial",
                    customdata=list(zip(
                        donut_df["deaths"],
                        donut_df["injured"],
                        donut_df["casualty_share_pct"],
                    )),
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        "Casualties: %{value:,}<br>"
                        "Deaths: %{customdata[0]:,} · Injured: %{customdata[1]:,}<br>"
                        "Contribution: %{customdata[2]:.1f}%"
                        "<extra></extra>"
                    ),
                )
            ]
        )

        fig_donut.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=_CHART_FONT,
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.15,
                xanchor="center",
                x=0.5,
            ),
            annotations=[
                dict(
                    text=f"TOTAL<br><b>{int(_total_casualties_all):,}</b>",
                    x=0.5,
                    y=0.5,
                    font=dict(size=16, color="#e3e2e1", family="Inter, sans-serif"),
                    showarrow=False,
                )
            ],
        )

        st.plotly_chart(fig_donut, use_container_width=True)

st.divider()

# ==========================================================
# D. BUBBLE CHART -- x=deaths, y=injured, size=total casualties,
#    color=province
# E. SCATTER PLOT -- Deaths vs Injured with province labels
# ==========================================================

de_left, de_right = st.columns(2)

with de_left:

    st.markdown('<div class="chart-tile-header primary">🫧 Deaths vs Injured (Bubble = Total Casualties)</div>', unsafe_allow_html=True)

    if not _has_provinces:
        st.info("No province data for the current filters.")
    else:
        fig_bubble = px.scatter(
            province_summary,
            x="deaths",
            y="injured",
            size="total_casualties",
            color="province",
            size_max=55,
        )
        fig_bubble.update_traces(marker=dict(line=dict(width=1, color="rgba(255,255,255,0.3)")))
        fig_bubble.update_layout(xaxis_title="Deaths", yaxis_title="Injured")

        st.plotly_chart(_base_layout(fig_bubble, "", height=440), use_container_width=True)

with de_right:

    st.markdown('<div class="chart-tile-header primary">🔎 Deaths vs Injured (Labeled)</div>', unsafe_allow_html=True)

    if not _has_provinces:
        st.info("No province data for the current filters.")
    else:
        fig_scatter = px.scatter(
            province_summary,
            x="deaths",
            y="injured",
            text="province",
            color="province",
        )
        fig_scatter.update_traces(
            textposition="top center",
            marker=dict(size=12, line=dict(width=1, color="rgba(255,255,255,0.3)")),
        )
        fig_scatter.update_layout(xaxis_title="Deaths", yaxis_title="Injured", showlegend=False)

        st.plotly_chart(_base_layout(fig_scatter, "", height=440), use_container_width=True)

st.divider()

# ==========================================================
# F. TREEMAP -- Deaths by Province
# G. HEATMAP -- Province vs Week
# ==========================================================

fg_left, fg_right = st.columns(2)

# ----------------------------------------------------------
# F. DEATHS BY PROVINCE (HORIZONTAL BAR CHART)
# ----------------------------------------------------------

with fg_left:

    st.markdown(
        '<div class="chart-tile-header primary">📊 Deaths by Province</div>',
        unsafe_allow_html=True,
    )

    if not _has_provinces:

        st.info("No province data for the current filters.")

    else:

        province_rank = (
            province_summary
            .sort_values("deaths", ascending=True)
        )

        fig_rank = px.bar(
            province_rank,
            x="deaths",
            y="province",
            orientation="h",
            color="deaths",
            text="deaths",
            color_continuous_scale="Reds",
        )

        fig_rank.update_traces(
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Deaths: %{x}<extra></extra>",
        )

        fig_rank.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            coloraxis_showscale=False,
            xaxis_title="Deaths",
            yaxis_title="",
            margin=dict(l=10, r=20, t=10, b=10),
        )

        st.plotly_chart(
            fig_rank,
            use_container_width=True,
        )

# ----------------------------------------------------------
# G. WEEKLY TREND BY PROVINCE
# ----------------------------------------------------------

with fg_right:

    st.markdown(
        '<div class="chart-tile-header primary">📈 Weekly Death Trend by Province</div>',
        unsafe_allow_html=True,
    )

    weekly = (
        filtered_df
        .assign(
            week=filtered_df["report_date"]
            .dt.to_period("W")
            .dt.start_time
        )
        .groupby(["week", "province"], as_index=False)["deaths"]
        .sum()
    )

    if weekly.empty:

        st.info("No data available for the selected filters.")

    else:

        fig_week = px.line(
            weekly,
            x="week",
            y="deaths",
            color="province",
            markers=True,
        )

        fig_week.update_traces(
            line=dict(width=3),
            marker=dict(size=8),
        )

        fig_week.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend_title="Province",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
            ),
            xaxis_title="Week",
            yaxis_title="Deaths",
            hovermode="x unified",
            margin=dict(l=10, r=10, t=10, b=10),
        )

        st.plotly_chart(
            fig_week,
            use_container_width=True,
        )

st.divider()
# ==========================================================
# H. TOP 10 MOST SEVERE INCIDENTS (sorted by deaths descending)
# ==========================================================

st.markdown('<div class="table-tile-header">🚨 Top 10 Most Severe Incidents</div>', unsafe_allow_html=True)

severe_incidents = (
    filtered_df
    .drop(columns=["period"])
    .sort_values("deaths", ascending=False)
    .head(10)
    .reset_index(drop=True)
)

if severe_incidents.empty:
    st.info("No incidents recorded for the current filters.")
else:
    severe_incidents.insert(0, "Rank", range(1, len(severe_incidents) + 1))

    st.dataframe(
    severe_incidents,
    hide_index=True,
    use_container_width=True,
    height=300,
    column_config={
        "report_date": st.column_config.DateColumn(
            "Report Date",
            format="DD MMM YYYY",
        ),
        "deaths": st.column_config.NumberColumn(
            "Deaths",
            format="%d",
        ),
        "injured": st.column_config.NumberColumn(
            "Injured",
            format="%d",
        ),
    },
)

st.divider()

# ==========================================================
# J. PROVINCE RANKING TABLE -- with Rank + conditional formatting
# ==========================================================

st.markdown('<div class="table-tile-header">🏅 Province Ranking</div>', unsafe_allow_html=True)

if not _has_provinces:

    st.info("No province data for the current filters.")

else:

    ranking = province_summary.copy().reset_index(drop=True)
    ranking.insert(0, "Rank", range(1, len(ranking) + 1))
    ranking = ranking.rename(columns={
        "death_share_pct": "Death Share (%)",
        "casualty_share_pct": "Casualty Share (%)",
        "total_casualties": "Total Casualties",
    })

    st.dataframe(
    ranking,
    hide_index=True,
    use_container_width=True,
    height=280,
    column_config={
        "Deaths": st.column_config.NumberColumn(format="%d"),
        "Injured": st.column_config.NumberColumn(format="%d"),
        "Total Casualties": st.column_config.NumberColumn(format="%d"),
        "Death Share (%)": st.column_config.ProgressColumn(
            "Death Share (%)",
            min_value=0,
            max_value=100,
            format="%.1f%%",
        ),
        "Casualty Share (%)": st.column_config.ProgressColumn(
            "Casualty Share (%)",
            min_value=0,
            max_value=100,
            format="%.1f%%",
        ),
    },
)

st.divider()

# ==========================================================
# LATEST RECORDS -- unchanged from the existing implementation
# ==========================================================

st.markdown('<div class="table-tile-header">📋 Latest Records</div>', unsafe_allow_html=True)

latest_records = (
    filtered_df
    .drop(columns=["period"])
    .sort_values("report_date", ascending=False)
    .reset_index(drop=True)
)

st.dataframe(
    latest_records,
    hide_index=True,
    use_container_width=True,
    height=320,
    column_config={
        "report_date": st.column_config.DateColumn(
            "Report Date",
            format="DD MMM YYYY",
        ),
        "deaths": st.column_config.NumberColumn(
            "Deaths",
            format="%d",
        ),
        "injured": st.column_config.NumberColumn(
            "Injured",
            format="%d",
        ),
    },
)

st.divider()



# ==========================================================
# FOOTER
# ============================================= =============

st.markdown(
    f"""
<div class="ndma-footer">
🇵🇰 <b>Pakistan Operational Risk Intelligence Platform</b> ·
Source: NDMA · Records: <b>{reports_count:,}</b> ·
Refreshes automatically after each Airflow pipeline run.
</div>
""",
    unsafe_allow_html=True,
)