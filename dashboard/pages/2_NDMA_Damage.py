import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_damage

# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="NDMA Infrastructure Damage",
    page_icon="🏚",
    layout="wide",
)

# ==========================================================
# INFRASTRUCTURE MISSION CONTROL DESIGN SYSTEM (CSS)
# Tokens sourced 1:1 from DESIGN.md / code.html mockup.
# ==========================================================

st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>

:root{

    --im-bg: #121416;
    --im-surface-lowest: #0c0e10;
    --im-surface-low: #1a1c1e;
    --im-surface: #1e2022;
    --im-surface-high: #282a2c;
    --im-surface-highest: #333537;
    --im-surface-bright: #37393b;

    --im-on-surface: #e2e2e5;
    --im-on-surface-variant: #c1c7d0;

    --im-outline: #8b919a;
    --im-outline-variant: #41474f;

    --im-primary: #96ccff;
    --im-on-primary: #003353;
    --im-primary-container: #5b96c9;

    --im-secondary: #abcdcd;
    --im-on-secondary: #143535;
    --im-secondary-container: #2e4e4e;
    --im-on-secondary-container: #9dbfbe;

    --im-tertiary: #b9cacb;
    --im-on-tertiary-container: #1e2c2d;

    --im-error: #ffb4ab;
    --im-on-error: #690005;
    --im-error-container: #93000a;
    --im-on-error-container: #ffdad6;

    --im-radius: 0px;
    --im-radius-sm: 4px;
    --im-radius-lg: 8px;
    --im-radius-pill: 999px;

    --im-unit: 4px;
    --im-gutter: 16px;

    --im-font-sans: 'Inter', 'Segoe UI', sans-serif;
    --im-font-mono: 'JetBrains Mono', ui-monospace, monospace;

}

html, body, [class*="css"]{
    font-family: var(--im-font-sans);
    background: var(--im-bg);
}

.block-container{
    max-width: 1680px;
    padding-top: 1.25rem;
    padding-bottom: var(--im-gutter);
}

hr{
    margin-top: var(--im-gutter) !important;
    margin-bottom: var(--im-gutter) !important;
    border-color: var(--im-outline-variant) !important;
    opacity: .7 !important;
}

/* ---------------------------------------------------------
   TOP NAV BAR
   --------------------------------------------------------- */

.im-topnav{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--im-gutter);
    flex-wrap: wrap;
    background: var(--im-bg);
    border-bottom: 1px solid var(--im-outline-variant);
    padding: 10px 4px 14px 4px;
    margin: -1.25rem -1px 18px -1px;
}

.im-topnav-left{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }

.im-brand{
    font-family: var(--im-font-mono);
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -.02em;
    text-transform: uppercase;
    color: var(--im-on-surface);
}

.im-live-pill{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 5px 12px;
    border-radius: var(--im-radius-sm);
    background: var(--im-surface-high);
    border: 1px solid var(--im-outline-variant);
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .1em;
    color: var(--im-primary);
    text-transform: uppercase;
}

.im-live-pill .dot{
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--im-primary);
    animation: im-pulse 1.8s infinite;
}

@keyframes im-pulse{
    0%   { box-shadow: 0 0 0 0 rgba(150,204,255,.5); }
    70%  { box-shadow: 0 0 0 7px rgba(150,204,255,0); }
    100% { box-shadow: 0 0 0 0 rgba(150,204,255,0); }
}

.im-daterange{
    font-family: var(--im-font-mono);
    font-size: 11.5px;
    letter-spacing: .05em;
    color: var(--im-on-surface-variant);
}

.im-topnav-tabs{ display: flex; align-items: center; gap: 22px; }

.im-tab{
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    padding: 6px 2px;
    color: var(--im-on-surface-variant);
    border-bottom: 2px solid transparent;
}

.im-tab.active{ color: var(--im-primary); border-bottom-color: var(--im-primary); }

.im-topnav-right{ display: flex; align-items: center; gap: 10px; }

.im-icon-btn{
    width: 34px; height: 34px;
    display: flex; align-items: center; justify-content: center;
    border-radius: var(--im-radius-sm);
    color: var(--im-on-surface-variant);
    border: 1px solid transparent;
    font-size: 16px;
}

.im-global-alert-btn{
    padding: 7px 16px;
    background: var(--im-error-container);
    color: var(--im-on-error-container);
    border: 1px solid var(--im-error);
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    border-radius: var(--im-radius-sm);
}

/* ---------------------------------------------------------
   ALERT BANNER
   --------------------------------------------------------- */

.im-alert-banner{
    background: var(--im-error-container);
    border: 1px solid var(--im-error);
    border-radius: var(--im-radius-sm);
    padding: 16px 20px;
    margin-bottom: 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    box-shadow: 0 0 18px rgba(147,0,10,.25);
}

.im-alert-left{ display: flex; align-items: center; gap: 14px; color: var(--im-on-error-container); }

.im-alert-icon{ font-size: 26px; line-height: 1; }

.im-alert-title{
    font-family: var(--im-font-mono);
    font-size: 18px;
    font-weight: 700;
    letter-spacing: .03em;
    text-transform: uppercase;
    color: var(--im-on-error-container);
}

