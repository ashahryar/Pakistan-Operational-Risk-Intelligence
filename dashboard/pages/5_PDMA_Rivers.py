"""
dashboard/pages/5_PDMA_Rivers.py

PDMA River Intelligence -- Business Intelligence Command Center.

Preserves the existing "Executive Command Surface" CSS/theme, page
config, auto-refresh, navigation, and download-button styling. Only
the analytics pipeline and filters were rebuilt: get_gauge() and
calculate_risk() are unchanged, and every KPI/chart/ranking/heatmap/
table/export below reads from exactly one dataframe, filtered_df.
"""

import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    AUTO_REFRESH = True
except Exception:
    AUTO_REFRESH = False

from dashboard.db import get_gauge

# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="PDMA River Intelligence",
    page_icon="🌊",
    layout="wide",
)

# ==========================================================
# AUTO REFRESH
# ==========================================================

if AUTO_REFRESH:

    st_autorefresh(
        interval=60000,
        key="river_refresh",
    )

# ==========================================================
# COMMAND SURFACE DESIGN SYSTEM (CSS) -- unchanged
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
    --cs-surface-low: #1a1c1c;
    --cs-surface-high: #292a2a;
    --cs-surface-highest: #343535;

    --cs-on-surface: #e3e2e1;
    --cs-on-surface-variant: #c4c6cd;

    --cs-outline: #8e9197;
    --cs-outline-variant: #44474d;

    --cs-primary: #b5c8e5;
    --cs-on-primary: #1f3148;
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

.block-container{
    max-width: 1600px;
    padding-top: var(--cs-space-4);
    padding-bottom: var(--cs-space-6);
}

hr{
    margin-top: var(--cs-space-4) !important;
    margin-bottom: var(--cs-space-4) !important;
    border-color: var(--cs-outline-variant) !important;
    opacity: .5 !important;
}

/* ---------------------------------------------------------
   HEADER
   --------------------------------------------------------- */

.riv-header{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--cs-space-4);
    flex-wrap: wrap;
}

.riv-title-block{
    display: flex;
    align-items: center;
    gap: var(--cs-space-3);
}

.riv-title-icon{
    font-size: 30px;
    line-height: 1;
}

.riv-main-title{
    font-family: var(--cs-font-mono);
    font-size: 26px;
    font-weight: 700;
    letter-spacing: .02em;
    color: var(--cs-on-surface);
    margin: 0;
}

.riv-subtitle{
    font-size: 13px;
    color: var(--cs-on-surface-variant);
    margin-top: 2px;
    letter-spacing: .01em;
}

.riv-header-right{
    display: flex;
    align-items: center;
    gap: var(--cs-space-4);
}

.riv-live-badge{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 16px;
    border-radius: var(--cs-radius-pill);
    background: var(--cs-success-container);
    color: var(--cs-on-success-container);
    font-family: var(--cs-font-mono);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
}

.riv-live-badge .dot{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--cs-success);
    box-shadow: 0 0 0 0 rgba(121,221,104,.5);
    animation: riv-pulse 1.8s infinite;
}

@keyframes riv-pulse{
    0%   { box-shadow: 0 0 0 0 rgba(121,221,104,.5); }
    70%  { box-shadow: 0 0 0 7px rgba(121,221,104,0); }
    100% { box-shadow: 0 0 0 0 rgba(121,221,104,0); }
}

.riv-update-block{
    text-align: right;
}

.riv-update-label{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--cs-on-surface-variant);
}

.riv-update-value{
    font-family: var(--cs-font-mono);
    font-size: 15px;
    font-weight: 600;
    color: var(--cs-on-surface);
}

/* ---------------------------------------------------------
   COMMAND TILES (KPI cards)
   --------------------------------------------------------- */

.tile{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-left: 4px solid var(--cs-outline);
    border-radius: var(--cs-radius);
    padding: var(--cs-space-4);
    height: 128px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: transform .18s ease, border-color .18s ease, background .18s ease;
}

.tile:hover{
    transform: translateY(-2px);
    background: var(--cs-surface-high);
}

.tile-danger{ border-left-color: var(--cs-danger); }
.tile-warning{ border-left-color: var(--cs-warning); }
.tile-success{ border-left-color: var(--cs-success); }
.tile-primary{ border-left-color: var(--cs-primary); }

