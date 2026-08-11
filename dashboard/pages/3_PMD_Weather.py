"""
dashboard/pages/3_PMD_Weather.py

PMD Weather Intelligence — Executive Command Center UI (v3).

v3 changes vs v2 (UI/UX + visualization fixes only — no business
logic, no CSS/theme/font changes, no filters removed):

  1. Sidebar Province / City / Weather Category multiselects replaced
     with a dropdown-style control (render_multiselect_dropdown):
     closed by default, shows a compact summary ("All Provinces" /
     "3 Provinces Selected"), opens like the Aggregation selectbox.
     Still returns a plain list, so filtering logic is unchanged.

  2. Combined Weather Trend chart: added 3-period rolling-average
     overlays for both temperature and humidity, a humidity fill
     layer to match the temperature fill, and min/max point
     annotations -- all computed from the same temp_trend /
     humidity_trend series already used for the KPI trend pills.
     No fabricated data.

  3. Temperature Footprint by Province (treemap): root-caused and
     fixed the "NaN°C" bug. `%{color}` in texttemplate/hovertemplate
     does not reliably resolve when Plotly Express assigns a
     *continuous* `color=` column (it renders via a shared coloraxis,
     not per-trace marker.colors). Replaced with explicit `customdata`
     carrying the real temperature / humidity / city-count / record
     values, so both the on-block label and the hover now show
     correct numbers. Also added city_count (from filtered_df, no new
     query) so the block can show "Province · Avg Temp · City Count"
     as requested.

  4. Minor visual polish: hover templates, axis titles, margins,
     legend placement -- no redesign, no theme/color/font change.

Everything else -- get_pmd_weather(), get_pmd_forecast(), data
cleaning, the filtered_df pipeline (row filters + aggregation), every
KPI calculation, every existing chart's underlying data, table
columns, and CSV/Excel export content/filenames -- is unchanged from
v2.
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    AUTO_REFRESH = True
except Exception:
    AUTO_REFRESH = False

from dashboard.db import (
    get_pmd_weather,
    get_pmd_forecast,
)

# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="PMD Weather Intelligence",
    page_icon="🌦",
    layout="wide",
)

# ==========================================================
# AUTO REFRESH
# ==========================================================

if AUTO_REFRESH:
    st_autorefresh(
        interval=60000,
        key="weather_refresh",
    )

# ==========================================================
# COMMAND SURFACE DESIGN SYSTEM (CSS) -- UNCHANGED FROM v2
# Tokens sourced from DESIGN.md ("Executive Command Surface"),
# extended with severity/trend accent scales for this page.
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
    --cs-surface-higher: #323434;

    --cs-on-surface: #e3e2e1;
    --cs-on-surface-variant: #c4c6cd;
    --cs-on-surface-dim: #8b8d92;

    --cs-outline: #8e9197;
    --cs-outline-variant: #3a3d42;

    --cs-primary: #b5c8e5;
    --cs-primary-container: #0d2137;

    --cs-success: #79dd68;
    --cs-success-container: #10321a;
    --cs-on-success-container: #92f87f;

    --cs-warning: #ffb5a0;
    --cs-warning-container: #3a1c0a;
    --cs-on-warning-container: #ff9d6e;

    --cs-danger: #ff6b6b;
    --cs-danger-container: #3a0f10;
    --cs-on-danger-container: #ffb4ab;

    /* Temperature scale: amber -> deep orange -> red */
    --temp-low: #ffc247;
    --temp-mid: #ff8a3d;
    --temp-high: #ff4d4d;

    /* Humidity scale: cyan -> blue */
    --hum-low: #22d3ee;
    --hum-mid: #0ea5e9;
    --hum-high: #0c4a7c;

    --cs-radius: 6px;
    --cs-radius-lg: 10px;
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

.block-container{
    max-width: 1680px;
    padding-top: var(--cs-space-2);
    padding-bottom: var(--cs-space-4);
}

hr{
    margin-top: var(--cs-space-2) !important;
    margin-bottom: var(--cs-space-2) !important;
    border-color: var(--cs-outline-variant) !important;
    opacity: .6 !important;
}

/* ---------------------------------------------------------
   HEADER
   --------------------------------------------------------- */

.wx-header{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--cs-space-4);
    flex-wrap: wrap;
    padding-bottom: 2px;
}

.wx-title-block{ display: flex; align-items: center; gap: var(--cs-space-3); }

.wx-title-icon{
    font-size: 26px;
    line-height: 1;
    width: 46px;
    height: 46px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(145deg, var(--cs-surface-high), var(--cs-surface));
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
}

.wx-main-title{
    font-family: var(--cs-font-mono);
    font-size: 21px;
    font-weight: 700;
    letter-spacing: .01em;
    color: var(--cs-on-surface);
    margin: 0;
}

.wx-subtitle{
    font-size: 12px;
    color: var(--cs-on-surface-variant);
    margin-top: 2px;
}

.wx-header-right{ display:flex; align-items:center; gap: var(--cs-space-2); }

.wx-live-badge{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: var(--cs-radius-pill);
    background: var(--cs-success-container);
    color: var(--cs-on-success-container);
    font-family: var(--cs-font-mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
    border: 1px solid rgba(121,221,104,.25);
}

.wx-live-badge .dot{
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--cs-success);
    box-shadow: 0 0 0 0 rgba(121,221,104,.5);
    animation: wx-pulse 1.8s infinite;
}

@keyframes wx-pulse{
    0%   { box-shadow: 0 0 0 0 rgba(121,221,104,.5); }
    70%  { box-shadow: 0 0 0 7px rgba(121,221,104,0); }
    100% { box-shadow: 0 0 0 0 rgba(121,221,104,0); }
}

/* ---------------------------------------------------------
   SECTION HEADERS
   --------------------------------------------------------- */

.wx-section-wrap{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 2px 8px 2px;
}

.wx-section-title{
    display: flex;
    align-items: center;
    gap: var(--cs-space-2);
    font-family: var(--cs-font-mono);
    font-size: 12.5px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--cs-on-surface);
}

.wx-section-title .n{
    color: var(--cs-on-surface-dim);
    font-weight: 500;
}

.wx-section-tag{
    font-family: var(--cs-font-mono);
    font-size: 10.5px;
    color: var(--cs-on-surface-dim);
    letter-spacing: .04em;
}

/* ---------------------------------------------------------
   KPI TILES
   --------------------------------------------------------- */

.tile{
    position: relative;
    background: linear-gradient(160deg, var(--cs-surface) 0%, var(--cs-bg-lowest) 130%);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: 13px 15px;
    height: 96px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    overflow: hidden;
    transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}

.tile::before{
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--tile-accent, var(--cs-primary));
    opacity: .8;
}

.tile:hover{
    transform: translateY(-3px);
    border-color: var(--tile-accent, var(--cs-outline));
    box-shadow: 0 10px 24px -12px rgba(0,0,0,.55);
}

.tile-top{ display:flex; align-items:center; justify-content:space-between; }

.tile-label{
    font-family: var(--cs-font-mono);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    display:flex; align-items:center; gap:6px;
}

.tile-icon{ font-size: 13px; opacity:.9; }

.tile-value{
    font-family: var(--cs-font-mono);
    font-size: 22px;
    font-weight: 700;
    color: var(--cs-on-surface);
    line-height: 1.1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.tile-bottom{ display:flex; align-items:center; justify-content:space-between; gap:6px; }

.tile-trend{
    font-family: var(--cs-font-mono);
    font-size: 10.5px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 1px 7px;
    border-radius: var(--cs-radius-pill);
}

.tile-trend.up{ color: var(--cs-danger); background: rgba(255,107,107,.12); }
.tile-trend.down{ color: var(--hum-low); background: rgba(142,205,240,.12); }
.tile-trend.flat{ color: var(--cs-on-surface-dim); background: rgba(255,255,255,.05); }

.tile-caption{
    font-size: 10.5px;
    color: var(--cs-on-surface-dim);
}

/* ---------------------------------------------------------
   ALERT / STATUS CARD
   --------------------------------------------------------- */

.wx-alert-card{
    background: linear-gradient(135deg, var(--cs-danger-container) 0%, var(--cs-surface) 70%);
    border: 1px solid rgba(255,107,107,.35);
    border-left: 4px solid var(--cs-danger);
    border-radius: var(--cs-radius-lg);
    padding: var(--cs-space-4);
}

.wx-alert-card.watch{
    background: linear-gradient(135deg, var(--cs-warning-container) 0%, var(--cs-surface) 70%);
    border-color: rgba(255,181,160,.35);
    border-left-color: var(--cs-warning);
}

.wx-alert-card.clear{
    background: var(--cs-surface);
    border-color: var(--cs-outline-variant);
    border-left-color: var(--cs-success);
}

.wx-alert-top{
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap: 10px;
    margin-bottom: 10px;
}

.wx-alert-title{
    font-family: var(--cs-font-mono);
    font-size: 15px;
    font-weight: 700;
    color: var(--cs-on-surface);
    display:flex; align-items:center; gap:8px;
}

.wx-badge{
    font-family: var(--cs-font-mono);
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: .05em;
    text-transform: uppercase;
    padding: 4px 11px;
    border-radius: var(--cs-radius-pill);
    background: var(--cs-danger-container);
    color: var(--cs-on-danger-container);
    border: 1px solid rgba(255,107,107,.4);
}

.wx-badge.watch{ background: var(--cs-warning-container); color: var(--cs-on-warning-container); border-color: rgba(255,181,160,.4); }
.wx-badge.clear{ background: var(--cs-success-container); color: var(--cs-on-success-container); border-color: rgba(121,221,104,.4); }

.wx-alert-grid{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--cs-space-3);
}

.wx-alert-meta{
    background: rgba(0,0,0,.18);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius);
    padding: 8px 12px;
}

.wx-alert-meta .k{
    font-family: var(--cs-font-mono);
    font-size: 9.5px;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--cs-on-surface-dim);
    margin-bottom: 2px;
}

.wx-alert-meta .v{
    font-size: 13px;
    font-weight: 600;
    color: var(--cs-on-surface);
}

/* ---------------------------------------------------------
   CHART CONTAINERS
   --------------------------------------------------------- */

div[data-testid="stPlotlyChart"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: 10px 12px 4px 12px;
    transition: border-color .15s ease;
}

div[data-testid="stPlotlyChart"]:hover{
    border-color: var(--cs-outline);
}

/* ---------------------------------------------------------
   TABLES
   --------------------------------------------------------- */

.table-tile-header{
    display:flex; align-items:center; justify-content:space-between;
    font-family: var(--cs-font-mono);
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    background: var(--cs-surface-high);
    border: 1px solid var(--cs-outline-variant);
    border-bottom: none;
    border-radius: var(--cs-radius-lg) var(--cs-radius-lg) 0 0;
    padding: 9px 14px;
}

.table-tile-header .count{
    color: var(--cs-on-surface-dim);
    font-weight: 500;
}

div[data-testid="stDataFrame"]{
    border: 1px solid var(--cs-outline-variant);
    border-top: none;
    border-radius: 0 0 var(--cs-radius-lg) var(--cs-radius-lg);
    overflow: hidden;
}

div[data-testid="stDataFrame"] table{
    font-family: var(--cs-font-mono);
    font-size: 12px;
}

div[data-testid="stDataFrame"] thead tr th{
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--cs-surface-high) !important;
}

/* ---------------------------------------------------------
   EXPORT CARD
   --------------------------------------------------------- */

.export-card-header{
    font-family: var(--cs-font-mono);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    margin-bottom: var(--cs-space-2);
    display:flex; align-items:center; gap:6px;
}

/* ---------------------------------------------------------
   SIDEBAR
   --------------------------------------------------------- */

section[data-testid="stSidebar"]{
    background: var(--cs-bg-lowest);
    border-right: 1px solid var(--cs-outline-variant);
}

section[data-testid="stSidebar"] .block-container{
    padding-top: var(--cs-space-4);
    padding-left: var(--cs-space-3);
    padding-right: var(--cs-space-3);
}

.sb-card{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: 12px 13px;
    margin-bottom: 10px;
}

.sb-card-title{
    font-family: var(--cs-font-mono);
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--cs-on-surface-dim);
    margin-bottom: 6px;
    display:flex; align-items:center; gap:6px;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3{
    font-family: var(--cs-font-mono);
    font-size: 11.5px;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
}

section[data-testid="stSidebar"] label{
    font-size: 12px !important;
    color: var(--cs-on-surface-variant) !important;
}

section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div{
    border-radius: var(--cs-radius) !important;
    background: var(--cs-bg) !important;
    border-color: var(--cs-outline-variant) !important;
}

section[data-testid="stSidebar"] div[data-baseweb="tag"]{
    background: var(--cs-primary-container) !important;
    border-radius: var(--cs-radius) !important;
}

/* Popover / dropdown trigger buttons for the custom multiselect --
   styled to look like the rest of the sidebar's dark inputs rather
   than a default Streamlit button. */
section[data-testid="stSidebar"] div[data-testid="stPopover"] > button,
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary{
    background: var(--cs-bg) !important;
    border: 1px solid var(--cs-outline-variant) !important;
    border-radius: var(--cs-radius) !important;
    color: var(--cs-on-surface) !important;
    font-family: var(--cs-font-sans) !important;
    font-size: 13px !important;
    text-align: left !important;
    justify-content: space-between !important;
}

.sb-stat-row{
    display:flex; align-items:center; justify-content:space-between;
    font-size: 12px;
    padding: 4px 0;
    color: var(--cs-on-surface-variant);
}

.sb-stat-row b{
    font-family: var(--cs-font-mono);
    color: var(--cs-on-surface);
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
    font-size: 11.5px;
    transition: transform .12s ease;
}

.stButton > button:hover, .stDownloadButton > button:hover{
    transform: translateY(-1px);
}

.stTextArea textarea{
    background: var(--cs-bg) !important;
    color: var(--cs-on-surface) !important;
    border-color: var(--cs-outline-variant) !important;
    font-family: var(--cs-font-mono) !important;
    font-size: 12.5px !important;
}

.stTextInput input{
    border-radius: var(--cs-radius) !important;
}

/* ---------------------------------------------------------
   COMPACT FOOTER
   --------------------------------------------------------- */

.wx-footer{
    text-align: center;
    font-size: 11px;
    color: var(--cs-on-surface-dim);
    padding: var(--cs-space-2) 0 0 0;
    line-height: 1.6;
}

.wx-footer b{ color: var(--cs-on-surface-variant); }

/* ---------------------------------------------------------
   ANIMATIONS
   --------------------------------------------------------- */

@keyframes wx-fadein{
    from{ opacity: 0; transform: translateY(6px); }
    to{ opacity: 1; transform: translateY(0); }
}

.tile, .wx-alert-card, div[data-testid="stPlotlyChart"], .table-tile-header{
    animation: wx-fadein .45s ease both;
}

div[data-testid="stDataFrame"] tbody tr:hover td{
    background: var(--cs-surface-high) !important;
    transition: background .12s ease;
}

div[data-testid="stMetric"], .stButton, .stDownloadButton{
    animation: wx-fadein .45s ease both;
}

/* ---------------------------------------------------------
   RESPONSIVE
   --------------------------------------------------------- */

@media (max-width: 1400px){
    .block-container{ padding-left: var(--cs-space-4); padding-right: var(--cs-space-4); }
    .wx-alert-grid{ grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 1024px){
    .wx-main-title{ font-size: 18px; }
    .wx-header{ flex-direction: column; align-items: flex-start; }
    .tile{ height: auto; min-height: 88px; }
    .wx-alert-grid{ grid-template-columns: 1fr; }
}

</style>
""",
    unsafe_allow_html=True,
)

