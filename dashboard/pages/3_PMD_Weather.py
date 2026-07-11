"""
dashboard/pages/3_PMD_Weather.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd
from dashboard.db import get_pmd_weather, get_pmd_forecast

st.set_page_config(page_title="PMD Weather", page_icon="🌦", layout="wide")
st.title("🌦 PMD — City Weather Forecasts")
st.caption("Source: Pakistan Meteorological Department · nwfc.pmd.gov.pk")

try:
    df_weather  = get_pmd_weather()
    df_forecast = get_pmd_forecast()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# ----------------------------------------------------------
# LATEST FORECAST TEXT
# ----------------------------------------------------------
if not df_forecast.empty:
    latest = df_forecast.iloc[0]
    with st.expander("📋 Latest PMD Forecast Text", expanded=True):
        st.write(f"**Category:** {latest['category']}")
        st.write(f"**Scraped at:** {latest['scraped_at']}")
        st.markdown(latest["forecast"] or "_No forecast text available_")

st.divider()

if df_weather.empty:
    st.warning("No weather data found. Run the pipeline first.")
    st.stop()

# ----------------------------------------------------------
# TEMPERATURE CHART
# ----------------------------------------------------------
df_weather["max_temp_num"] = pd.to_numeric(
    df_weather["max_temperature"].str.extract(r"(\d+)")[0],
    errors="coerce"
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Max Temperature by City")
    df_temp = df_weather.dropna(subset=["max_temp_num"]).sort_values(
        "max_temp_num", ascending=False
    ).head(20)
    fig = px.bar(
        df_temp, x="city", y="max_temp_num",
        color="max_temp_num",
        color_continuous_scale="RdYlGn_r",
        labels={"max_temp_num": "°C", "city": "City"},
    )
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Humidity by City")
    df_hum = df_weather.copy()
    df_hum["humidity_num"] = pd.to_numeric(
        df_hum["humidity"].str.extract(r"(\d+)")[0],
        errors="coerce"
    )
    df_hum = df_hum.dropna(subset=["humidity_num"]).sort_values(
        "humidity_num", ascending=False
    ).head(20)
    fig2 = px.bar(
        df_hum, x="city", y="humidity_num",
        color="humidity_num",
        color_continuous_scale="Blues",
        labels={"humidity_num": "%", "city": "City"},
    )
    fig2.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig2, use_container_width=True)

# ----------------------------------------------------------
# 3-DAY FORECAST TABLE
# ----------------------------------------------------------
st.subheader("3-Day City Forecast")
display_cols = ["city", "max_temperature", "humidity",
                "day1_forecast", "day2_forecast", "day3_forecast"]
st.dataframe(
    df_weather[display_cols].drop_duplicates("city"),
    use_container_width=True,
    hide_index=True,
)