.im-alert-sub{
    font-size: 13px;
    color: var(--im-on-error-container);
    opacity: .9;
    margin-top: 3px;
}

.im-ack-btn{
    padding: 9px 18px;
    background: var(--im-error);
    color: var(--im-on-error);
    border: 1px solid var(--im-on-error-container);
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    border-radius: var(--im-radius-sm);
    white-space: nowrap;
}

.im-alert-banner.clear{
    background: var(--im-surface);
    border-color: var(--im-outline-variant);
    box-shadow: none;
}
.im-alert-banner.clear .im-alert-title,
.im-alert-banner.clear .im-alert-sub{ color: var(--im-on-surface); opacity: 1; }
.im-alert-banner.clear .im-alert-left{ color: var(--im-on-surface); }

/* ---------------------------------------------------------
   SECTION LABEL
   --------------------------------------------------------- */

.im-section-label{
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--im-font-mono);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--im-on-surface-variant);
    padding: 4px 2px 10px 2px;
}

/* ---------------------------------------------------------
   INDUSTRIAL CARD / KPI TILES
   --------------------------------------------------------- */

.industrial-card{
    background: var(--im-surface);
    border: 1px solid var(--im-outline-variant);
    border-radius: var(--im-radius);
}

.tile{
    background: var(--im-surface);
    border: 1px solid var(--im-outline-variant);
    padding: 14px 16px;
    height: 108px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: box-shadow .15s ease, border-color .15s ease;
}

.tile:hover{
    border-color: var(--im-primary);
    box-shadow: inset 0 0 10px rgba(150,204,255,.10);
}

.tile-label{
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--im-on-surface-variant);
}

.tile-icon{ font-size: 13px; }

.tile-value{
    font-family: var(--im-font-mono);
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -.02em;
    color: var(--im-on-surface);
    line-height: 1.05;
}

/* ---------------------------------------------------------
   OPERATIONAL INSIGHTS CARDS
   --------------------------------------------------------- */

.insight-card{
    background: var(--im-surface-high);
    border: 1px solid var(--im-outline-variant);
    border-left: 4px solid var(--im-outline-variant);
    padding: 14px 16px;
    height: 88px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 6px;
}

.insight-card.accent-error{ border-left-color: var(--im-error); }
.insight-card.accent-primary{ border-left-color: var(--im-primary); }
.insight-card.accent-neutral{ border-left-color: var(--im-outline-variant); }

.insight-label{
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
}

.insight-label.error{ color: var(--im-error); }
.insight-label.primary{ color: var(--im-primary); }
.insight-label.neutral{ color: var(--im-on-surface-variant); }

.insight-value{
    font-family: var(--im-font-mono);
    font-size: 26px;
    font-weight: 600;
    color: var(--im-on-surface);
    letter-spacing: -.01em;
}

/* ---------------------------------------------------------
   CHART CARD HEADER
   --------------------------------------------------------- */

.chart-header{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    background: var(--im-surface-high);
    border-bottom: 1px solid var(--im-outline-variant);
    padding: 9px 16px;
    font-family: var(--im-font-mono);
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--im-on-surface);
}

.chart-header-legend{ display: flex; align-items: center; gap: 14px; }

.chart-legend-item{
    display: flex; align-items: center; gap: 6px;
    font-family: var(--im-font-mono);
    font-size: 10.5px;
    font-weight: 500;
    text-transform: none;
    color: var(--im-on-surface-variant);
}

.chart-legend-dot{ width: 9px; height: 9px; border-radius: 50%; }

.chart-wrap{
    background: var(--im-surface);
    border: 1px solid var(--im-outline-variant);
    border-top: none;
    padding: 6px 10px 2px 10px;
}

div[data-testid="stPlotlyChart"]{
    background: transparent;
    border: none;
    padding: 0;
}

/* ---------------------------------------------------------
   LOLLIPOP ROWS (Damaged Houses by Province)
   --------------------------------------------------------- */

.lollipop-row{ display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }

.lollipop-label{
    font-family: var(--im-font-mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--im-on-surface);
    width: 92px;
    text-align: right;
    flex-shrink: 0;
}

.lollipop-track{ flex: 1; height: 30px; background: var(--im-bg); position: relative; }

.lollipop-fill{
    position: absolute; inset: 0 auto 0 0;
    display: flex; align-items: center; justify-content: flex-end;
    padding: 0 10px;
    font-family: var(--im-font-mono);
    font-size: 13px;
    font-weight: 600;
    transition: filter .15s ease;
}

.lollipop-fill.top{ background: var(--im-error-container); color: var(--im-on-error-container); }
.lollipop-fill.rest{ background: var(--im-surface-highest); color: var(--im-on-surface); border: 1px solid var(--im-outline-variant); }

/* ---------------------------------------------------------
   TABLES
   --------------------------------------------------------- */

.table-card-header{
    display: flex; align-items: center; justify-content: space-between;
    background: var(--im-surface-high);
    border: 1px solid var(--im-outline-variant);
    border-bottom: none;
    padding: 9px 16px;
    font-family: var(--im-font-mono);
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--im-on-surface);
}

div[data-testid="stDataFrame"]{
    border: 1px solid var(--im-outline-variant);
    border-top: none;
    border-radius: 0;
}

