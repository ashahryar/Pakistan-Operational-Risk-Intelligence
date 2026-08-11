import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard.db import (
    get_casualties,
    get_pmd_weather,
    get_rainfall,
    get_gauge,
    get_dashboard_summary,
)

from dashboard.styles.theme import load_css

from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header
from dashboard.components.executive_cards import render_executive_cards
from dashboard.components.executive_summary import render_executive_summary
from dashboard.components.alerts import render_alerts
from dashboard.components.footer import render_footer

from dashboard.sections.disaster import render_disaster_section
from dashboard.sections.weather import render_weather_section
from dashboard.sections.hydrology import render_hydrology_section


# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="Pakistan Operational Risk Intelligence",
    page_icon="🇵🇰",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================================
# GLOBAL STYLES
# ==========================================================

load_css()


# ==========================================================
# LIVE REFRESH
# ==========================================================

st_autorefresh(
    interval=60000,
    key="dashboard_refresh",
)


# ==========================================================
# LOAD DASHBOARD DATA
# ==========================================================

summary = get_dashboard_summary()

kpis = summary["kpis"]
last_update = summary["last_update"]

casualties = get_casualties()
weather = get_pmd_weather()
rainfall = get_rainfall()
gauge = get_gauge()


# ==========================================================
# GLOBAL SIDEBAR FILTERS
# ==========================================================

filters = render_sidebar(
    casualties,
    weather,
    rainfall,
    gauge,
)


# ==========================================================
# 1. EXECUTIVE HEADER
# ==========================================================

render_header(last_update)


# ==========================================================
# 2. NATIONAL KPI COMMAND CENTER
# ==========================================================

render_executive_cards(kpis)


# ==========================================================
# 3. CURRENT NATIONAL SITUATION
# ==========================================================

render_executive_summary(
    summary,
    casualties,
)


# ==========================================================
# 4. NATIONAL ALERT CENTER
# ==========================================================

render_alerts(summary)


# ==========================================================
# 5. NATIONAL DISASTER SNAPSHOT
# ==========================================================

if filters["show_ndma"]:

    render_disaster_section(
        filters["casualties"]
    )


# ==========================================================
# 6. NATIONAL WEATHER SNAPSHOT
# ==========================================================

if filters["show_pmd"]:

    render_weather_section(
        filters["weather"]
    )


# ==========================================================
# 7. NATIONAL HYDROLOGY SNAPSHOT
# ==========================================================

if filters["show_pdma"]:

    render_hydrology_section(
        filters["rainfall"],
        filters["gauge"],
    )


# ==========================================================
# 8. EXPORT
# ==========================================================

render_footer(
    casualties,
    weather,
    rainfall,
    gauge,
)