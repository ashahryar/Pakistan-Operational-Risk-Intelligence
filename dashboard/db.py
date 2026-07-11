"""
dashboard/db.py

Shared data access layer for the Streamlit dashboard.
Reads from PostgreSQL (local). All queries are cached for 10 minutes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import text
from config.database import engine


@st.cache_data(ttl=60)
def get_casualties() -> pd.DataFrame:
    q = """
        SELECT report_date, province, deaths, injured
        FROM ndma_casualties
        WHERE province NOT IN ('Grand Total', '')
          AND province IS NOT NULL
        ORDER BY report_date
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["report_date"])


@st.cache_data(ttl=60)
def get_damage() -> pd.DataFrame:
    q = """
        SELECT report_date, province, roads_km, bridges, houses_total, livestock
        FROM ndma_damage
        WHERE province NOT IN ('Grand Total', '')
          AND province IS NOT NULL
        ORDER BY report_date
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["report_date"])


@st.cache_data(ttl=60)
def get_relief() -> pd.DataFrame:
    q = """
        SELECT report_date, province, item, quantity
        FROM ndma_relief
        WHERE province NOT IN ('Grand Total', '')
          AND province IS NOT NULL
        ORDER BY report_date
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["report_date"])


@st.cache_data(ttl=60)
def get_rescue() -> pd.DataFrame:
    q = """
        SELECT report_date, province, rescue_operations, persons_rescued
        FROM ndma_rescue
        WHERE province NOT IN ('Grand Total', '')
          AND province IS NOT NULL
        ORDER BY report_date
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["report_date"])


@st.cache_data(ttl=60)
def get_pmd_weather() -> pd.DataFrame:
    q = """
        SELECT city, humidity, max_temperature,
               day1_forecast, day2_forecast, day3_forecast, scraped_at
        FROM pmd_weather
        ORDER BY scraped_at DESC
        LIMIT 200
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["scraped_at"])


@st.cache_data(ttl=60)
def get_pmd_forecast() -> pd.DataFrame:
    q = """
        SELECT category, forecast, scraped_at
        FROM pmd_reports
        ORDER BY scraped_at DESC
        LIMIT 10
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["scraped_at"])


@st.cache_data(ttl=60)
def get_rainfall() -> pd.DataFrame:
    q = """
        SELECT report_date, station, rainfall_mm
        FROM pdma_rainfall_readings
        WHERE rainfall_mm > 0
        ORDER BY report_date DESC, rainfall_mm DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["report_date"])


@st.cache_data(ttl=60)
def get_gauge() -> pd.DataFrame:
    q = """
        SELECT report_datetime, station, river,
               current_level_ft, danger_level_ft,
               discharge_cusecs, flow_status
        FROM pdma_gauge_readings
        ORDER BY report_datetime DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(text(q), conn, parse_dates=["report_datetime"])


@st.cache_data(ttl=60)
def get_kpis() -> dict:
    queries = {
        "total_deaths":    "SELECT COALESCE(SUM(deaths), 0) FROM ndma_casualties WHERE province NOT IN ('Grand Total','')",
        "total_injured":   "SELECT COALESCE(SUM(injured), 0) FROM ndma_casualties WHERE province NOT IN ('Grand Total','')",
        "houses_damaged":  "SELECT COALESCE(SUM(houses_total), 0) FROM ndma_damage WHERE province NOT IN ('Grand Total','')",
        "persons_rescued": "SELECT COALESCE(SUM(persons_rescued), 0) FROM ndma_rescue WHERE province NOT IN ('Grand Total','')",
        "rainfall_stations": "SELECT COUNT(DISTINCT station) FROM pdma_rainfall_readings",
        "rivers_monitored":  "SELECT COUNT(DISTINCT river) FROM pdma_gauge_readings WHERE river IS NOT NULL",
    }
    result = {}
    with engine.connect() as conn:
        for key, q in queries.items():
            result[key] = conn.execute(text(q)).scalar() or 0
    return result