div[data-testid="stDataFrame"] table{
    font-family: var(--im-font-mono);
    font-size: 12.5px;
}

div[data-testid="stDataFrame"] thead tr th{
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--im-surface-high) !important;
    text-transform: uppercase;
    letter-spacing: .04em;
    font-size: 11px !important;
}

div[data-testid="stDataFrame"] tbody tr:nth-child(even) td{
    background: rgba(255,255,255,0.015);
}

div[data-testid="stDataFrame"] tbody tr:hover td{
    background: var(--im-surface-highest) !important;
    transition: background .12s ease;
}

/* ---------------------------------------------------------
   EXPORT PANEL
   --------------------------------------------------------- */

.export-panel-title{
    font-family: var(--im-font-mono);
    font-size: 18px;
    font-weight: 700;
    letter-spacing: .02em;
    text-transform: uppercase;
    color: var(--im-on-surface);
    margin-bottom: 6px;
}

.export-panel-sub{
    font-size: 13px;
    color: var(--im-on-surface-variant);
}

/* ---------------------------------------------------------
   SIDEBAR (SideNavBar equivalent — real filters live here)
   --------------------------------------------------------- */

section[data-testid="stSidebar"]{
    background: var(--im-surface-low);
    border-right: 1px solid var(--im-outline-variant);
}

section[data-testid="stSidebar"] .block-container{
    padding-top: 0;
    padding-left: 0;
    padding-right: 0;
}

.im-side-brand{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 20px 16px;
    border-bottom: 1px solid var(--im-outline-variant);
}

.im-side-avatar{
    width: 44px; height: 44px;
    border-radius: 50%;
    background: linear-gradient(155deg, var(--im-surface-highest), var(--im-surface-low));
    border: 1px solid var(--im-outline-variant);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
}

.im-side-brand-title{
    font-family: var(--im-font-mono);
    font-size: 15px;
    font-weight: 700;
    color: var(--im-on-surface);
    line-height: 1.2;
}

.im-side-brand-sub{
    font-family: var(--im-font-mono);
    font-size: 10.5px;
    letter-spacing: .05em;
    color: var(--im-on-surface-variant);
    margin-top: 2px;
}

.im-side-section{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px 8px 16px;
    border-left: 4px solid var(--im-primary);
    background: var(--im-secondary-container);
    margin: 14px 12px 0 12px;
}

.im-side-section-label{
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .07em;
    text-transform: uppercase;
    color: var(--im-on-secondary-container);
}

.im-side-body{ padding: 10px 16px 4px 16px; }

/* Sidebar section containers -- these target the REAL Streamlit
   containers created with st.sidebar.container(key=...) further
   down the page. Using an actual container (a real DOM parent) is
   what makes the header label and the widgets inside it render as
   one visual block; the previous approach (opening a <div> with one
   st.sidebar.markdown() call, adding widgets, then closing the <div>
   with a second, unrelated st.sidebar.markdown() call) never worked
   because every st.sidebar.* call is an independent sibling in the
   DOM -- there is no way for a later call to "close" an element
   opened by an earlier, separate call. */
section[data-testid="stSidebar"] [class*="st-key-sb_temporal_range"],
section[data-testid="stSidebar"] [class*="st-key-sb_regional_sectors"]{
    padding: 10px 16px 4px 16px;
}

section[data-testid="stSidebar"] label{
    font-size: 12px !important;
    color: var(--im-on-surface-variant) !important;
    font-family: var(--im-font-mono) !important;
    text-transform: uppercase;
    letter-spacing: .04em;
}

section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div{
    border-radius: var(--im-radius-sm) !important;
    background: var(--im-bg) !important;
    border-color: var(--im-outline-variant) !important;
    color: var(--im-on-surface) !important;
}

section[data-testid="stSidebar"] div[data-baseweb="tag"]{
    background: var(--im-primary-container) !important;
    border-radius: var(--im-radius-sm) !important;
}

.im-side-stats{
    margin: 16px 12px 12px 12px;
    padding: 12px 14px;
    background: var(--im-surface);
    border: 1px solid var(--im-outline-variant);
}

.im-stat-row{
    display: flex; align-items: center; justify-content: space-between;
    font-size: 12px;
    padding: 4px 0;
    color: var(--im-on-surface-variant);
    font-family: var(--im-font-mono);
}

.im-stat-row b{ color: var(--im-on-surface); }