.tile-head{
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.tile-label{
    font-family: var(--cs-font-mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
}

.tile-value{
    font-family: var(--cs-font-mono);
    font-size: 26px;
    font-weight: 700;
    color: var(--cs-on-surface);
    line-height: 1;
    margin: 6px 0;
}

.tile-value.danger{ color: var(--cs-danger); }
.tile-value.warning{ color: var(--cs-warning); }
.tile-value.success{ color: var(--cs-success); }

.tile-foot{
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    color: var(--cs-on-surface-variant);
}

.tile-foot .tag{
    font-family: var(--cs-font-mono);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
}

.tile-foot .tag.danger{ color: var(--cs-danger); }
.tile-foot .tag.success{ color: var(--cs-success); }

/* ---------------------------------------------------------
   EXECUTIVE SUMMARY CARDS (4-card)
   --------------------------------------------------------- */

.exec-card{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: var(--cs-space-4);
    height: 168px;
    display: flex;
    flex-direction: column;
    transition: box-shadow .18s ease, transform .18s ease;
}

.exec-card:hover{
    transform: translateY(-2px);
}

.exec-card-danger{ border-top: 3px solid var(--cs-danger); }
.exec-card-success{ border-top: 3px solid var(--cs-success); }
.exec-card-primary{ border-top: 3px solid var(--cs-primary); }
.exec-card-warning{ border-top: 3px solid var(--cs-warning); }

.exec-card-title{
    font-family: var(--cs-font-mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    margin-bottom: var(--cs-space-3);
}

.exec-card-row{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 5px 0;
    font-size: 13px;
    color: var(--cs-on-surface-variant);
    border-bottom: 1px solid rgba(255,255,255,0.05);
}

.exec-card-row:last-child{
    border-bottom: none;
}

.exec-card-row b{
    font-family: var(--cs-font-mono);
    font-size: 14px;
    color: var(--cs-on-surface);
    font-weight: 600;
}

/* ---------------------------------------------------------
   CHART CONTAINERS (2x2 grid)
   --------------------------------------------------------- */

.chart-tile-header{
    font-family: var(--cs-font-mono);
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
    padding: 2px 4px 10px 4px;
}

div[data-testid="stPlotlyChart"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: var(--cs-space-3);
}

/* ---------------------------------------------------------
   TABLE CONTAINERS
   --------------------------------------------------------- */

.table-tile-header{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--cs-surface-high);
    border: 1px solid var(--cs-outline-variant);
    border-bottom: none;
    border-radius: var(--cs-radius-lg) var(--cs-radius-lg) 0 0;
    padding: 10px var(--cs-space-4);
    font-family: var(--cs-font-mono);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
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

/* ---------------------------------------------------------
   EXPORT CARD
   --------------------------------------------------------- */

.export-card{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
    padding: var(--cs-space-4) var(--cs-space-4) var(--cs-space-2) var(--cs-space-4);
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

section[data-testid="stSidebar"] h2{
    font-family: var(--cs-font-mono);
    font-size: 12px;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--cs-on-surface-variant);
}

/* ---------------------------------------------------------
   NATIVE ELEMENT OVERRIDES
   --------------------------------------------------------- */

div[data-testid="stMetric"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius);
    padding: var(--cs-space-3) var(--cs-space-4);
}

div[data-testid="stAlert"]{
    background: var(--cs-surface);
    border: 1px solid var(--cs-outline-variant);
    border-radius: var(--cs-radius-lg);
}

.stButton > button, .stDownloadButton > button{
    border-radius: var(--cs-radius);
    font-family: var(--cs-font-mono);
    font-weight: 600;
    letter-spacing: .03em;
    text-transform: uppercase;
    font-size: 12.5px;
}

/* ---------------------------------------------------------
   RESPONSIVE
   --------------------------------------------------------- */

@media (max-width: 1400px){
    .block-container{ padding-left: var(--cs-space-4); padding-right: var(--cs-space-4); }
    .tile{ height: auto; min-height: 120px; }
    .exec-card{ height: auto; min-height: 150px; }
}

@media (max-width: 1024px){
    .riv-main-title{ font-size: 21px; }
    .riv-header{ flex-direction: column; align-items: flex-start; }
    .riv-header-right{ width: 100%; justify-content: space-between; }
    .tile, .exec-card{ height: auto; }
}

</style>
""",
    unsafe_allow_html=True,
)

# ==========================================================
# LOAD DATA -- ONE SQL QUERY, ONE TIME (get_gauge() unchanged)
# ==========================================================

with st.spinner("Loading latest river monitoring data..."):

    try:

        df = get_gauge()

    except Exception as e:

        st.error(f"Database Error\n\n{e}")
        st.stop()

if df.empty:

    st.warning("No river monitoring data available.")
    st.stop()

# ==========================================================
# DATA CLEANING
# ==========================================================

df = df.copy()

df["report_datetime"] = pd.to_datetime(
    df["report_datetime"],
    errors="coerce",
)

numeric_cols = [

    "current_level_ft",
    "danger_level_ft",
    "discharge_cusecs",

]

for col in numeric_cols:

    if col in df.columns:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

df["station"] = (

    df["station"]
    .fillna("Unknown")
    .astype(str)
    .str.strip()

)

df["river"] = (

    df["river"]
    .fillna("Unknown")
    .astype(str)
    .str.strip()

)

df["flow_status"] = (

    df["flow_status"]
    .fillna("Unknown")
    .astype(str)
    .str.strip()

)

df = df.dropna(subset=["report_datetime", "station"])

# ==========================================================
# RISK CALCULATION -- unchanged
# ==========================================================

def calculate_risk(row):

    if pd.isna(row["current_level_ft"]) or pd.isna(row["danger_level_ft"]):
        return "Unknown"

    ratio = row["current_level_ft"] / row["danger_level_ft"]

    if ratio >= 1:
        return "Danger"

    elif ratio >= 0.80:
        return "Watch"

    return "Normal"

latest_update = df["report_datetime"].max()

# ==========================================================
# HEADER
# ==========================================================

st.markdown(
    f"""
<div class="riv-header">

  <div class="riv-title-block">
    <div class="riv-title-icon">🌊</div>
    <div>
      <div class="riv-main-title">PUNJAB RIVER INTELLIGENCE</div>
      <div class="riv-subtitle">Provincial Disaster Management Authority (PDMA) &nbsp;•&nbsp; Live River Monitoring &amp; Flood Early Warning Intelligence</div>
    </div>
  </div>

  <div class="riv-header-right">
    <div class="riv-live-badge"><span class="dot"></span> Live Monitoring Active</div>
    <div class="riv-update-block">
      <div class="riv-update-label">Last Update</div>
      <div class="riv-update-value">{latest_update.strftime('%H:%M:%S')}</div>
    </div>
  </div>

</div>
""",
    unsafe_allow_html=True,
)

st.divider()

# ==========================================================
# SIDEBAR FILTERS
# ==========================================================

def render_dropdown_filter(label: str, options: list, key: str, noun_singular: str, noun_plural: str) -> list:
    """
    Compact 'All X / N X Selected' dropdown that behaves like the
    existing Aggregation selectbox from the outside, but still
    supports multi-selection on the inside (via st.multiselect,
    which already provides type-to-search). Select All / Clear All
    set st.session_state[key] directly BEFORE the widget with that
    same key is instantiated later in this same run, which is the
    documented, safe way to programmatically control a widget's
    value in Streamlit -- no extra rerun is required.

    Semantics are identical to the plain st.sidebar.multiselect this
    replaces: same key holds the same list of selected values, same
    default (all options) on first load.
    """

    if key not in st.session_state:
        st.session_state[key] = list(options)

    # Drop any previously-selected values that no longer exist in the
    # current option list (keeps behavior identical to how a plain
    # st.multiselect would react to a shrinking options list).
    st.session_state[key] = [v for v in st.session_state[key] if v in options]

    current = st.session_state[key]
    total = len(options)
    n = len(current)

    if total == 0:
        button_label = f"No {noun_plural} Available"
    elif n == total:
        button_label = f"All {noun_plural}"
    elif n == 0:
        button_label = f"No {noun_plural} Selected"
    elif n == 1:
        button_label = f"1 {noun_singular} Selected"
    else:
        button_label = f"{n} {noun_plural} Selected"

    with st.sidebar.popover(button_label, use_container_width=True):

        bcol1, bcol2 = st.columns(2)

        with bcol1:
            if st.button("Select All", key=f"{key}_select_all", use_container_width=True):
                st.session_state[key] = list(options)

        with bcol2:
            if st.button("Clear All", key=f"{key}_clear_all", use_container_width=True):
                st.session_state[key] = []

        selected = st.multiselect(
            label,
            options,
            key=key,
            label_visibility="collapsed",
        )

    return selected


st.sidebar.header("🌊 River Filters")

min_date = df["report_datetime"].min().date()
max_date = df["report_datetime"].max().date()

start_date = st.sidebar.date_input(
    "📅 Start Date",
    value=min_date,
    min_value=min_date,
    max_value=max_date,
)

end_date = st.sidebar.date_input(
    "📅 End Date",
    value=max_date,
    min_value=min_date,
    max_value=max_date,
)

river_list = sorted(df["river"].dropna().unique())

selected_rivers = render_dropdown_filter("River", river_list, "sel_river", "River", "Rivers")

station_list = sorted(df["station"].dropna().unique())

selected_stations = render_dropdown_filter("Station", station_list, "sel_station", "Station", "Stations")

risk_levels = ["Normal", "Watch", "Danger", "Unknown"]

selected_risk = render_dropdown_filter("Risk Level", risk_levels, "sel_risk", "Risk Level", "Risk Levels")

flow_options = sorted(df["flow_status"].dropna().unique())

selected_flow = render_dropdown_filter("Flow Status", flow_options, "sel_flow", "Flow Status", "Flow Statuses")

aggregation = st.sidebar.selectbox(
    "📊 Aggregation",
    ["Hourly", "Daily", "Weekly", "Monthly", "Yearly"],
    index=1,
)

AGG_FREQ_MAP = {
    "Hourly": "h",
    "Daily": "D",
    "Weekly": "W",
    "Monthly": "ME",
    "Yearly": "YE",
}

st.sidebar.divider()

st.sidebar.caption(
    f"""
### Dashboard Status

**Monitoring Stations:** {df['station'].nunique()}

**Active Rivers:** {df['river'].nunique()}

**Last Update**

{latest_update.strftime('%d %b %Y %I:%M %p')}
"""
)

# ==========================================================
# ANALYTICS PIPELINE -- SINGLE DATAFRAME: filtered_df
# ==========================================================

filtered_df = df.copy()

filtered_df["risk"] = filtered_df.apply(calculate_risk, axis=1)

start_ts = pd.to_datetime(start_date)
end_ts = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

filtered_df = filtered_df[
    (filtered_df["report_datetime"] >= start_ts)
    & (filtered_df["report_datetime"] <= end_ts)
]

filtered_df = filtered_df[filtered_df["river"].isin(selected_rivers)]
filtered_df = filtered_df[filtered_df["station"].isin(selected_stations)]
filtered_df = filtered_df[filtered_df["risk"].isin(selected_risk)]
filtered_df = filtered_df[filtered_df["flow_status"].isin(selected_flow)]

if filtered_df.empty:

    st.warning("No matching river stations found.")
    st.stop()

freq = AGG_FREQ_MAP[aggregation]

def _mode_or_unknown(series: pd.Series) -> str:

    modes = series.mode()

    return modes.iat[0] if not modes.empty else "Unknown"

filtered_df = (
    filtered_df
    .groupby(
        [pd.Grouper(key="report_datetime", freq=freq), "station", "river"],
        as_index=False,
    )
    .agg(
        current_level_ft=("current_level_ft", "mean"),
        danger_level_ft=("danger_level_ft", "mean"),
        discharge_cusecs=("discharge_cusecs", "mean"),
        flow_status=("flow_status", _mode_or_unknown),
        # NEW: real count of raw rows that fed each aggregated bucket --
        # not a new query, just one more named aggregation on the same
        # groupby already being computed. Powers the "observation count"
        # hover field requested for both replacement charts below.
        observation_count=("station", "count"),
    )
    .rename(columns={"report_datetime": "period"})
)

filtered_df["risk"] = filtered_df.apply(calculate_risk, axis=1)

filtered_df = filtered_df.sort_values(
    ["period", "station"],
    ascending=[False, True],
).reset_index(drop=True)

if filtered_df.empty:

    st.warning("No matching river stations found.")
    st.stop()

# ==========================================================
# EXECUTIVE METRICS (ALL FROM filtered_df)
# ==========================================================

latest_time = filtered_df["period"].max()

river_count = filtered_df["river"].nunique()
station_count = filtered_df["station"].nunique()

highest_level_val = filtered_df["current_level_ft"].max()
lowest_level_val = filtered_df["current_level_ft"].min()
avg_level_val = filtered_df["current_level_ft"].mean()
highest_discharge_val = filtered_df["discharge_cusecs"].max()

highest_row = filtered_df.loc[filtered_df["current_level_ft"].idxmax()]
lowest_row = filtered_df.loc[filtered_df["current_level_ft"].idxmin()]

current_status = (
    filtered_df
    .sort_values("period")
    .drop_duplicates(subset=["station"], keep="last")
)

danger_count = int((current_status["risk"] == "Danger").sum())
watch_count = int((current_status["risk"] == "Watch").sum())
normal_count = int((current_status["risk"] == "Normal").sum())

if danger_count > 0:
    overall_status = "🔴 High Flood Risk"
elif watch_count > 0:
    overall_status = "🟡 Watch Level"
else:
    overall_status = "🟢 Normal"

# ==========================================================
# KPI COMMAND TILES
# ==========================================================

k1, k2, k3, k4, k5 = st.columns(5)

with k1:

    st.markdown(f"""
<div class="tile tile-primary">
  <div class="tile-head">
    <div class="tile-label">Total Rivers</div>
    <div>🌊</div>
  </div>
  <div class="tile-value">{river_count}</div>
  <div class="tile-foot">
    <span>Active in selection</span>
    <span class="tag">Rivers</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k2:

    st.markdown(f"""
<div class="tile tile-primary">
  <div class="tile-head">
    <div class="tile-label">Monitoring Stations</div>
    <div>📡</div>
  </div>
  <div class="tile-value">{station_count}</div>
  <div class="tile-foot">
    <span>Reporting in range</span>
    <span class="tag">Stations</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k3:

    st.markdown(f"""
<div class="tile tile-danger">
  <div class="tile-head">
    <div class="tile-label">Highest Water Level</div>
    <div>⚠</div>
  </div>
  <div class="tile-value danger">{highest_level_val:.2f} ft</div>
  <div class="tile-foot">
    <span>{highest_row['station']}</span>
    <span class="tag danger">Peak</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k4:

    st.markdown(f"""
<div class="tile tile-success">
  <div class="tile-head">
    <div class="tile-label">Lowest Water Level</div>
    <div>▽</div>
  </div>
  <div class="tile-value success">{lowest_level_val:.2f} ft</div>
  <div class="tile-foot">
    <span>{lowest_row['station']}</span>
    <span class="tag success">Min</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k5:

    st.markdown(f"""
<div class="tile tile-primary">
  <div class="tile-head">
    <div class="tile-label">Average Water Level</div>
    <div>≈</div>
  </div>
  <div class="tile-value">{avg_level_val:.2f} ft</div>
  <div class="tile-foot">
    <span>Across selection</span>
    <span class="tag">Mean</span>
  </div>
</div>
""", unsafe_allow_html=True)

k6, k7, k8, k9, k10 = st.columns(5)

with k6:

    st.markdown(f"""
<div class="tile tile-primary">
  <div class="tile-head">
    <div class="tile-label">Highest Discharge</div>
    <div>〰</div>
  </div>
  <div class="tile-value">{highest_discharge_val:,.0f}</div>
  <div class="tile-foot">
    <span>Cusecs</span>
    <span class="tag">Flow</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k7:

    st.markdown(f"""
<div class="tile {'tile-danger' if danger_count > 0 else 'tile-success'}">
  <div class="tile-head">
    <div class="tile-label">Danger Stations</div>
    <div>🚨</div>
  </div>
  <div class="tile-value {'danger' if danger_count > 0 else 'success'}">{danger_count:02d}</div>
  <div class="tile-foot">
    <span>Current status</span>
    <span class="tag {'danger' if danger_count > 0 else 'success'}">{'Alert' if danger_count > 0 else 'Clear'}</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k8:

    st.markdown(f"""
<div class="tile tile-warning">
  <div class="tile-head">
    <div class="tile-label">Watch Stations</div>
    <div>👁</div>
  </div>
  <div class="tile-value warning">{watch_count:02d}</div>
  <div class="tile-foot">
    <span>Current status</span>
    <span class="tag">Watch</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k9:

    st.markdown(f"""
<div class="tile tile-success">
  <div class="tile-head">
    <div class="tile-label">Normal Stations</div>
    <div>✓</div>
  </div>
  <div class="tile-value success">{normal_count:02d}</div>
  <div class="tile-foot">
    <span>Current status</span>
    <span class="tag success">Normal</span>
  </div>
</div>
""", unsafe_allow_html=True)

with k10:

    st.markdown(f"""
<div class="tile tile-primary">
  <div class="tile-head">
    <div class="tile-label">Latest Monitoring Time</div>
    <div>🕒</div>
  </div>
  <div class="tile-value" style="font-size:18px;">{latest_time.strftime('%d %b %Y')}</div>
  <div class="tile-foot">
    <span>{latest_time.strftime('%I:%M %p')}</span>
    <span class="tag">{aggregation}</span>
  </div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ==========================================================
# ANALYTICS GRID -- TRENDS (aggregation-aware)
# ==========================================================

CHART_HEIGHT = 440

trend_level = (
    filtered_df
    .groupby("period", as_index=False)["current_level_ft"]
    .mean()
    .sort_values("period")
)

trend_discharge = (
    filtered_df
    .groupby("period", as_index=False)["discharge_cusecs"]
    .mean()
    .sort_values("period")
)

g1, g2 = st.columns(2)

with g1:

    st.markdown(f'<div class="chart-tile-header">📈 Water Level Trend Over Time ({aggregation})</div>', unsafe_allow_html=True)

    fig = px.line(
        trend_level,
        x="period",
        y="current_level_ft",
        markers=True,
    )

    fig.update_traces(
        line=dict(width=3, color="#b5c8e5"),
        hovertemplate="<b>%{x}</b><br>Level : %{y:.2f} ft<extra></extra>",
    )

    fig.update_layout(
        template="plotly_dark",
        height=CHART_HEIGHT,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#c4c6cd"),
        xaxis_title="Period",
        yaxis_title="Water Level (ft)",
    )

    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")

    st.plotly_chart(fig, use_container_width=True)

with g2:

    st.markdown(f'<div class="chart-tile-header">〰 Discharge Trend Over Time ({aggregation})</div>', unsafe_allow_html=True)

    fig = px.line(
        trend_discharge,
        x="period",
        y="discharge_cusecs",
        markers=True,
    )

    fig.update_traces(
        line=dict(width=3, color="#79dd68"),
        hovertemplate="<b>%{x}</b><br>Discharge : %{y:,.0f} cusecs<extra></extra>",
    )

    fig.update_layout(
        template="plotly_dark",
        height=CHART_HEIGHT,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#c4c6cd"),
        xaxis_title="Period",
        yaxis_title="Discharge (Cusecs)",
    )

    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")

    st.plotly_chart(fig, use_container_width=True)

# ==========================================================
# AVERAGE LEVEL / DISCHARGE BY RIVER
# ==========================================================

river_level_avg = (
    filtered_df
    .groupby("river", as_index=False)["current_level_ft"]
    .mean()
    .sort_values("current_level_ft", ascending=False)
)

river_discharge_avg = (
    filtered_df
    .groupby("river", as_index=False)["discharge_cusecs"]
    .mean()
    .sort_values("discharge_cusecs", ascending=False)
)

g3, g4 = st.columns(2)

with g3:

    st.markdown('<div class="chart-tile-header">📊 Average Water Level by River</div>', unsafe_allow_html=True)

    fig = px.bar(
        river_level_avg,
        x="river",
        y="current_level_ft",
        color="current_level_ft",
        text="current_level_ft",
        color_continuous_scale=[[0, "#0d2137"], [1, "#b5c8e5"]],
    )

    fig.update_traces(
        texttemplate="%{text:.2f} ft",
        textposition="outside",
    )

    fig.update_layout(
        template="plotly_dark",
        height=CHART_HEIGHT,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#c4c6cd"),
        coloraxis_showscale=False,
        xaxis_title="",
        yaxis_title="Average Water Level (ft)",
    )

    fig.update_xaxes(tickangle=-30, gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")

    st.plotly_chart(fig, use_container_width=True)

with g4:

    st.markdown('<div class="chart-tile-header">📊 Average Discharge by River</div>', unsafe_allow_html=True)

    fig = px.bar(
        river_discharge_avg,
        x="river",
        y="discharge_cusecs",
        color="discharge_cusecs",
        text="discharge_cusecs",
        color_continuous_scale=[[0, "#430c00"], [1, "#ffb5a0"]],
    )

    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
    )

    fig.update_layout(
        template="plotly_dark",
        height=CHART_HEIGHT,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#c4c6cd"),
        coloraxis_showscale=False,
        xaxis_title="",
        yaxis_title="Average Discharge (Cusecs)",
    )

    fig.update_xaxes(tickangle=-30, gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")

    st.plotly_chart(fig, use_container_width=True)

# ==========================================================
# AVERAGE WATER LEVEL BY RIVER -- HORIZONTAL RANKING
# ==========================================================

st.markdown(
    '<div class="chart-tile-header">📊 Average Water Level by River (Ranked)</div>',
    unsafe_allow_html=True,
)

RISK_COLOR_MAP = {
    "Danger": "#ffb4ab",
    "Watch": "#ffb5a0",
    "Normal": "#79dd68",
    "Unknown": "#8e9197",
}

_RISK_SEVERITY = {
    "Danger": 3,
    "Watch": 2,
    "Normal": 1,
    "Unknown": 0,
}


def _worst_risk(series: pd.Series) -> str:
    valid = [
        str(value)
        for value in series
        if pd.notna(value)
    ]

    if not valid:
        return "Unknown"

    return max(
        valid,
        key=lambda r: _RISK_SEVERITY.get(r, 0),
    )


# ----------------------------------------------------------
# RIVER AVERAGES
# ----------------------------------------------------------

river_ranked = (
    filtered_df
    .groupby("river", as_index=False)
    .agg(
        average_level_ft=("current_level_ft", "mean"),
    )
)

# Remove invalid average levels before plotting
river_ranked = river_ranked[
    pd.notna(river_ranked["average_level_ft"])
    & river_ranked["average_level_ft"].apply(
        lambda x: pd.notna(x) and x != float("inf") and x != float("-inf")
    )
].copy()


# ----------------------------------------------------------
# WORST CURRENT RISK PER RIVER
# ----------------------------------------------------------

river_worst_risk = (
    current_status
    .groupby("river")["risk"]
    .apply(_worst_risk)
)

river_ranked["risk"] = (
    river_ranked["river"]
    .map(river_worst_risk)
    .fillna("Unknown")
)

river_ranked["bar_color"] = (
    river_ranked["risk"]
    .map(RISK_COLOR_MAP)
    .fillna(RISK_COLOR_MAP["Unknown"])
)


# ----------------------------------------------------------
# REAL DANGER THRESHOLD
#
# IMPORTANT:
# Only use valid numeric danger levels.
# NaN / infinity / zero values are ignored.
# ----------------------------------------------------------

threshold_df = filtered_df[
    pd.notna(filtered_df["danger_level_ft"])
].copy()

threshold_df = threshold_df[
    threshold_df["danger_level_ft"].apply(
        lambda x: pd.notna(x)
        and x != float("inf")
        and x != float("-inf")
    )
]

# Danger threshold must be a meaningful positive value
threshold_df = threshold_df[
    threshold_df["danger_level_ft"] > 0
]

if not threshold_df.empty:

    river_danger_threshold = (
        threshold_df
        .groupby("river")["danger_level_ft"]
        .mean()
        .dropna()
        .to_dict()
    )

else:

    river_danger_threshold = {}


# ----------------------------------------------------------
# SORT LOWEST -> HIGHEST
# ----------------------------------------------------------

river_ranked = river_ranked.sort_values(
    "average_level_ft",
    ascending=True,
).reset_index(drop=True)


# ----------------------------------------------------------
# PERIOD LABEL
# ----------------------------------------------------------

_period_start = filtered_df["period"].min()
_period_end = filtered_df["period"].max()

if _period_start == _period_end:

    _period_label = _period_start.strftime("%d %b %Y")

else:

    _period_label = (
        f"{_period_start.strftime('%d %b %Y')} – "
        f"{_period_end.strftime('%d %b %Y')}"
    )


# ----------------------------------------------------------
# CHART
# ----------------------------------------------------------

fig = go.Figure()


# ----------------------------------------------------------
# MAIN RIVER BARS
# ----------------------------------------------------------

fig.add_trace(
    go.Bar(

        x=river_ranked["average_level_ft"],

        y=river_ranked["river"],

        orientation="h",

        marker=dict(
            color=river_ranked["bar_color"],
            line=dict(width=0),
        ),

        text=river_ranked["average_level_ft"],

        texttemplate="%{text:.2f} ft",

        textposition="outside",

        customdata=river_ranked[
            ["risk"]
        ].to_numpy(),

        hovertemplate=(
            "<b>%{y}</b><br>"
            "Avg Water Level: %{x:.2f} ft<br>"
            "Risk Level: %{customdata[0]}<br>"
            f"Period: {_period_label}"
            "<extra></extra>"
        ),

        showlegend=False,
    )
)


# ----------------------------------------------------------
# DANGER THRESHOLD MARKERS
#
# Only create this trace when there are ACTUAL valid
# numeric thresholds.
# This prevents NaN ft from appearing.
# ----------------------------------------------------------

_threshold_rivers = []

_threshold_values = []

for river_name in river_ranked["river"]:

    threshold = river_danger_threshold.get(river_name)

    if threshold is None:
        continue

    if pd.isna(threshold):
        continue

    if threshold == float("inf"):
        continue

    if threshold == float("-inf"):
        continue

    if threshold <= 0:
        continue

    _threshold_rivers.append(river_name)
    _threshold_values.append(float(threshold))


if _threshold_rivers:

    fig.add_trace(
        go.Scatter(

            x=_threshold_values,

            y=_threshold_rivers,

            mode="markers",

            marker=dict(
                symbol="line-ns",
                size=16,
                line=dict(
                    width=2,
                    color="#e3e2e1",
                ),
            ),

            name="Danger Threshold",

            hovertemplate=(
                "<b>%{y} Danger Level</b><br>"
                "%{x:.2f} ft"
                "<extra></extra>"
            ),

        )
    )


# ----------------------------------------------------------
# LAYOUT
# ----------------------------------------------------------

fig.update_layout(

    template="plotly_dark",

    height=CHART_HEIGHT,

    margin=dict(
        l=10,
        r=70,
        t=10,
        b=10,
    ),

    paper_bgcolor="rgba(0,0,0,0)",

    plot_bgcolor="rgba(0,0,0,0)",

    font=dict(
        family="Inter, sans-serif",
        size=12,
        color="#c4c6cd",
    ),

    xaxis_title="Average Water Level (ft)",

    yaxis_title="",

    yaxis=dict(
        automargin=True,
        gridcolor="rgba(255,255,255,0.06)",
    ),

    showlegend=bool(_threshold_rivers),

    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
        bgcolor="rgba(0,0,0,0)",
    ),
)


fig.update_xaxes(
    gridcolor="rgba(255,255,255,0.06)"
)


# ----------------------------------------------------------
# DISPLAY
# ----------------------------------------------------------

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "responsive": True,
        "displaylogo": False,
    },
)

# ==========================================================
# MONITORING STATIONS BY RIVER -- horizontal stacked bar chart
# by risk level (replaces the old bubble/scatter chart, which had
# overlapping station labels and a risk-color legend that didn't
# make the chart any easier to read).
#
# Built entirely from current_status (already computed above for
# the KPI tiles: one row per station, its latest reading and risk)
# -- no new query, no invented columns. Rivers with zero matching
# stations after filtering simply never appear in current_status,
# so they are naturally excluded without extra code.
# ==========================================================

st.markdown('<div class="chart-tile-header">📡 Monitoring Stations by River</div>', unsafe_allow_html=True)

_RISK_ORDER = ["Normal", "Watch", "Danger", "Unknown"]

station_risk_counts = (
    current_status
    .groupby(["river", "risk"])
    .size()
    .unstack(fill_value=0)
    .reindex(columns=_RISK_ORDER, fill_value=0)
)

station_risk_counts["Total"] = station_risk_counts.sum(axis=1)
station_risk_counts = station_risk_counts[station_risk_counts["Total"] > 0]
station_risk_counts = station_risk_counts.sort_values("Total", ascending=True)

fig = go.Figure()

for risk_label in _RISK_ORDER:

    fig.add_trace(
        go.Bar(
            name=risk_label,
            y=station_risk_counts.index,
            x=station_risk_counts[risk_label],
            orientation="h",
            marker=dict(color=RISK_COLOR_MAP[risk_label], line=dict(width=0)),
            hovertemplate=(
                "<b>%{y}</b><br>"
                f"{risk_label} Stations: " + "%{x}<extra></extra>"
            ),
        )
    )

# Total-station-count label at the end of each stacked bar.
for river_name, row in station_risk_counts.iterrows():
    fig.add_annotation(
        x=row["Total"],
        y=river_name,
        text=f"<b>{int(row['Total'])}</b>",
        showarrow=False,
        xanchor="left",
        xshift=8,
        font=dict(family="JetBrains Mono, monospace", size=12, color="#e3e2e1"),
    )

fig.update_layout(
    template="plotly_dark",
    height=CHART_HEIGHT,
    barmode="stack",
    margin=dict(l=10, r=60, t=10, b=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=12, color="#c4c6cd"),
    xaxis_title="Number of Monitoring Stations",
    yaxis_title="",
    yaxis=dict(automargin=True, gridcolor="rgba(255,255,255,0.06)"),
    legend=dict(
        title="Risk Level",
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
        bgcolor="rgba(0,0,0,0)",
    ),
)

fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)")

st.plotly_chart(
    fig,
    use_container_width=True,
    config={"responsive": True, "displaylogo": False},
)

st.divider()

# ==========================================================
# RANKING TABLES
# ==========================================================

r1, r2 = st.columns(2)

with r1:

    st.markdown('<div class="table-tile-header">🏆 Top Highest Water Level Stations</div>', unsafe_allow_html=True)

    level_rank = (
        filtered_df
        .groupby("station", as_index=False)["current_level_ft"]
        .max()
        .sort_values("current_level_ft", ascending=False)
        .head(15)
        .reset_index(drop=True)
    )

    level_rank.index = level_rank.index + 1

    level_rank.rename(
        columns={
            "station": "Station",
            "current_level_ft": "Water Level (ft)",
        },
        inplace=True,
    )

    st.dataframe(
        level_rank,
        hide_index=False,
        use_container_width=True,
        height=420,
        column_config={
            "Water Level (ft)": st.column_config.NumberColumn(format="%.2f"),
        },
    )

with r2:

    st.markdown('<div class="table-tile-header">🏆 Top Highest Discharge Stations</div>', unsafe_allow_html=True)

    discharge_rank = (
        filtered_df
        .groupby("station", as_index=False)["discharge_cusecs"]
        .max()
        .sort_values("discharge_cusecs", ascending=False)
        .head(15)
        .reset_index(drop=True)
    )

    discharge_rank.index = discharge_rank.index + 1

    discharge_rank.rename(
        columns={
            "station": "Station",
            "discharge_cusecs": "Discharge (Cusecs)",
        },
        inplace=True,
    )

    st.dataframe(
        discharge_rank,
        hide_index=False,
        use_container_width=True,
        height=420,
        column_config={
            "Discharge (Cusecs)": st.column_config.NumberColumn(format="%,.0f"),
        },
    )

st.divider()

# ==========================================================
# FOUR-CARD EXECUTIVE SUMMARY
# ==========================================================

e1, e2, e3, e4 = st.columns(4)

with e1:

    st.markdown(f"""
<div class="exec-card exec-card-danger">
  <div class="exec-card-title">↑ Critical Alert Summary</div>
  <div class="exec-card-row"><span>Max Level</span><b>{highest_row['station']} ({highest_row['current_level_ft']:.2f} ft)</b></div>
  <div class="exec-card-row"><span>River</span><b>{highest_row['river']}</b></div>
  <div class="exec-card-row"><span>Status</span><b>{overall_status}</b></div>
</div>
""", unsafe_allow_html=True)

with e2:

    st.markdown(f"""
<div class="exec-card exec-card-success">
  <div class="exec-card-title">↓ Lowest Water Level</div>
  <div class="exec-card-row"><span>Min Level</span><b>{lowest_row['station']} ({lowest_row['current_level_ft']:.2f} ft)</b></div>
  <div class="exec-card-row"><span>River Segment</span><b>{lowest_row['river']}</b></div>
  <div class="exec-card-row"><span>Risk</span><b>{lowest_row['risk']}</b></div>
</div>
""", unsafe_allow_html=True)

with e3:

    st.markdown(f"""
<div class="exec-card exec-card-primary">
  <div class="exec-card-title">⊙ Network Summary</div>
  <div class="exec-card-row"><span>Stations</span><b>{station_count}</b></div>
  <div class="exec-card-row"><span>Rivers</span><b>{river_count}</b></div>
  <div class="exec-card-row"><span>Alerts</span><b>{danger_count}</b></div>
</div>
""", unsafe_allow_html=True)

with e4:

    st.markdown(f"""
<div class="exec-card exec-card-warning">
  <div class="exec-card-title">🕒 Latest Observation</div>
  <div class="exec-card-row"><span>Date</span><b>{latest_time.strftime('%d %b %Y')}</b></div>
  <div class="exec-card-row"><span>Time</span><b>{latest_time.strftime('%I:%M %p')}</b></div>
  <div class="exec-card-row"><span>Aggregation</span><b>{aggregation}</b></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ==========================================================
# LATEST RIVER MONITORING RECORDS (filtered_df)
# ==========================================================

st.markdown(
    '<div class="table-tile-header">▤ Latest River Monitoring Records</div>',
    unsafe_allow_html=True,
)

st.dataframe(
    filtered_df[
        [
            "period",
            "station",
            "river",
            "current_level_ft",
            "danger_level_ft",
            "discharge_cusecs",
            "flow_status",
            "risk",
        ]
    ],
    hide_index=True,
    use_container_width=True,
    height=380,
    column_config={

        "period": st.column_config.DatetimeColumn(
            f"📅 Period ({aggregation})",
            format="DD MMM YYYY hh:mm A",
        ),

        "station": st.column_config.TextColumn(
            "📍 Station",
            width="medium",
        ),

        "river": st.column_config.TextColumn(
            "🌊 River",
            width="medium",
        ),

        "current_level_ft": st.column_config.NumberColumn(
            "Current Level (ft)",
            format="%.2f",
        ),

        "danger_level_ft": st.column_config.NumberColumn(
            "Danger Level (ft)",
            format="%.2f",
        ),

        "discharge_cusecs": st.column_config.NumberColumn(
            "Discharge (Cusecs)",
            format="%.0f",
        ),

        "flow_status": st.column_config.TextColumn(
            "Flow Status",
        ),

        "risk": st.column_config.TextColumn(
            "Risk",
        ),

    },
)

st.divider()

# ==========================================================
# EXPORT (merged Dataset Information + Download) -- filtered_df
# ==========================================================

with st.container(border=True):

    st.markdown('<div class="chart-tile-header">📥 Export River Dataset</div>', unsafe_allow_html=True)

    d1, d2, d3, d4, d5 = st.columns([1, 1, 1, 1, 1.6])

    with d1:

        st.metric("Records", f"{len(filtered_df):,}")

    with d2:

        st.metric("Stations", filtered_df['station'].nunique())

    with d3:

        st.metric("Rivers", filtered_df['river'].nunique())

    with d4:

        st.metric("Danger", int((filtered_df['risk'] == 'Danger').sum()))

    with d5:

        st.write("")

        dl1, dl2 = st.columns(2)

        with dl1:

            st.download_button(
                label="⬇ CSV",
                data=filtered_df.to_csv(index=False).encode("utf-8"),
                file_name="pdma_river_monitoring.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with dl2:

            excel_buffer = BytesIO()

            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                filtered_df.to_excel(writer, index=False, sheet_name="River")

            st.download_button(
                label="⬇ Excel",
                data=excel_buffer.getvalue(),
                file_name="pdma_river_monitoring.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    st.caption(
        f"Latest observation: {filtered_df['period'].max().strftime('%d %b %Y %I:%M %p')} · "
        f"Aggregation: {aggregation} · "
        f"Exports contain exactly the currently filtered and aggregated river dataset."
    )

st.divider()

# ==========================================================
# FOOTER
# ==========================================================

st.markdown(
    """
<div style="text-align:center; color:#8e9197; font-size:13px; padding-top:8px; padding-bottom:8px; font-family:'JetBrains Mono', monospace;">

<b style="color:#c4c6cd;">PAKISTAN OPERATIONAL RISK INTELLIGENCE PLATFORM</b><br>

Provincial Disaster Management Authority (PDMA) Punjab<br>

Real-Time River Monitoring • Flood Early Warning • Operational Risk Intelligence

</div>
""",
    unsafe_allow_html=True,
)