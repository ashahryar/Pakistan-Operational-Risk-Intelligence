"""
dashboard/pages/4_PDMA_Rainfall.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px
from dashboard.db import get_rainfall

st.set_page_config(page_title="PDMA Rainfall", page_icon="🌧", layout="wide")
st.title("🌧 PDMA — Rainfall Readings")
st.caption("Source: PDMA Punjab rainfall reports")

try:
    df = get_rainfall()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if df.empty:
    st.warning("No rainfall data found. Run the pipeline first.")
    st.stop()

# ----------------------------------------------------------
# FILTERS
# ----------------------------------------------------------
col_f1, col_f2 = st.columns(2)
with col_f1:
    min_date = df["report_date"].min()
    max_date = df["report_date"].max()
    date_range = st.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
with col_f2:
    top_n = st.slider("Top N Stations", 5, 30, 15)

if len(date_range) == 2:
    df = df[
        (df["report_date"] >= str(date_range[0])) &
        (df["report_date"] <= str(date_range[1]))
    ]

# ----------------------------------------------------------
# KPI ROW
# ----------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Total Readings",   f"{len(df):,}")
c2.metric("Stations",         f"{df['station'].nunique()}")
c3.metric("Max Rainfall (mm)", f"{df['rainfall_mm'].max():.1f}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"Top {top_n} Stations by Total Rainfall")
    top_stations = (
        df.groupby("station")["rainfall_mm"]
        .sum().reset_index()
        .sort_values("rainfall_mm", ascending=False)
        .head(top_n)
    )
    fig = px.bar(
        top_stations, x="rainfall_mm", y="station",
        orientation="h",
        color="rainfall_mm",
        color_continuous_scale="Blues",
        labels={"rainfall_mm": "mm", "station": ""},
    )
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Daily Total Rainfall Over Time")
    by_date = (
        df.groupby("report_date")["rainfall_mm"]
        .sum().reset_index()
    )
    fig2 = px.area(
        by_date, x="report_date", y="rainfall_mm",
        color_discrete_sequence=["#3498db"],
        labels={"rainfall_mm": "mm", "report_date": "Date"},
    )
    fig2.update_layout(margin=dict(t=20))
    st.plotly_chart(fig2, use_container_width=True)

st.subheader("Station Data")
st.dataframe(
    df.sort_values(["report_date", "rainfall_mm"], ascending=[False, False]),
    use_container_width=True,
    hide_index=True,
)