.im-side-export-label{
    font-family: var(--im-font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .07em;
    text-transform: uppercase;
    color: var(--im-on-surface-variant);
    padding: 4px 16px 8px 16px;
}

/* ---------------------------------------------------------
   NATIVE ELEMENT OVERRIDES
   --------------------------------------------------------- */

div[data-testid="stMetric"]{
    background: var(--im-surface);
    border: 1px solid var(--im-outline-variant);
    border-radius: 0;
    padding: 10px 14px;
}

div[data-testid="stMetric"] label{
    font-family: var(--im-font-mono) !important;
    text-transform: uppercase;
    letter-spacing: .05em;
}

div[data-testid="stAlert"]{
    background: var(--im-surface);
    border: 1px solid var(--im-outline-variant);
    border-radius: var(--im-radius-sm);
}

.stButton > button, .stDownloadButton > button{
    border-radius: var(--im-radius-sm);
    font-family: var(--im-font-mono);
    font-weight: 700;
    letter-spacing: .05em;
    text-transform: uppercase;
    font-size: 11.5px;
    border: 1px solid var(--im-outline-variant);
    background: transparent;
    color: var(--im-on-surface);
    transition: border-color .15s ease, color .15s ease;
}

.stButton > button:hover, .stDownloadButton > button:hover{
    border-color: var(--im-primary);
    color: var(--im-primary);
}

/* ---------------------------------------------------------
   FOOTER
   --------------------------------------------------------- */

.im-footer{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    background: var(--im-surface-low);
    border-top: 1px solid var(--im-outline-variant);
    padding: 12px 4px;
    margin-top: 10px;
}

.im-footer-brand{
    font-family: var(--im-font-mono);
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--im-on-surface);
}

.im-footer-links{ display: flex; gap: 20px; }

.im-footer-links span{
    font-size: 12px;
    color: var(--im-secondary);
}

/* ---------------------------------------------------------
   RESPONSIVE
   --------------------------------------------------------- */

@media (max-width: 1400px){
    .block-container{ padding-left: var(--im-gutter); padding-right: var(--im-gutter); }
}

@media (max-width: 1024px){
    .im-brand{ font-size: 18px; }
    .im-topnav{ flex-direction: column; align-items: flex-start; }
    .tile{ height: auto; min-height: 96px; }
    .insight-card{ height: auto; min-height: 76px; }
}

</style>
""",
    unsafe_allow_html=True,
)

# ==========================================================
# UI HELPER FUNCTIONS (presentation only — no business logic)
# ==========================================================

def render_topnav(brand: str, date_range_label: str) -> None:
    st.markdown(
        f"""
<div class="im-topnav">
  <div class="im-topnav-left">
    <span class="im-brand">{brand}</span>
    <span class="im-live-pill"><span class="dot"></span> Live System</span>
    <span class="im-daterange">Data Range: {date_range_label}</span>
  </div>
  <div class="im-topnav-tabs">
    <span class="im-tab active">Dashboard</span>
    <span class="im-tab">Reports</span>
    <span class="im-tab">Alerts</span>
  </div>
  <div class="im-topnav-right">
    <div class="im-icon-btn">🔄</div>
    <div class="im-icon-btn">🛟</div>
    <div class="im-global-alert-btn">Global Alert</div>
    <div class="im-icon-btn">👤</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_alert_banner(title: str, subtitle: str, variant: str = "danger") -> None:
    css_class = "im-alert-banner" if variant == "danger" else "im-alert-banner clear"
    icon = "⚠" if variant == "danger" else "✓"
    ack = '<div class="im-ack-btn">Acknowledge</div>' if variant == "danger" else ""
    st.markdown(
        f"""
<div class="{css_class}">
  <div class="im-alert-left">
    <span class="im-alert-icon">{icon}</span>
    <div>
      <div class="im-alert-title">{title}</div>
      <div class="im-alert-sub">{subtitle}</div>
    </div>
  </div>
  {ack}
</div>
""",
        unsafe_allow_html=True,
    )


def render_section_label(icon: str, title: str) -> None:
    st.markdown(f'<div class="im-section-label">{icon} {title}</div>', unsafe_allow_html=True)


def render_kpi_tile(icon: str, label: str, value: str) -> str:
    return f"""
<div class="tile">
  <div class="tile-label"><span class="tile-icon">{icon}</span>{label}</div>
  <div class="tile-value">{value}</div>
</div>
"""


def render_insight_card(label: str, value: str, accent: str = "neutral") -> str:
    return f"""
<div class="insight-card accent-{accent}">
  <div class="insight-label {accent}">{label}</div>
  <div class="insight-value">{value}</div>
</div>
"""


def render_chart_header(icon: str, title: str, legend_items=None) -> None:
    legend_html = ""
    if legend_items:
        chips = "".join(
            f'<span class="chart-legend-item"><span class="chart-legend-dot" style="background:{color};"></span>{name}</span>'
            for name, color in legend_items
        )
        legend_html = f'<div class="chart-header-legend">{chips}</div>'
    st.markdown(
        f"""
<div class="chart-header">
  <span>{icon} {title}</span>
  {legend_html}
</div>
""",
        unsafe_allow_html=True,
    )


def render_table_header(icon: str, title: str) -> None:
    st.markdown(f'<div class="table-card-header">{icon} {title}</div>', unsafe_allow_html=True)


_PLOTLY_FONT = dict(family="Inter, sans-serif", size=12, color="#c1c7d0")

_PLOTLY_LAYOUT_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=_PLOTLY_FONT,
    hoverlabel=dict(
        bgcolor="#1e2022",
        bordercolor="#41474f",
        font=dict(family="JetBrains Mono, monospace", size=12, color="#e2e2e5"),
    ),
)


