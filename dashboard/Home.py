"""
dashboard/Home.py

Pakistan Operational Risk Intelligence — Dashboard Home
Run: streamlit run dashboard/Home.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from dashboard.db import get_kpis

st.set_page_config(
    page_title="Pakistan Operational Risk Intelligence",
    page_icon="🇵🇰",
    layout="wide",
)

st.title("🇵🇰 Pakistan Operational Risk Intelligence")
st.caption("Real-time disaster monitoring — NDMA · PDMA Punjab · PMD")
st.divider()

# ----------------------------------------------------------
# KPI CARDS
# ----------------------------------------------------------
try:
    kpis = get_kpis()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("💀 Total Deaths",      f"{int(kpis['total_deaths']):,}")
    c2.metric("🤕 Total Injured",     f"{int(kpis['total_injured']):,}")
    c3.metric("🏠 Houses Damaged",    f"{int(kpis['houses_damaged']):,}")
    c4.metric("🚁 Persons Rescued",   f"{int(kpis['persons_rescued']):,}")
    c5.metric("🌧 Rainfall Stations", f"{int(kpis['rainfall_stations']):,}")
    c6.metric("🌊 Rivers Monitored",  f"{int(kpis['rivers_monitored']):,}")

except Exception as e:
    st.error(f"Could not load KPIs: {e}")
    st.info("Make sure PostgreSQL is running and tables are loaded.")

st.divider()

# ----------------------------------------------------------
# NAVIGATION GUIDE
# ----------------------------------------------------------
st.subheader("📊 Dashboard Pages")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **NDMA — National Disaster Management Authority**
    - 📄 **NDMA Casualties** — Deaths & injuries by province over time
    - 🏚 **NDMA Damage** — Roads, bridges, houses, livestock damage
    """)

with col2:
    st.markdown("""
    **PDMA / PMD — Provincial & Meteorological Data**
    - 🌦 **PMD Weather** — City-level 3-day forecasts
    - 🌧 **PDMA Rainfall** — Station-level rainfall readings
    - 🌊 **PDMA Rivers** — River gauge levels vs danger thresholds
    """)

st.divider()
st.caption("Data sources: ndma.gov.pk · pdma.punjab.gov.pk · pmd.gov.pk · nwfc.pmd.gov.pk")
