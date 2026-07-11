"""
dashboard/pages/2_NDMA_Damage.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px
from dashboard.db import get_damage

st.set_page_config(page_title="NDMA Damage", page_icon="🏚", layout="wide")
st.title("🏚 NDMA — Infrastructure Damage")
st.caption("Source: National Disaster Management Authority sitreps")

try:
    df = get_damage()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if df.empty:
    st.warning("No damage data found. Run the pipeline first.")
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
c1, c2, c3, c4 = st.columns(4)
c1.metric("Houses Damaged", f"{int(df['houses_total'].sum()):,}")
c2.metric("Roads (km)",     f"{df['roads_km'].sum():.1f}")
c3.metric("Bridges",        f"{int(df['bridges'].sum()):,}")
c4.metric("Livestock Lost", f"{int(df['livestock'].sum()):,}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Houses Damaged by Province")
    by_prov = (
        df.groupby("province")["houses_total"]
        .sum().reset_index()
        .sort_values("houses_total", ascending=True)
    )
    fig = px.bar(
        by_prov, x="houses_total", y="province",
        orientation="h",
        color="houses_total",
        color_continuous_scale="Reds",
        labels={"houses_total": "Houses", "province": ""},
    )
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Damage Breakdown by Province")
    by_prov2 = (
        df.groupby("province")[["roads_km", "bridges", "livestock"]]
        .sum().reset_index()
        .sort_values("roads_km", ascending=False)
    )
    fig2 = px.bar(
        by_prov2, x="province", y=["roads_km", "bridges", "livestock"],
        barmode="group",
        labels={"value": "Count", "province": "Province"},
    )
    fig2.update_layout(legend_title="", margin=dict(t=20))
    st.plotly_chart(fig2, use_container_width=True)

st.subheader("Raw Data")
st.dataframe(
    df.sort_values("report_date", ascending=False),
    use_container_width=True,
    hide_index=True,
)