def style_fig(fig, **layout_overrides):
    """Applies the shared Mission Control chart cosmetics. Never touches trace data."""
    fig.update_layout(**_PLOTLY_LAYOUT_BASE)
    fig.update_layout(**layout_overrides)
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def style_rank_table(df_in: pd.DataFrame, rank_col: str, highlight_col: str, numeric_cols: list):
    """
    Sticky header / hover come from CSS above. This adds right-aligned
    numeric columns and highlights the #1 ranked row's name in the
    error accent, exactly as the mockup does for its top row.
    """
    styler = df_in.style
    styler = styler.set_properties(subset=numeric_cols, **{"text-align": "right"})
    styler = styler.set_properties(subset=[rank_col], **{"text-align": "center", "color": "#c1c7d0"})

    def _highlight_top(row):
        if row.name == df_in.index[0]:
            return [f"color:#ffb4ab; font-weight:700;" if col == highlight_col else "" for col in df_in.columns]
        return ["" for _ in df_in.columns]

    styler = styler.apply(_highlight_top, axis=1)
    return styler


# ==========================================================
# LOAD DATABASE -- EXACTLY ONCE
# ==========================================================

try:

    df = get_damage()

except Exception as e:

    st.error(e)

    st.stop()

if df.empty:

    st.warning("No NDMA Infrastructure Damage data available.")

    st.stop()

# ==========================================================
# DATA CLEANING
# ==========================================================

df = df.copy()

df["report_date"] = pd.to_datetime(df["report_date"])

numeric_columns = [

    "roads_km",

    "bridges",

    "houses_total",

    "livestock",

]

for col in numeric_columns:

    df[col] = pd.to_numeric(

        df[col],

        errors="coerce",

    ).fillna(0)

df["province"] = (

    df["province"]

    .fillna("Unknown")

    .astype(str)

)

# ==========================================================
# TOP NAV
# ==========================================================

render_topnav(
    "INFRA-INTEL OPS",
    f"{df['report_date'].min().strftime('%d %b %Y')} – {df['report_date'].max().strftime('%d %b %Y')}",
)

# ==========================================================
# SIDEBAR -- ONLY THE 5 ALLOWED FILTERS (restyled as the
# mockup's fixed side nav, real widgets underneath)
# ==========================================================

st.sidebar.markdown(
    """
<div class="im-side-brand">
  <div class="im-side-avatar">🛡</div>
  <div>
    <div class="im-side-brand-title">NDMA OPS</div>
    <div class="im-side-brand-sub">INFRASTRUCTURE INTELLIGENCE</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

min_date = df["report_date"].min().date()
max_date = df["report_date"].max().date()

# NOTE ON THE FIX: st.sidebar.container(key=...) creates one real
# Streamlit container. Everything called with the plain (non-sidebar-
# prefixed) st.* API inside the `with` block below is mounted as an
# actual DOM child of that container -- so the header label and the
# widgets underneath it are genuinely nested together, and the CSS
# rule added above (targeting the container's "st-key-..." class)
# reliably wraps all of them. This replaces the previous pattern of
# opening a <div> with one markdown call and "closing" it with a
# second, unrelated markdown call after the widgets, which never
# actually wrapped anything.
with st.sidebar.container(key="sb_temporal_range"):

    st.markdown(
        '<div class="im-side-section"><span class="im-side-section-label">🕒 Temporal Range</span></div>',
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

    aggregation = st.selectbox(

        "Aggregation",

        ["Hourly", "Daily", "Weekly", "Monthly", "Yearly"],

        index=1,

    )

with st.sidebar.container(key="sb_regional_sectors"):

    st.markdown(
        """
        <div class="im-side-section">
            <span class="im-side-section-label">
                🗺 Regional Sectors
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    province_list = sorted(df["province"].dropna().unique())

    # Single dropdown (same UI as Aggregation)
    selected_province = st.selectbox(
        "Province",
        options=["All Provinces"] + province_list,
        index=0,
    )

    # Convert dropdown value into list
    if selected_province == "All Provinces":
        selected_provinces = province_list
    else:
        selected_provinces = [selected_province]

_FREQ_MAP = {
    "Hourly": "h",
    "Daily": "D",
    "Weekly": "W",
    "Monthly": "ME",
    "Yearly": "YE",
}

freq = _FREQ_MAP[aggregation]
# ==========================================================
# BUILD filtered_df -- THE SINGLE SOURCE OF TRUTH
# Every KPI / chart / table / export below reads ONLY from this.
# ==========================================================

start_ts = pd.to_datetime(start_date)
end_ts = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

filtered_df = df[
    (df["report_date"] >= start_ts)
    &
    (df["report_date"] <= end_ts)
]

# Province Filter
if selected_provinces:
    filtered_df = filtered_df[
        filtered_df["province"].isin(selected_provinces)
    ]

# Stop if no data
if filtered_df.empty:
    st.warning("No records found for selected filters.")
    st.stop()

# ==========================================================
# SIDEBAR STATS
# ==========================================================

with st.sidebar.container():

    st.markdown("### 📊 Statistics")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="Provinces",
            value=filtered_df["province"].nunique()
        )

    with col2:
        st.metric(
            label="Reports",
            value=f"{len(filtered_df):,}"
        )

    st.metric(
        label="Date Range",
        value=f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"
    )
# ==========================================================
# SIDEBAR -- EXPORT
# ==========================================================