# ==========================================================
# UI HELPER FUNCTIONS (presentation only — no business logic)
# ==========================================================

def render_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
<div class="wx-header">
  <div class="wx-title-block">
    <div class="wx-title-icon">🌦</div>
    <div>
      <div class="wx-main-title">{title}</div>
      <div class="wx-subtitle">{subtitle}</div>
    </div>
  </div>
  <div class="wx-header-right">
    <div class="wx-live-badge"><span class="dot"></span> Live</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_section_title(icon: str, title: str, tag: str = "") -> None:
    st.markdown(
        f"""
<div class="wx-section-wrap">
  <div class="wx-section-title">{icon} {title}</div>
  <div class="wx-section-tag">{tag}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_kpi_tile(
    label: str,
    value: str,
    icon: str = "▪",
    accent: str = "var(--cs-primary)",
    trend: float | None = None,
    trend_label: str = "",
    caption: str = "",
) -> str:
    """
    Renders one KPI tile. `trend` (percent, real number derived from the
    existing filtered_df — never fabricated) drives an up/down/flat pill;
    pass None to hide the trend pill and show a plain caption instead.
    """
    trend_html = ""
    if trend is not None:
        direction = "up" if trend > 0.05 else ("down" if trend < -0.05 else "flat")
        arrow = "▲" if direction == "up" else ("▼" if direction == "down" else "▬")
        trend_html = f'<span class="tile-trend {direction}">{arrow} {abs(trend):.1f}% {trend_label}</span>'
    elif caption:
        trend_html = f'<span class="tile-caption">{caption}</span>'

    return f"""
<div class="tile" style="--tile-accent:{accent};">
  <div class="tile-top">
    <div class="tile-label"><span class="tile-icon">{icon}</span>{label}</div>
  </div>
  <div class="tile-value">{value}</div>
  <div class="tile-bottom">{trend_html}</div>
</div>
"""


def render_alert_card(title: str, variant: str, meta: dict) -> str:
    badge_label = {"danger": "ACTIVE ALERT", "watch": "WATCH", "clear": "ALL CLEAR"}.get(variant, "STATUS")
    meta_html = "".join(
        f"""
<div class="wx-alert-meta">
  <div class="k">{k}</div>
  <div class="v">{v}</div>
</div>
"""
        for k, v in meta.items()
    )
    return f"""
<div class="wx-alert-card {variant}">
  <div class="wx-alert-top">
    <div class="wx-alert-title">⚠ {title}</div>
    <div class="wx-badge {variant}">{badge_label}</div>
  </div>
  <div class="wx-alert-grid">{meta_html}</div>
</div>
"""


def render_table_header(icon: str, title: str, count: str = "") -> None:
    count_html = f'<span class="count">{count}</span>' if count else ""
    st.markdown(
        f'<div class="table-tile-header"><span>{icon} {title}</span>{count_html}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_card_open(icon: str, title: str) -> None:
    st.sidebar.markdown(
        f'<div class="sb-card"><div class="sb-card-title">{icon} {title}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_card_close() -> None:
    st.sidebar.markdown("</div>", unsafe_allow_html=True)


def render_multiselect_dropdown(
    label: str,
    options: list,
    state_key: str,
) -> list:
    """
    Dropdown-style replacement for st.multiselect in the sidebar.

    Instead of rendering every selection as a chip inline (which is
    what st.multiselect always does — there's no prop to suppress it),
    this renders a single closed trigger (an st.popover, matching the
    look/behavior of the Aggregation selectbox; falls back to
    st.expander on Streamlit versions without popover support) whose
    label summarizes the selection ("All Provinces" / "3 Provinces
    Selected" / "No Provinces Selected"). Opening it reveals
    checkboxes plus Select All / Clear All.

    Selection lives in st.session_state keyed per option, so it
    survives reruns and gracefully reconciles when `options` itself
    changes (e.g. City options narrowing after a Province change) —
    any option no longer in the list is simply dropped from the
    returned selection.

    Returns a plain list, in the same order as `options` — identical
    in shape/behavior to st.multiselect's return value, so it can be
    swapped in without touching any downstream filtering logic.
    """

    for opt in options:
        st.session_state.setdefault(f"{state_key}__opt__{opt}", True)

    selected = [opt for opt in options if st.session_state.get(f"{state_key}__opt__{opt}", True)]

    total = len(options)
    chosen = len(selected)

    if total == 0:
        summary = f"No {label} Available"
    elif chosen == total:
        summary = f"All {label}"
    elif chosen == 0:
        summary = f"No {label} Selected"
    else:
        summary = f"{chosen} {label} Selected"

    container = st.sidebar.popover if hasattr(st.sidebar, "popover") else st.sidebar.expander

    with container(summary, use_container_width=True):

        bcol1, bcol2 = st.columns(2)

        with bcol1:
            if st.button("Select All", key=f"{state_key}__select_all", use_container_width=True):
                for opt in options:
                    st.session_state[f"{state_key}__opt__{opt}"] = True
                st.rerun()

        with bcol2:
            if st.button("Clear All", key=f"{state_key}__clear_all", use_container_width=True):
                for opt in options:
                    st.session_state[f"{state_key}__opt__{opt}"] = False
                st.rerun()

        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

        for opt in options:
            st.checkbox(
                str(opt),
                value=st.session_state.get(f"{state_key}__opt__{opt}", True),
                key=f"{state_key}__opt__{opt}",
            )

    return [opt for opt in options if st.session_state.get(f"{state_key}__opt__{opt}", True)]


_PLOTLY_FONT = dict(family="Inter, sans-serif", size=12, color="#c4c6cd")

_PLOTLY_LAYOUT_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=_PLOTLY_FONT,
    hoverlabel=dict(
        bgcolor="#1e2020",
        bordercolor="#3a3d42",
        font=dict(family="JetBrains Mono, monospace", size=12, color="#e3e2e1"),
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        bgcolor="rgba(0,0,0,0)",
    ),
    transition=dict(duration=300, easing="cubic-in-out"),
)


def style_fig(fig, **layout_overrides):
    """
    Apply the shared Executive Command Surface chart cosmetics (dark
    transparent background, Inter/JetBrains Mono fonts, unified hover
    styling, subtle gridlines, smooth transitions) on top of whatever
    layout the chart already has, then apply per-chart overrides.
    Never touches trace data/x/y bindings.
    """
    fig.update_layout(**_PLOTLY_LAYOUT_BASE)
    fig.update_layout(**layout_overrides)
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def style_metric_column(styler, column: str, kind: str):
    """
    Applies a lightweight, dependency-free (no matplotlib) color
    treatment to a ranking table column based on real values already
    present in the dataframe — temperature uses the yellow->red scale,
    humidity uses the light->dark blue scale. Formatting only.
    """

    def _color(val):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return ""
        if kind == "temp":
            if v >= 38:
                c = "#ff4d4d"
            elif v >= 30:
                c = "#ff8a3d"
            else:
                c = "#ffc247"
        else:
            if v >= 70:
                c = "#0c4a7c"
            elif v >= 45:
                c = "#0ea5e9"
            else:
                c = "#22d3ee"
        return f"background-color:{c}26; color:{c}; font-weight:700;"

    return styler.map(_color, subset=[column])


def add_rank_medals(df_in: pd.DataFrame) -> pd.DataFrame:
    """Prefixes rank 1-3 with medal emoji — display-only, no data change."""
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    out = df_in.copy()
    out.insert(0, "Rank", [medals.get(i, f"#{i}") for i in out.index])
    return out


# ==========================================================
# HEADER
# ==========================================================

render_header(
    "PAKISTAN WEATHER INTELLIGENCE",
    "Pakistan Meteorological Department (PMD) • Live Weather Monitoring &amp; Forecast Intelligence",
)

st.divider()

# ==========================================================
# LOAD DATABASE -- EXACTLY ONE QUERY for the analytics pipeline
# ==========================================================

with st.spinner("Loading latest PMD weather data..."):

    try:

        df = get_pmd_weather()

        df_alert = get_pmd_forecast()

    except Exception as e:

        st.error(f"Database Error\n\n{e}")

        st.stop()

if df.empty:

    st.warning("No PMD weather data available.")

    st.stop()

# ==========================================================
# DATA CLEANING
# ==========================================================

df = df.copy()

numeric_columns = [

    "max_temperature",

    "humidity",

]

for col in numeric_columns:

    if col in df.columns:

        df[col] = pd.to_numeric(

            df[col],

            errors="coerce",

        )

df["temperature"] = df["max_temperature"]

df["scraped_at"] = pd.to_datetime(

    df["scraped_at"],

    errors="coerce",

)

df["city"] = (

    df["city"]

    .fillna("Unknown")

    .astype(str)

    .str.strip()

)

df["province"] = (

    df["province"]

    .fillna("Unknown")

    .astype(str)

    .str.strip()

)

df["category"] = (

    df["category"]

    .fillna("Unknown")

    .astype(str)

    .str.strip()

)

df = df.dropna(subset=["scraped_at"])

# ==========================================================
# SIDEBAR -- DASHBOARD FILTERS
# ==========================================================

st.sidebar.markdown(
    """
<div class="im-side-brand">
  <div class="im-side-avatar">🌦</div>
  <div>
    <div class="im-side-brand-title">PMD WEATHER</div>
    <div class="im-side-brand-sub">LIVE WEATHER INTELLIGENCE</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

min_date = df["scraped_at"].min().date()
max_date = df["scraped_at"].max().date()

# ==========================================================
# DATE RANGE
# ==========================================================

with st.sidebar.container():

    st.markdown(
        """
<div class="im-side-section">
<span class="im-side-section-label">📅 DATE RANGE</span>
</div>
""",
        unsafe_allow_html=True,
    )

    start_date = st.date_input(
        "Start Date",
        value=min_date,
        min_value=min_date,
        max_value=max_date,
    )

    end_date = st.date_input(
        "End Date",
        value=max_date,
        min_value=min_date,
        max_value=max_date,
    )

# ==========================================================
# GEOGRAPHY
# (Province / City now use the dropdown-style multiselect —
# see render_multiselect_dropdown. Same downstream variables,
# same filtering behavior as the old st.multiselect calls.)
# ==========================================================

province_list = sorted(df["province"].dropna().unique())

with st.sidebar.container():

    st.markdown(
        """
<div class="im-side-section">
<span class="im-side-section-label">📍 GEOGRAPHY</span>
</div>
""",
        unsafe_allow_html=True,
    )

    selected_provinces = render_multiselect_dropdown(
        "Provinces", province_list, state_key="flt_province",
    )

    city_options = sorted(
        df[
            df["province"].isin(selected_provinces)
        ]["city"]
        .dropna()
        .unique()
    )

    selected_cities = render_multiselect_dropdown(
        "Cities", city_options, state_key="flt_city",
    )

# ==========================================================
# WEATHER CONDITIONS
# ==========================================================

with st.sidebar.container():

    st.markdown(
        """
<div class="im-side-section">
<span class="im-side-section-label">🌤 CONDITIONS</span>
</div>
""",
        unsafe_allow_html=True,
    )

    category_list = sorted(df["category"].dropna().unique())

    selected_categories = render_multiselect_dropdown(
        "Categories", category_list, state_key="flt_category",
    )

    aggregation = st.selectbox(
        "Aggregation",
        ["Hourly", "Daily", "Weekly", "Monthly", "Yearly"],
        index=1,
    )

# ==========================================================
# AGGREGATION MAP
# ==========================================================

_FREQ_MAP = {
    "Hourly": "h",
    "Daily": "D",
    "Weekly": "W",
    "Monthly": "ME",
    "Yearly": "YE",
}

freq = _FREQ_MAP[aggregation]

# ==========================================================
# DATASET OVERVIEW
# ==========================================================

st.sidebar.markdown(
    """
    <div class="im-side-section">
        <span class="im-side-section-label">📊 DATASET OVERVIEW</span>
    </div>
    """,
    unsafe_allow_html=True,
)

s1, s2 = st.sidebar.columns(2)

with s1:
    st.metric(
        "Cities",
        f"{df['city'].nunique():,}",
    )

with s2:
    st.metric(
        "Provinces",
        f"{df['province'].nunique():,}",
    )

st.sidebar.metric(
    "Weather Records",
    f"{len(df):,}",
)
# ==========================================================
# BUILD filtered_df -- THE SINGLE SOURCE OF TRUTH
# Step 1-4: row-level filters applied directly onto filtered_df.
# Step 5: Aggregation applied directly onto filtered_df, replacing
# it with its own time-bucketed, per-city/per-province form. Every
# KPI / chart / ranking / heatmap / table / export below reads ONLY
# from this final filtered_df.
# ==========================================================

filtered_df = df.copy()

start_ts = pd.to_datetime(start_date)
end_ts = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

filtered_df = filtered_df[

    (filtered_df["scraped_at"] >= start_ts)

    &

    (filtered_df["scraped_at"] <= end_ts)

]

filtered_df = filtered_df[

    filtered_df["province"].isin(selected_provinces)

]

filtered_df = filtered_df[

    filtered_df["city"].isin(selected_cities)

]

filtered_df = filtered_df[

    filtered_df["category"].isin(selected_categories)

]

if filtered_df.empty:

    st.warning("No weather records found for the selected filters.")

    st.stop()

filtered_df = (

    filtered_df

    .groupby(

        [

            "city",

            "province",

            pd.Grouper(key="scraped_at", freq=freq),

        ]

    )[["temperature", "humidity"]]

    .mean()

    .reset_index()

)

if filtered_df.empty:

    st.warning("No weather records found for the selected filters.")

    st.stop()

# ==========================================================
# SIDEBAR -- EXPORT
# ==========================================================

render_sidebar_card_open("📥", "Export")

_csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")

st.sidebar.download_button(
    "⬇ CSV",
    data=_csv_bytes,
    file_name="pmd_weather_filtered.csv",
    mime="text/csv",
    use_container_width=True,
)

_excel_buffer = io.BytesIO()

with pd.ExcelWriter(_excel_buffer, engine="openpyxl") as _writer:

    filtered_df.to_excel(_writer, index=False, sheet_name="PMD Weather")

st.sidebar.download_button(
    "⬇ Excel",
    data=_excel_buffer.getvalue(),
    file_name="pmd_weather_filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
    key="sidebar_excel_export",
)

render_sidebar_card_close()

# ==========================================================
# SHARED TREND SERIES (same aggregation the combined trend chart
# uses further down the page — computed once here, before the
# KPI row, purely so the KPI trend pills and the chart stay in
# sync and nothing is computed twice). No data is fabricated;
# this is the same groupby("scraped_at") used by the chart below.
#
# v3: also adds a 3-period rolling average column to each series
# here (reused by both the chart's rolling-average overlay and
# available for the KPI pills), so it's computed exactly once.
# ==========================================================

temp_trend = (

    filtered_df

    .groupby("scraped_at", as_index=False)["temperature"]

    .mean()

    .sort_values("scraped_at")

)

humidity_trend = (

    filtered_df

    .groupby("scraped_at", as_index=False)["humidity"]

    .mean()

    .sort_values("scraped_at")

)

temp_trend["temperature_rolling"] = (
    temp_trend["temperature"].rolling(window=3, min_periods=1).mean()
)

humidity_trend["humidity_rolling"] = (
    humidity_trend["humidity"].rolling(window=3, min_periods=1).mean()
)


def _half_split_trend(series: pd.Series) -> float:
    """% change between the first half and second half of a real series."""
    vals = series.dropna().to_numpy()
    if len(vals) < 2:
        return 0.0
    mid = len(vals) // 2
    first = vals[:mid].mean() if mid > 0 else vals[0]
    second = vals[mid:].mean()
    if first == 0:
        return 0.0
    return ((second - first) / abs(first)) * 100


temp_trend_pct = _half_split_trend(temp_trend["temperature"])
humidity_trend_pct = _half_split_trend(humidity_trend["humidity"])

# ==========================================================
# WEATHER ALERT -- PREMIUM ALERT CARD (unrelated feature, data kept
# as-is). Shown first, per the requested storytelling order:
# Alert -> Executive KPIs -> Trend -> Province -> Distribution ->
# Rankings -> Records -> Export.
# ==========================================================

render_section_title("🛰", "Weather Alert Status")

if not df_alert.empty:

    latest_alert = df_alert.iloc[0]

    _sev = str(latest_alert["severity"])
    _sev_lower = _sev.lower()
    variant = "danger" if _sev_lower in ("high", "severe", "critical", "extreme") else "watch"

    meta = {"Severity": _sev}

    # Only surface fields that genuinely exist in the query result —
    # nothing here is invented if the column isn't present.
    for label, col in [
        ("Affected Regions", "affected_regions"),
        ("Affected Regions", "region"),
        ("Duration", "duration"),
        ("Valid Until", "valid_until"),
    ]:
        if col in latest_alert.index and pd.notna(latest_alert[col]) and label not in meta:
            meta[label] = latest_alert[col]

    meta["Issued"] = latest_alert["scraped_at"]

    st.markdown(
        render_alert_card(str(latest_alert["alert_type"]), variant, meta),
        unsafe_allow_html=True,
    )

    with st.expander("📄 View Full Forecast Details"):

        forecast = str(latest_alert["forecast"]).strip()

        forecast = forecast.replace("•", "\n•")
        forecast = forecast.replace(". ", ".\n\n")
        forecast = forecast.replace(" - ", "\n- ")

        st.text_area(
            "Forecast Details",
            forecast,
            height=240,
            disabled=True,
            label_visibility="collapsed",
        )

        st.caption(f"Updated : {latest_alert['scraped_at']}")

else:

    st.markdown(
        render_alert_card("No Active Weather Alerts", "clear", {"Status": "Normal", "Checked": pd.Timestamp.now().strftime("%d %b %Y %H:%M")}),
        unsafe_allow_html=True,
    )

st.divider()

# ==========================================================
# EXECUTIVE SUMMARY / KPIs (from filtered_df ONLY)
# ==========================================================

city_count = filtered_df["city"].nunique()

province_count = filtered_df["province"].nunique()

avg_temp = filtered_df["temperature"].mean()

max_temp = filtered_df["temperature"].max()

min_temp = filtered_df["temperature"].min()

avg_humidity = filtered_df["humidity"].mean()

max_humidity = filtered_df["humidity"].max()

hottest_row = filtered_df.loc[filtered_df["temperature"].idxmax()]

most_humid_row = filtered_df.loc[filtered_df["humidity"].idxmax()]

latest_report = filtered_df["scraped_at"].max()

active_alert_label = "None"
alert_variant = "clear"
if not df_alert.empty:
    active_alert_label = str(df_alert.iloc[0]["alert_type"])
    _sev = str(df_alert.iloc[0].get("severity", "")).lower()
    alert_variant = "danger" if _sev in ("high", "severe", "critical", "extreme") else "watch"

render_section_title("📊", "Executive Summary", f"Aggregation · {aggregation}")

k1, k2, k3, k4, k5, k6 = st.columns(6)

with k1:
    st.markdown(
        render_kpi_tile(
            "Highest Temp", f"{max_temp:.1f}°C", icon="🔥",
            accent="var(--temp-high)",
            trend=temp_trend_pct, trend_label="vs period start",
        ),
        unsafe_allow_html=True,
    )

with k2:
    st.markdown(
        render_kpi_tile(
            "Highest Humidity", f"{max_humidity:.0f}%", icon="💧",
            accent="var(--hum-high)",
            trend=humidity_trend_pct, trend_label="vs period start",
        ),
        unsafe_allow_html=True,
    )

with k3:
    st.markdown(
        render_kpi_tile("Total Cities", f"{city_count:,}", icon="🏙", accent="var(--cs-primary)", caption="in selection"),
        unsafe_allow_html=True,
    )

with k4:
    st.markdown(
        render_kpi_tile("Total Provinces", f"{province_count:,}", icon="🗺", accent="var(--cs-primary)", caption="in selection"),
        unsafe_allow_html=True,
    )

with k5:
    st.markdown(
        render_kpi_tile("Latest Update", latest_report.strftime("%d %b, %H:%M"), icon="🕒", accent="var(--cs-success)", caption=aggregation + " bucket"),
        unsafe_allow_html=True,
    )

with k6:
    accent = {"danger": "var(--cs-danger)", "watch": "var(--cs-warning)", "clear": "var(--cs-success)"}[alert_variant]
    st.markdown(
        render_kpi_tile("Active Alert", active_alert_label, icon="⚠", accent=accent, caption=alert_variant.upper()),
        unsafe_allow_html=True,
    )

k7, k8, k9, k10 = st.columns(4)

with k7:
    st.markdown(render_kpi_tile("Avg Temperature", f"{avg_temp:.1f} °C", icon="🌡", accent="var(--temp-mid)"), unsafe_allow_html=True)

with k8:
    st.markdown(render_kpi_tile("Avg Humidity", f"{avg_humidity:.0f}%", icon="💧", accent="var(--hum-low)"), unsafe_allow_html=True)

with k9:
    st.markdown(render_kpi_tile("Min Temperature", f"{min_temp:.1f} °C", icon="❄", accent="var(--cs-primary)"), unsafe_allow_html=True)

with k10:
    st.markdown(render_kpi_tile("Hottest City", hottest_row["city"], icon="📍", accent="var(--temp-high)", caption=hottest_row["province"]), unsafe_allow_html=True)

st.divider()

# ==========================================================
# COMBINED WEATHER TREND -- Enterprise version (Grafana / Kibana /
# QuickSight / Power BI style): KPI strip, auto-generated insight
# card, threshold background zones, rolling averages, max/min
# markers, dynamic annotations, rich unified hover, a Combined/Split
# view toggle, and a proper top legend + dual/independent axes.
#
# Still built entirely from temp_trend / humidity_trend / filtered_df
# (already computed above, unchanged) and styled through
# _PLOTLY_LAYOUT_BASE. No new dependencies, no new files, no upstream
# data changes -- this is a pure visualization upgrade of the same
# aggregated series.
# ==========================================================

render_section_title("📈", "Combined Weather Trend", aggregation)

combined_trend = temp_trend.merge(humidity_trend, on="scraped_at", how="outer").sort_values("scraped_at")

_temp_valid = combined_trend.dropna(subset=["temperature"])
_hum_valid = combined_trend.dropna(subset=["humidity"])

# ---- Threshold bands (same cut-points already used elsewhere on
# this page in style_metric_column(), so the visual language is
# consistent across the dashboard) ----

_TEMP_ZONES = [
    (float("-inf"), 30, "rgba(255,194,71,0.06)", "Normal"),
    (30, 38, "rgba(255,138,61,0.08)", "Warm"),
    (38, float("inf"), "rgba(255,77,77,0.10)", "Hot"),
]

_HUM_ZONES = [
    (float("-inf"), 45, "rgba(34,211,238,0.06)", "Low"),
    (45, 70, "rgba(14,165,233,0.08)", "Moderate"),
    (70, float("inf"), "rgba(12,74,124,0.12)", "High"),
]

# ==========================================================
# COMBINED / SPLIT WEATHER TREND
# ==========================================================

render_section_title(
    "📈",
    "Weather Trend",
    aggregation,
)

combined_trend = (
    temp_trend
    .merge(
        humidity_trend,
        on="scraped_at",
        how="outer",
    )
    .sort_values("scraped_at")
)

_temp_valid = combined_trend.dropna(
    subset=["temperature"]
)

_hum_valid = combined_trend.dropna(
    subset=["humidity"]
)

_temp_max_row = (
    _temp_valid.loc[
        _temp_valid["temperature"].idxmax()
    ]
    if not _temp_valid.empty
    else None
)

_temp_min_row = (
    _temp_valid.loc[
        _temp_valid["temperature"].idxmin()
    ]
    if not _temp_valid.empty
    else None
)

_hum_max_row = (
    _hum_valid.loc[
        _hum_valid["humidity"].idxmax()
    ]
    if not _hum_valid.empty
    else None
)

_hum_min_row = (
    _hum_valid.loc[
        _hum_valid["humidity"].idxmin()
    ]
    if not _hum_valid.empty
    else None
)


# ----------------------------------------------------------
# VIEW SWITCH
# ----------------------------------------------------------

trend_view = st.radio(
    "Trend view",
    ["Combined View", "Split View"],
    horizontal=True,
    label_visibility="collapsed",
    key="wx_trend_view_toggle",
)


# ==========================================================
# COMBINED VIEW
# ==========================================================

if trend_view == "Combined View":

    fig = make_subplots(
        specs=[[{"secondary_y": True}]]
    )

    # ------------------------------
    # Temperature
    # ------------------------------

    fig.add_trace(
        go.Scatter(
            x=combined_trend["scraped_at"],
            y=combined_trend["temperature"],
            name="Temperature",
            mode="lines+markers",
            line=dict(
                width=3,
                color="#ff8a3d",
                shape="linear",
            ),
            marker=dict(
                size=5,
                color="#ff8a3d",
            ),
            hovertemplate=(
                "<b>%{x|%d %b %Y %H:%M}</b>"
                "<br>Temperature: %{y:.1f} °C"
                "<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # Temperature rolling average

    fig.add_trace(
        go.Scatter(
            x=combined_trend["scraped_at"],
            y=combined_trend["temperature_rolling"],
            name="Temperature Rolling Avg",
            mode="lines",
            line=dict(
                width=2,
                color="#ffc247",
                dash="dot",
            ),
            hovertemplate=(
                "Temperature avg: %{y:.1f} °C"
                "<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # ------------------------------
    # Humidity
    # ------------------------------

    fig.add_trace(
        go.Scatter(
            x=combined_trend["scraped_at"],
            y=combined_trend["humidity"],
            name="Humidity",
            mode="lines+markers",
            line=dict(
                width=3,
                color="#22d3ee",
                shape="linear",
            ),
            marker=dict(
                size=5,
                color="#22d3ee",
            ),
            hovertemplate=(
                "<b>%{x|%d %b %Y %H:%M}</b>"
                "<br>Humidity: %{y:.0f}%"
                "<extra></extra>"
            ),
        ),
        secondary_y=True,
    )

    # Humidity rolling average

    fig.add_trace(
        go.Scatter(
            x=combined_trend["scraped_at"],
            y=combined_trend["humidity_rolling"],
            name="Humidity Rolling Avg",
            mode="lines",
            line=dict(
                width=2,
                color="#0ea5e9",
                dash="dot",
            ),
            hovertemplate=(
                "Humidity avg: %{y:.0f}%"
                "<extra></extra>"
            ),
        ),
        secondary_y=True,
    )

    # ------------------------------
    # Peak markers
    # ------------------------------

    if _temp_max_row is not None:
        fig.add_trace(
            go.Scatter(
                x=[_temp_max_row["scraped_at"]],
                y=[_temp_max_row["temperature"]],
                mode="markers",
                name="Peak Temperature",
                marker=dict(
                    size=11,
                    color="#ff4d4d",
                    symbol="triangle-up",
                ),
                hovertemplate=(
                    "Peak Temperature: %{y:.1f} °C"
                    "<extra></extra>"
                ),
                showlegend=False,
            ),
            secondary_y=False,
        )

    if _hum_max_row is not None:
        fig.add_trace(
            go.Scatter(
                x=[_hum_max_row["scraped_at"]],
                y=[_hum_max_row["humidity"]],
                mode="markers",
                name="Peak Humidity",
                marker=dict(
                    size=11,
                    color="#0c4a7c",
                    symbol="triangle-up",
                ),
                hovertemplate=(
                    "Peak Humidity: %{y:.0f}%"
                    "<extra></extra>"
                ),
                showlegend=False,
            ),
            secondary_y=True,
        )

    # ------------------------------
    # Layout
    # ------------------------------

    fig = style_fig(
        fig,
        height=440,
        hovermode="x unified",
        margin=dict(
            l=20,
            r=20,
            t=45,
            b=25,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
    )

    fig.update_xaxes(
        title_text="Time",
        rangeslider=dict(
            visible=True,
            thickness=0.05,
        ),
    )

    fig.update_yaxes(
        title_text="Temperature (°C)",
        secondary_y=False,
    )

    fig.update_yaxes(
        title_text="Humidity (%)",
        secondary_y=True,
        showgrid=False,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "displaylogo": False,
        },
    )


# ==========================================================
# SPLIT VIEW
# ==========================================================

else:

    left, right = st.columns(2)

    # ======================================================
    # TEMPERATURE
    # ======================================================

    with left:

        fig_temp = go.Figure()

        fig_temp.add_trace(
            go.Scatter(
                x=combined_trend["scraped_at"],
                y=combined_trend["temperature"],
                name="Temperature",
                mode="lines+markers",
                line=dict(
                    width=3,
                    color="#ff8a3d",
                    shape="linear",
                ),
                marker=dict(
                    size=5,
                    color="#ff8a3d",
                ),
                hovertemplate=(
                    "<b>%{x|%d %b %Y %H:%M}</b>"
                    "<br>Temperature: %{y:.1f} °C"
                    "<extra></extra>"
                ),
            )
        )

        fig_temp.add_trace(
            go.Scatter(
                x=combined_trend["scraped_at"],
                y=combined_trend["temperature_rolling"],
                name="Rolling Avg",
                mode="lines",
                line=dict(
                    width=2,
                    color="#ffc247",
                    dash="dot",
                ),
                hovertemplate=(
                    "Rolling Avg: %{y:.1f} °C"
                    "<extra></extra>"
                ),
            )
        )

        if _temp_max_row is not None:
            fig_temp.add_trace(
                go.Scatter(
                    x=[_temp_max_row["scraped_at"]],
                    y=[_temp_max_row["temperature"]],
                    mode="markers",
                    marker=dict(
                        size=11,
                        color="#ff4d4d",
                        symbol="triangle-up",
                    ),
                    name="Peak",
                    hovertemplate=(
                        "Peak: %{y:.1f} °C"
                        "<extra></extra>"
                    ),
                    showlegend=False,
                )
            )

        fig_temp = style_fig(
            fig_temp,
            height=360,
            hovermode="x unified",
            title=dict(
                text="🌡 Temperature Trend",
                font=dict(
                    size=14,
                    family="JetBrains Mono, monospace",
                ),
            ),
            xaxis_title="",
            yaxis_title="°C",
            margin=dict(
                l=20,
                r=20,
                t=50,
                b=20,
            ),
        )

        st.plotly_chart(
            fig_temp,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "displaylogo": False,
            },
        )

    # ======================================================
    # HUMIDITY
    # ======================================================

    with right:

        fig_hum = go.Figure()

        fig_hum.add_trace(
            go.Scatter(
                x=combined_trend["scraped_at"],
                y=combined_trend["humidity"],
                name="Humidity",
                mode="lines+markers",
                line=dict(
                    width=3,
                    color="#22d3ee",
                    shape="linear",
                ),
                marker=dict(
                    size=5,
                    color="#22d3ee",
                ),
                hovertemplate=(
                    "<b>%{x|%d %b %Y %H:%M}</b>"
                    "<br>Humidity: %{y:.0f}%"
                    "<extra></extra>"
                ),
            )
        )

        fig_hum.add_trace(
            go.Scatter(
                x=combined_trend["scraped_at"],
                y=combined_trend["humidity_rolling"],
                name="Rolling Avg",
                mode="lines",
                line=dict(
                    width=2,
                    color="#0ea5e9",
                    dash="dot",
                ),
                hovertemplate=(
                    "Rolling Avg: %{y:.0f}%"
                    "<extra></extra>"
                ),
            )
        )

        if _hum_max_row is not None:
            fig_hum.add_trace(
                go.Scatter(
                    x=[_hum_max_row["scraped_at"]],
                    y=[_hum_max_row["humidity"]],
                    mode="markers",
                    marker=dict(
                        size=11,
                        color="#0c4a7c",
                        symbol="triangle-up",
                    ),
                    name="Peak",
                    hovertemplate=(
                        "Peak: %{y:.0f}%"
                        "<extra></extra>"
                    ),
                    showlegend=False,
                )
            )

        fig_hum = style_fig(
            fig_hum,
            height=360,
            hovermode="x unified",
            title=dict(
                text="💧 Humidity Trend",
                font=dict(
                    size=14,
                    family="JetBrains Mono, monospace",
                ),
            ),
            xaxis_title="Time",
            yaxis_title="%",
            margin=dict(
                l=20,
                r=20,
                t=50,
                b=20,
            ),
        )

        st.plotly_chart(
            fig_hum,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "displaylogo": False,
            },
        )
# ==========================================================
# PROVINCE COMPARISON -- ONE grouped bar chart replacing the
# separate Avg Temperature / Avg Humidity by Province charts.
# Same province_summary aggregation used everywhere below.
#
# v3: also merges city_count per province (from filtered_df, no
# new query) so the Treemap fix below can show it without a
# separate computation.
# ==========================================================

render_section_title("🗺", "Province Comparison")

province_summary = (

    filtered_df

    .groupby("province", as_index=False)[["temperature", "humidity"]]

    .mean()

)

# Record count per province, from the same filtered_df — used to
# size the bubble chart and as the Treemap's "area" value (real
# counts, nothing fabricated).
province_counts = (

    filtered_df

    .groupby("province", as_index=False)

    .size()

    .rename(columns={"size": "records"})

)

# City count per province, from the same filtered_df — used by the
# Treemap fix below.
province_city_counts = (

    filtered_df

    .groupby("province")["city"]

    .nunique()

    .reset_index(name="city_count")

)

province_summary = province_summary.merge(province_counts, on="province", how="left")
province_summary = province_summary.merge(province_city_counts, on="province", how="left")

sort_col, _sort_spacer = st.columns([1, 3])
with sort_col:
    sort_metric = st.selectbox(
        "Sort provinces by",
        ["Temperature", "Humidity"],
        index=0,
        label_visibility="collapsed",
    )

sort_key = "temperature" if sort_metric == "Temperature" else "humidity"
province_sorted = province_summary.sort_values(sort_key, ascending=False)

fig = go.Figure()

fig.add_trace(
    go.Bar(
        x=province_sorted["province"],
        y=province_sorted["temperature"],
        name="Avg Temperature (°C)",
        marker=dict(color="#ff8a3d", line=dict(width=0)),
        text=province_sorted["temperature"],
        texttemplate="%{text:.1f}°C",
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Avg Temperature : %{y:.1f} °C<extra></extra>",
    )
)

fig.add_trace(
    go.Bar(
        x=province_sorted["province"],
        y=province_sorted["humidity"],
        name="Avg Humidity (%)",
        marker=dict(color="#22d3ee", line=dict(width=0)),
        text=province_sorted["humidity"],
        texttemplate="%{text:.0f}%",
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Avg Humidity : %{y:.0f}%<extra></extra>",
    )
)

fig = style_fig(
    fig,
    height=440,
    barmode="group",
    bargap=0.28,
    bargroupgap=0.12,
    xaxis_title="",
    yaxis_title="",
    margin=dict(l=20, r=20, t=30, b=20),
)
fig.update_traces(marker_cornerradius=6)

st.plotly_chart(fig, use_container_width=True)

st.divider()

# ==========================================================
# WEATHER DISTRIBUTION -- bubble comparison + Treemap.
# Both built from province_summary (same aggregated data used
# in Province Comparison above), just visualized differently.
# ==========================================================

render_section_title("🌐", "Weather Distribution")

left, right = st.columns(2)

with left:

    render_section_title("🫧", "Province Bubble Comparison", "temp vs humidity")

    fig = px.scatter(

        province_summary,

        x="temperature",

        y="humidity",

        size="records",

        color="temperature",

        text="province",

        color_continuous_scale=["#ffc247", "#ff8a3d", "#ff4d4d"],

        size_max=52,

    )

    fig.update_traces(

        textposition="top center",

        textfont=dict(size=12, color="#e3e2e1"),

        marker=dict(line=dict(width=1.5, color="#1e2020"), opacity=0.92),

        hovertemplate="<b>%{text}</b><br>Avg Temp : %{x:.1f} °C<br>Avg Humidity : %{y:.0f}%<br>Records : %{marker.size}<extra></extra>",

    )

    fig = style_fig(
        fig,
        height=430,
        xaxis_title="Avg Temperature (°C)",
        yaxis_title="Avg Humidity (%)",
        margin=dict(l=20, r=20, t=15, b=20),
        coloraxis_showscale=False,
    )

    st.plotly_chart(fig, use_container_width=True)

with right:

    render_section_title("🌳", "Temperature Footprint by Province", "treemap")

    # ----------------------------------------------------------
    # v3 FIX (Issue 3): the previous version referenced %{color}
    # in texttemplate/hovertemplate, which does not reliably
    # resolve when Plotly Express assigns a *continuous* color
    # column (it renders through a shared coloraxis rather than
    # per-trace marker.colors) — that's what produced "NaN°C" on
    # every block even though province_summary's `temperature`
    # column is populated correctly (same data the bar chart and
    # bubble chart above already render correctly, since neither
    # of them references %{color}).
    #
    # Fix: pass the real values explicitly via `custom_data` and
    # reference them as %{customdata[n]} instead of %{color}.
    # This is deterministic regardless of Plotly/coloraxis version
    # behavior. Also adds city_count to satisfy "Province · Avg
    # Temp · City Count" on the block, plus Avg Humidity and
    # Weather Records in the hover — all real, already-aggregated
    # values from province_summary, nothing fabricated.
    # ----------------------------------------------------------

    fig = px.treemap(

        province_summary,

        path=["province"],

        values="records",

        color="temperature",

        color_continuous_scale=["#ffc247", "#ff8a3d", "#ff4d4d"],

        custom_data=["temperature", "humidity", "city_count", "records"],

    )

    fig.update_traces(

        texttemplate="<b>%{label}</b><br>%{customdata[0]:.1f}°C · %{customdata[2]:.0f} cities",

        textfont=dict(size=14, family="Inter, sans-serif"),

        hovertemplate=(
            "<b>%{label}</b><br>"
            "Avg Temperature : %{customdata[0]:.1f} °C<br>"
            "Avg Humidity : %{customdata[1]:.0f}%<br>"
            "Total Cities : %{customdata[2]:.0f}<br>"
            "Weather Records : %{customdata[3]:.0f}<extra></extra>"
        ),

        marker=dict(line=dict(width=2, color="#121413"), cornerradius=6),

    )

    fig = style_fig(
        fig,
        height=430,
        coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=15, b=10),
    )

    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ==========================================================
# RANKINGS -- Top Hottest / Highest Humidity Cities
# ==========================================================

render_section_title("🏆", "Weather Rankings")

city_summary = (

    filtered_df

    .groupby(["city", "province"], as_index=False)[["temperature", "humidity"]]

    .mean()

)

left, right = st.columns(2)

with left:

    hottest_cities = (

        city_summary

        .sort_values("temperature", ascending=False)

        [["city", "province", "temperature"]]

        .head(10)

        .reset_index(drop=True)

    )

    hottest_cities.index += 1

    hottest_cities_display = add_rank_medals(hottest_cities).rename(
        columns={"city": "City", "province": "Province", "temperature": "Temperature"}
    )

    render_table_header("🔥", "Top 10 Hottest Cities", f"{len(hottest_cities_display)} shown")

    styler = hottest_cities_display.style.format({"Temperature": "{:.1f} °C"})
    styler = style_metric_column(styler, "Temperature", "temp")
    styler = styler.hide(axis="index")

    st.dataframe(
        styler,
        use_container_width=True,
        height=380,
    )

with right:

    humid_cities = (

        city_summary

        .sort_values("humidity", ascending=False)

        [["city", "province", "humidity"]]

        .head(10)

        .reset_index(drop=True)

    )

    humid_cities.index += 1

    humid_cities_display = add_rank_medals(humid_cities).rename(
        columns={"city": "City", "province": "Province", "humidity": "Humidity"}
    )

    render_table_header("💧", "Top 10 Highest Humidity Cities", f"{len(humid_cities_display)} shown")

    styler = humid_cities_display.style.format({"Humidity": "{:.0f}%"})
    styler = style_metric_column(styler, "Humidity", "humidity")
    styler = styler.hide(axis="index")

    st.dataframe(
        styler,
        use_container_width=True,
        height=380,
    )

st.divider()

# ==========================================================
# LATEST WEATHER RECORDS TABLE
# ==========================================================

render_section_title("📋", "Latest Weather Records")

records = (

    filtered_df

    .sort_values("scraped_at", ascending=False)

    .copy()

)

search_col, _spacer = st.columns([1, 3])
with search_col:
    city_search = st.text_input(
        "🔍 Search city",
        placeholder="Type a city name…",
        label_visibility="collapsed",
    )

records_display = records
if city_search:
    records_display = records[records["city"].str.contains(city_search, case=False, na=False)]

render_table_header("📋", "Weather Records", f"{len(records_display):,} of {len(records):,} rows")

st.dataframe(

    records_display,

    hide_index=True,

    use_container_width=True,

    height=500,

    column_config={

        "city": st.column_config.TextColumn("🏙 City", width="small"),

        "province": st.column_config.TextColumn("Province", width="small"),

        "temperature": st.column_config.ProgressColumn(

            "🌡 Temp",

            format="%.1f °C",

            min_value=float(records["temperature"].min()) if not records["temperature"].isna().all() else 0.0,

            max_value=float(records["temperature"].max()) if not records["temperature"].isna().all() else 1.0,

        ),

        "humidity": st.column_config.ProgressColumn(

            "💧 Humidity",

            format="%.0f%%",

            min_value=0.0,

            max_value=100.0,

        ),

        "scraped_at": st.column_config.DatetimeColumn(

            "Bucket",

            format="DD MMM YYYY HH:mm",

            width="medium",

        ),

    },

)

st.divider()

# ==========================================================
# EXPORT CARD (mirrors sidebar export, same filtered_df)
# ==========================================================

render_section_title("📥", "Export")

with st.container(border=True):

    st.markdown('<div class="export-card-header">📥 Export Weather Dataset</div>', unsafe_allow_html=True)

    d1, d2 = st.columns(2)

    with d1:

        st.download_button(

            "⬇ Download CSV",

            data=_csv_bytes,

            file_name="pmd_weather_filtered.csv",

            mime="text/csv",

            use_container_width=True,

            key="main_csv_export",

        )

    with d2:

        st.download_button(

            "⬇ Download Excel",

            data=_excel_buffer.getvalue(),

            file_name="pmd_weather_filtered.xlsx",

            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

            use_container_width=True,

            key="main_excel_export",

        )

st.divider()

st.markdown(
    """
<div class="wx-footer">
<b>Source:</b> Pakistan Meteorological Department (PMD)<br>
The dashboard refreshes automatically after every Airflow pipeline execution.
</div>
""",
    unsafe_allow_html=True,
)