"""
dashboard/pages/5_PDMA_Rivers.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from dashboard.db import get_gauge

st.set_page_config(page_title="PDMA Rivers", page_icon="🌊", layout="wide")
st.title("🌊 PDMA — River Gauge Readings")
st.caption("Source: PDMA Punjab gauge reports")

try:
    df = get_gauge()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if df.empty:
    st.warning("No gauge data found. Run the pipeline first.")
    st.stop()

# ----------------------------------------------------------
# LATEST READING PER STATION
# ----------------------------------------------------------
latest = (
    df.sort_values("report_datetime", ascending=False)
    .drop_duplicates("station")
    .copy()
)

# Danger flag
latest["above_danger"] = (
    latest["current_level_ft"].notna() &
    latest["danger_level_ft"].notna() &
    (latest["current_level_ft"] >= latest["danger_level_ft"])
)

# ----------------------------------------------------------
# KPI ROW
# ----------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Stations Monitored", f"{len(latest)}")
c2.metric("Rivers",             f"{latest['river'].nunique()}")
c3.metric("Above Danger Level", f"{latest['above_danger'].sum()}")
c4.metric("Rising Flow",        f"{(latest['flow_status'] == 'RISING').sum()}")

st.divider()

# ----------------------------------------------------------
# FILTERS
# ----------------------------------------------------------
rivers = sorted(latest["river"].dropna().unique())
sel_rivers = st.multiselect("Filter by River", rivers, default=rivers)
filtered = latest[latest["river"].isin(sel_rivers)]

col1, col2 = st.columns(2)

with col1:
    st.subheader("Current vs Danger Level by Station")
    plot_df = filtered.dropna(subset=["current_level_ft", "danger_level_ft"])
    if not plot_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Current Level (ft)",
            x=plot_df["station"],
            y=plot_df["current_level_ft"],
            marker_color="#3498db",
        ))
        fig.add_trace(go.Bar(
            name="Danger Level (ft)",
            x=plot_df["station"],
            y=plot_df["danger_level_ft"],
            marker_color="#e74c3c",
            opacity=0.6,
        ))
        fig.update_layout(
            barmode="overlay",
            xaxis_tickangle=-45,
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No level data available for selected rivers.")

with col2:
    st.subheader("Flow Status Distribution")
    flow_counts = (
        filtered["flow_status"]
        .fillna("UNKNOWN")
        .value_counts()
        .reset_index()
    )
    flow_counts.columns = ["status", "count"]
    color_map = {
        "RISING":  "#e74c3c",
        "FALLING": "#2ecc71",
        "STEADY":  "#f39c12",
        "UNKNOWN": "#95a5a6",
    }
    fig2 = px.pie(
        flow_counts, names="status", values="count",
        color="status",
        color_discrete_map=color_map,
        hole=0.4,
    )
    fig2.update_layout(margin=dict(t=20))
    st.plotly_chart(fig2, use_container_width=True)

# ----------------------------------------------------------
# DANGER ALERT TABLE
# ----------------------------------------------------------
danger_stations = filtered[filtered["above_danger"]]
if not danger_stations.empty:
    st.subheader(f"⚠️ Stations Above Danger Level ({len(danger_stations)})")
    st.dataframe(
        danger_stations[[
            "station", "river", "current_level_ft",
            "danger_level_ft", "discharge_cusecs", "flow_status"
        ]].sort_values("current_level_ft", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("✅ No stations currently above danger level.")

st.subheader("All Gauge Readings")
st.dataframe(
    filtered[[
        "station", "river", "current_level_ft",
        "danger_level_ft", "discharge_cusecs",
        "flow_status", "report_datetime"
    ]].sort_values("report_datetime", ascending=False),
    use_container_width=True,
    hide_index=True,
)