st.sidebar.markdown('<div class="im-side-export-label">📥 Export</div>', unsafe_allow_html=True)

_csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")

st.sidebar.download_button(
    "⬇ CSV",
    data=_csv_bytes,
    file_name="ndma_damage_filtered.csv",
    mime="text/csv",
    use_container_width=True,
)

_excel_buffer = io.BytesIO()

with pd.ExcelWriter(_excel_buffer, engine="openpyxl") as _writer:

    filtered_df.to_excel(_writer, index=False, sheet_name="NDMA Damage")

st.sidebar.download_button(
    "⬇ Excel",
    data=_excel_buffer.getvalue(),
    file_name="ndma_damage_filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
    key="sidebar_excel_export",
)

# ==========================================================
# SUMMARY VALUES (computed ONLY from filtered_df)
# ==========================================================

latest_date = filtered_df["report_date"].max()

province_summary = (

    filtered_df

    .groupby("province", as_index=False)[

        [

            "houses_total",

            "roads_km",

            "bridges",

            "livestock",

        ]

    ]

    .sum()

)

total_houses = int(filtered_df["houses_total"].sum())

total_roads = round(filtered_df["roads_km"].sum(), 1)

total_bridges = int(filtered_df["bridges"].sum())

total_livestock = int(filtered_df["livestock"].sum())

total_records = len(filtered_df)

province_count = filtered_df["province"].nunique()

top_province = (

    province_summary

    .sort_values("houses_total", ascending=False)

    .iloc[0]["province"]

)

# ==========================================================
# ALERT BANNER -- driven by real data: fires when the top
# province's share of total houses damaged crosses a threshold,
# instead of the mockup's static demo copy. No values fabricated.
# ==========================================================

top_house_share = (
    province_summary.sort_values("houses_total", ascending=False).iloc[0]["houses_total"]
    / total_houses * 100
    if total_houses > 0 else 0
)

if top_house_share >= 30:
    render_alert_banner(
        "Critical Infrastructure Risk",
        f"{top_province} accounts for {top_house_share:.0f}% of houses damaged in the selected "
        f"window ({int(province_summary.sort_values('houses_total', ascending=False).iloc[0]['houses_total']):,} of {total_houses:,}). "
        f"Immediate resource allocation recommended.",
        variant="danger",
    )
else:
    render_alert_banner(
        "No Critical Concentration Detected",
        f"Damage is distributed across {province_count} province(s) in the selected window; "
        f"{top_province} holds the largest share at {top_house_share:.0f}%.",
        variant="clear",
    )

# ==========================================================
# KPI COMMAND TILES (6, matching the mockup) -- houses_total is
# the only damage granularity available; there is no fully/
# partially split column in ndma_damage, so those two KPIs are
# not shown (same limitation as before).
# ==========================================================

k1, k2, k3, k4, k5, k6 = st.columns(6)

with k1:
    st.markdown(render_kpi_tile("🏠", "Houses Damaged", f"{total_houses:,}"), unsafe_allow_html=True)

with k2:
    st.markdown(render_kpi_tile("🛣", "Roads (KM)", f"{total_roads:,.1f}"), unsafe_allow_html=True)

with k3:
    st.markdown(render_kpi_tile("🌉", "Bridges", f"{total_bridges:,}"), unsafe_allow_html=True)

with k4:
    st.markdown(render_kpi_tile("🐄", "Livestock Lost", f"{total_livestock:,}"), unsafe_allow_html=True)

with k5:
    st.markdown(render_kpi_tile("🗺", "Active Sectors", f"{province_count}"), unsafe_allow_html=True)

with k6:
    st.markdown(render_kpi_tile("📄", "Total Reports", f"{total_records:,}"), unsafe_allow_html=True)

st.divider()

# ==========================================================
# OPERATIONAL INSIGHTS ROW (4 cards, matching the mockup)
# ==========================================================

asset_scores = {

    "Houses": total_houses * 1,

    "Roads": total_roads * 10,

    "Bridges": total_bridges * 100,

    "Livestock": total_livestock * 2,

}

critical_asset = max(asset_scores, key=asset_scores.get)

critical_asset_share = (

    asset_scores[critical_asset]
    / sum(asset_scores.values())
    * 100

    if sum(asset_scores.values()) > 0
    else 0

)

# "Recovery Readiness" — derived from whether the filtered window's
# latest report matches the overall dataset's latest report (i.e.
# the view is current vs. looking at a historical window). Real,
# not fabricated: comparison of two already-computed real dates.
is_current_window = latest_date == df["report_date"].max()
readiness_label = "ACTIVE" if is_current_window else "HISTORICAL"
readiness_accent = "primary" if is_current_window else "neutral"

i1, i2, i3, i4 = st.columns(4)

with i1:
    st.markdown(render_insight_card("Highest Damage Province", top_province, "error"), unsafe_allow_html=True)

with i2:
    st.markdown(render_insight_card("Network Impact", f"{critical_asset_share:.0f}%", "primary"), unsafe_allow_html=True)

with i3:
    st.markdown(render_insight_card("Recovery Readiness", readiness_label, readiness_accent), unsafe_allow_html=True)

