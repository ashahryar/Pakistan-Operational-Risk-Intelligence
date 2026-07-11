"""
dashboard/pages/1_NDMA_Casualties.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.db import get_casualties

st.set_page_config(page_title="NDMA Casualties", page_icon="📄", layout="wide")
st.title("📄 NDMA — Casualties by Province")
st.caption("Source: National Disaster Management Authority sitreps")

# ----------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------
try:
    df = get_casualties()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if df.empty:
    st.warning("No casualty data found. Run the pipeline first.")
    st.stop()

# ----------------------------------------------------------
# FILTERS
# ----------------------------------------------------------
provinces = sorted(df["province"].dropna().unique())
selected  = st.multiselect("Filter by Province", provinces, default=provinces)
df = df[df["province"].isin(selected)]

# ----------------------------------------------------------
# KPI ROW
# ----------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Total Deaths",  f"{int(df['deaths'].sum()):,}")
c2.metric("Total Injured", f"{int(df['injured'].sum()):,}")
c3.metric("Reports",       f"{df['report_date'].nunique()}")

st.divider()

# ----------------------------------------------------------
# CHARTS
# ----------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Deaths by Province")
    by_province = (
        df.groupby("province")[["deaths", "injured"]]
        .sum()
        .reset_index()
        .sort_values("deaths", ascending=False)
    )
    fig = px.bar(
        by_province, x="province", y=["deaths", "injured"],
        barmode="group",
        color_discrete_map={"deaths": "#e74c3c", "injured": "#f39c12"},
        labels={"value": "Count", "province": "Province"},
    )
    fig.update_layout(legend_title="", margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Casualties Over Time")
    by_date = (
        df.groupby("report_date")[["deaths", "injured"]]
        .sum()
        .reset_index()
    )
    fig2 = px.line(
        by_date, x="report_date", y=["deaths", "injured"],
        color_discrete_map={"deaths": "#e74c3c", "injured": "#f39c12"},
        labels={"value": "Count", "report_date": "Date"},
        markers=True,
    )
    fig2.update_layout(legend_title="", margin=dict(t=20))
    st.plotly_chart(fig2, use_container_width=True)

# ----------------------------------------------------------
# TABLE
# ----------------------------------------------------------
st.subheader("Raw Data")
st.dataframe(
    df.sort_values("report_date", ascending=False),
    use_container_width=True,
    hide_index=True,
)