with i4:
    st.markdown(render_insight_card("Latest Data Sync", latest_date.strftime("%d %b").upper(), "neutral"), unsafe_allow_html=True)

st.divider()

# ==========================================================
# TIME-BUCKETED VIEWS (ONLY from filtered_df, obey Aggregation)
# ==========================================================

trend_df = (

    filtered_df

    .groupby(pd.Grouper(key="report_date", freq=freq))[

        ["houses_total", "roads_km", "bridges", "livestock"]

    ]

    .sum()

    .reset_index()

)

# ==========================================================
# MAIN CHART AREA -- Lollipop (4 cols) + Trend (8 cols)
# ==========================================================

render_section_label("📡", "Main Analytics")

p1, p2 = st.columns([4, 8])

# ----------------------------------------------------------
# 1. DAMAGED HOUSES BY PROVINCE (lollipop-style horizontal bars,
#    top province highlighted in the error accent — matches mockup)
# ----------------------------------------------------------

with p1:

    render_chart_header("📊", "Damaged Houses by Province")

    ranking = province_summary.sort_values("houses_total", ascending=False).reset_index(drop=True)

    bar_colors = ["#93000a" if i == 0 else "#333537" for i in range(len(ranking))]
    line_colors = ["#ffb4ab" if i == 0 else "#41474f" for i in range(len(ranking))]
    text_colors = ["#ffdad6" if i == 0 else "#e2e2e5" for i in range(len(ranking))]

    fig = go.Figure(
        go.Bar(
            x=ranking["houses_total"],
            y=ranking["province"],
            orientation="h",
            text=ranking["houses_total"].map(lambda v: f"{int(v):,}"),
            textposition="inside",
            insidetextanchor="end",
            textfont=dict(color=text_colors, family="JetBrains Mono, monospace", size=13),
            marker=dict(color=bar_colors, line=dict(color=line_colors, width=1)),
            hovertemplate="<b>%{y}</b><br>Damaged Houses : %{x:,}<extra></extra>",
        )
    )

    fig = style_fig(
        fig,
        height=470,
        yaxis=dict(autorange="reversed", title=""),
        xaxis_title="",
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        bargap=0.35,
    )

    st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------
# 2. INFRASTRUCTURE DAMAGE TREND OVER TIME (dual-axis: Houses
#    primary + Roads secondary shown by default, Bridges kept
#    available via legend-toggle so no data is dropped)
# ----------------------------------------------------------

with p2:

    render_chart_header(
        "📈",
        f"Infrastructure Damage Trend ({aggregation})",
        legend_items=[("Houses", "#96ccff"), ("Roads", "#abcdcd")],
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=trend_df["report_date"],
            y=trend_df["houses_total"],
            name="Houses",
            mode="lines+markers",
            line=dict(width=3, color="#96ccff", shape="spline", smoothing=0.5),
            marker=dict(size=5, color="#96ccff"),
            fill="tozeroy",
            fillcolor="rgba(150,204,255,0.10)",
            hovertemplate="Houses : %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=trend_df["report_date"],
            y=trend_df["roads_km"],
            name="Roads (km)",
            mode="lines+markers",
            line=dict(width=2.5, color="#abcdcd"),
            marker=dict(size=5, color="#abcdcd"),
            hovertemplate="Roads : %{y:,.1f} km<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.add_trace(
        go.Scatter(
            x=trend_df["report_date"],
            y=trend_df["bridges"],
            name="Bridges",
            mode="lines+markers",
            line=dict(width=2.5, color="#b9cacb", dash="dot"),
            marker=dict(size=5, color="#b9cacb"),
            visible="legendonly",
            hovertemplate="Bridges : %{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(**_PLOTLY_LAYOUT_BASE)
    fig.update_layout(
        height=470,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", title="")
    fig.update_yaxes(title_text="Houses", gridcolor="rgba(255,255,255,0.06)", secondary_y=False)
    fig.update_yaxes(title_text="Roads (km) / Bridges", gridcolor="rgba(0,0,0,0)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ==========================================================
# SECONDARY CHARTS ROW -- Roads vs Bridges (butterfly/grouped
# horizontal bar) + Infrastructure Distribution (polar chart)
# ==========================================================

render_section_label("🌐", "Secondary Analytics")

s1, s2 = st.columns(2)

with s1:

    render_chart_header("🔀", "Roads vs Bridges by Province")

    stacked = province_summary.sort_values("houses_total", ascending=False)

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Roads (km)",
            y=stacked["province"],
            x=stacked["roads_km"],
            orientation="h",
            marker_color="#96ccff",
            hovertemplate="<b>%{y}</b><br>Roads : %{x:,.1f} km<extra></extra>",
        )
    )

    fig.add_trace(
        go.Bar(
            name="Bridges",
            y=stacked["province"],
            x=stacked["bridges"],
            orientation="h",
            marker_color="#abcdcd",
            hovertemplate="<b>%{y}</b><br>Bridges : %{x:,}<extra></extra>",
        )
    )

    fig = style_fig(
        fig,
        height=340,
        barmode="group",
        bargap=0.3,
        xaxis_title="",
        yaxis=dict(autorange="reversed", title=""),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
    )

    st.plotly_chart(fig, use_container_width=True)

with s2:

    render_chart_header("◎", "Infrastructure Distribution")

    dist_labels = ["Houses", "Roads", "Bridges", "Livestock"]
    dist_values = [total_houses, total_roads, total_bridges, total_livestock]
    dist_colors = ["#96ccff", "#abcdcd", "#b9cacb", "#ffb4ab"]

    fig = go.Figure()

    for label, value, color in zip(dist_labels, dist_values, dist_colors):
        fig.add_trace(
            go.Barpolar(
                r=[value],
                theta=[label],
                name=label,
                marker_color=color,
                marker_line_color="#121416",
                marker_line_width=2,
                opacity=0.85,
                hovertemplate=f"<b>{label}</b><br>Total : %{{r:,.0f}}<extra></extra>",
            )
        )

    fig.update_layout(**_PLOTLY_LAYOUT_BASE)
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=10, b=10),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(showticklabels=False, gridcolor="rgba(255,255,255,0.08)"),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        ),
        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)"),
        showlegend=True,
    )

    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ==========================================================
# PROVINCE RANKING -- TOP PROVINCES BY INFRASTRUCTURE DAMAGE
# (reuses the existing Damage Score formula already established
# on this page: houses*1 + roads*10 + bridges*100 + livestock*2)
# ==========================================================

render_table_header("🏆", "Province Ranking — Top Damage")

summary = province_summary.copy()

summary["Damage Score"] = (

    summary["houses_total"]

    +

    summary["roads_km"] * 10

    +

    summary["bridges"] * 100

    +

    summary["livestock"] * 2

).round(0)

summary = summary.sort_values("Damage Score", ascending=False).reset_index(drop=True)

summary.index += 1

summary.rename(

    columns={

        "province": "Province",

        "houses_total": "Houses",

        "roads_km": "Roads (km)",

        "bridges": "Bridges",

        "livestock": "Livestock",

    },

    inplace=True,

)

summary.insert(0, "#", summary.index)

_numeric_cols = ["Houses", "Roads (km)", "Bridges", "Livestock", "Damage Score"]

styler = style_rank_table(summary, rank_col="#", highlight_col="Province", numeric_cols=_numeric_cols)
styler = styler.format({
    "Houses": "{:,.0f}",
    "Roads (km)": "{:,.2f}",
    "Bridges": "{:,.0f}",
    "Livestock": "{:,.0f}",
    "Damage Score": "{:,.0f}",
})
styler = styler.hide(axis="index")

st.dataframe(
    styler,
    use_container_width=True,
    height=340,
)

st.divider()

# ==========================================================
# LATEST DAMAGE RECORDS TABLE
# ==========================================================

render_table_header("📋", "Latest Damage Records")

records = (

    filtered_df

    .sort_values("report_date", ascending=False)

    .copy()

)

records.rename(

    columns={

        "report_date": "Report Date",

        "province": "Province",

        "houses_total": "Houses",

        "roads_km": "Roads (km)",

        "bridges": "Bridges",

        "livestock": "Livestock",

    },

    inplace=True,

)

_records_numeric = ["Houses", "Roads (km)", "Bridges", "Livestock"]

records_styler = records.style.set_properties(subset=_records_numeric, **{"text-align": "right"})
records_styler = records_styler.format({
    "Houses": "{:,.0f}",
    "Roads (km)": "{:,.2f}",
    "Bridges": "{:,.0f}",
    "Livestock": "{:,.0f}",
    "Report Date": lambda d: d.strftime("%d %b %Y"),
})
records_styler = records_styler.hide(axis="index")

st.dataframe(
    records_styler,
    use_container_width=True,
    height=380,
)

st.divider()

# ==========================================================
# EXPORT PANEL (mirrors sidebar export, same filtered_df)
# ==========================================================

with st.container(border=True):

    ex1, ex2 = st.columns([2, 1])

    with ex1:
        st.markdown('<div class="export-panel-title">📥 Export Filtered Dataset</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="export-panel-sub">Latest report: {latest_date.strftime("%d %b %Y")}. '
            f'Aggregation: {aggregation}. Exported files contain the filtered infrastructure damage dataset.</div>',
            unsafe_allow_html=True,
        )

    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric("Provinces", province_count)

    with m2:
        st.metric("Houses", f"{total_houses:,}")

    with m3:
        st.metric("Roads (km)", f"{total_roads:,.1f}")

    with m4:
        st.metric("Records", f"{total_records:,}")

    d1, d2 = st.columns(2)

    with d1:

        st.download_button(

            "⬇ Download CSV",

            data=_csv_bytes,

            file_name="ndma_damage_filtered.csv",

            mime="text/csv",

            use_container_width=True,

            key="main_csv_export",

        )

    with d2:

        st.download_button(

            "⬇ Download Excel",

            data=_excel_buffer.getvalue(),

            file_name="ndma_damage_filtered.xlsx",

            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

            use_container_width=True,

            key="main_excel_export",

        )

st.markdown(
    """
<div class="im-footer">
  <span class="im-footer-brand">NDMA Infrastructure Hub</span>
  <div class="im-footer-links">
    <span>Platform Metadata</span>
    <span>Production Environment</span>
    <span>Security Policy</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)