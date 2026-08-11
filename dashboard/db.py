from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# ==========================================================
# SETUP
# ==========================================================

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(
    Path(__file__).resolve().parents[1] / ".env",
    override=True
)

logger = logging.getLogger("dashboard.db")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] dashboard.db: %(message)s")
    )
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)


# ==========================================================
# ENGINE (single reusable, pooled connection)
# ==========================================================

@st.cache_resource
def get_engine() -> Engine:

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "postgres")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    print("HOST =", host)
    print("PORT =", port)
    print("DB =", name)
    print("USER =", user)
    print("PASS =", password)

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    logger.info(
        "Creating SQLAlchemy engine for %s:%s/%s",
        host,
        port,
        name,
    )

    return create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

def _read_sql(
    query: str,
    params: Optional[dict] = None,
    parse_dates: Optional[list] = None,
) -> pd.DataFrame:
    """
    Internal helper: execute a read-only SQL query and always return
    a pandas DataFrame -- never a raw cursor, never an exception
    that reaches Streamlit. On failure, logs the error and returns
    an empty DataFrame so the dashboard keeps rendering.
    """

    try:

        engine = get_engine()

        with engine.connect() as conn:

            df = pd.read_sql(
                text(query),
                conn,
                params=params,
                parse_dates=parse_dates,
            )

        return df

    except Exception as exc:

        logger.error("Query failed: %s\nSQL: %s", exc, query)

        return pd.DataFrame()


# ==========================================================
# COMMON / GENERIC QUERY HELPERS
# ==========================================================

@st.cache_data(ttl=60)
def run_query(sql: str) -> pd.DataFrame:
    """
    Run an arbitrary read-only SQL statement and return the result
    as a DataFrame. Cached for 60 seconds. Never raises -- returns an
    empty DataFrame on error.
    """

    return _read_sql(sql)


@st.cache_data(ttl=60)
def get_dataframe(sql: str) -> pd.DataFrame:
    """
    Alias of run_query(), kept as a separate named entry point for
    call-site readability (e.g. ad-hoc exploratory queries in a
    notebook-style page). Identical behavior to run_query().
    """

    return run_query(sql)


def execute_query(sql: str) -> bool:
    """
    Execute a write statement (INSERT / UPDATE / DELETE / DDL) inside
    a transaction. Returns True on success, False on failure -- never
    raises, never returns a raw cursor.
    """

    try:

        engine = get_engine()

        with engine.begin() as conn:

            conn.execute(text(sql))

        return True

    except Exception as exc:

        logger.error("execute_query failed: %s\nSQL: %s", exc, sql)

        return False


def _clean_province_filter(column: str = "province") -> str:
    """
    Shared WHERE-clause fragment excluding null/blank/"Grand Total"
    rows that NDMA report exports commonly contain as summary rows.
    Used by every NDMA query to avoid duplicating this filter.
    """

    return (
        f"{column} IS NOT NULL "
        f"AND TRIM({column}) <> '' "
        f"AND {column} NOT ILIKE 'grand total'"
    )


# ==========================================================
# NDMA -- CASUALTIES
# ==========================================================

@st.cache_data(ttl=60)
def get_ndma_casualties() -> pd.DataFrame:
    """
    Return NDMA casualty reports: report_date, province, deaths,
    injured. One row per province per report date.
    """

    query = f"""
    SELECT
        report_date,
        province,
        deaths,
        injured
    FROM ndma_casualties
    WHERE {_clean_province_filter()}
    ORDER BY report_date
    """

    return _read_sql(query, parse_dates=["report_date"])


# ==========================================================
# NDMA -- INFRASTRUCTURE DAMAGE
# ==========================================================

@st.cache_data(ttl=60)
def get_ndma_damage() -> pd.DataFrame:
    """
    Return NDMA infrastructure damage reports: report_date, province,
    roads_km, bridges, houses_total, livestock.
    """

    query = f"""
    SELECT
        report_date,
        province,
        roads_km,
        bridges,
        houses_total,
        livestock
    FROM ndma_damage
    WHERE {_clean_province_filter()}
    ORDER BY report_date
    """

    return _read_sql(query, parse_dates=["report_date"])


# ==========================================================
# NDMA -- SUMMARY / PROVINCES / CITIES
# ==========================================================

@st.cache_data(ttl=60)
def get_ndma_summary() -> pd.DataFrame:
    """
    Return a single-row DataFrame of national NDMA totals, combining
    casualties, damage, and rescue operations:
        total_deaths, total_injured, total_houses_damaged,
        total_roads_km, total_bridges, total_livestock,
        total_persons_rescued, provinces_affected
    """

    query = f"""
    SELECT
        (SELECT COALESCE(SUM(deaths), 0)  FROM ndma_casualties WHERE {_clean_province_filter()}) AS total_deaths,
        (SELECT COALESCE(SUM(injured), 0) FROM ndma_casualties WHERE {_clean_province_filter()}) AS total_injured,
        (SELECT COALESCE(SUM(houses_total), 0) FROM ndma_damage WHERE {_clean_province_filter()}) AS total_houses_damaged,
        (SELECT COALESCE(SUM(roads_km), 0)     FROM ndma_damage WHERE {_clean_province_filter()}) AS total_roads_km,
        (SELECT COALESCE(SUM(bridges), 0)      FROM ndma_damage WHERE {_clean_province_filter()}) AS total_bridges,
        (SELECT COALESCE(SUM(livestock), 0)    FROM ndma_damage WHERE {_clean_province_filter()}) AS total_livestock,
        (SELECT COALESCE(SUM(persons_rescued), 0) FROM ndma_rescue WHERE {_clean_province_filter()}) AS total_persons_rescued,
        (SELECT COUNT(DISTINCT province) FROM ndma_casualties WHERE {_clean_province_filter()}) AS provinces_affected
    """

    return _read_sql(query)


@st.cache_data(ttl=60)
def get_ndma_provinces() -> pd.DataFrame:
    """
    Return the distinct list of provinces appearing across NDMA
    casualty and damage reports, as a single-column DataFrame
    (column: "province").
    """

    query = f"""
    SELECT DISTINCT province
    FROM (
        SELECT province FROM ndma_casualties WHERE {_clean_province_filter()}
        UNION
        SELECT province FROM ndma_damage WHERE {_clean_province_filter()}
    ) AS combined
    ORDER BY province
    """

    return _read_sql(query)


@st.cache_data(ttl=60)
def get_ndma_cities() -> pd.DataFrame:
    """
    NDMA source tables (ndma_casualties, ndma_damage, ndma_relief,
    ndma_rescue) only report at province granularity -- none of them
    have a city or district column. Rather than guess/invent one,
    this returns an empty DataFrame. Kept as a real function (not
    removed) so any caller expecting this name does not crash; it
    will simply receive no rows.
    """

    logger.info(
        "get_ndma_cities() called, but no NDMA table has a city "
        "column in the current schema -- returning empty DataFrame."
    )

    return pd.DataFrame(columns=["city"])


# ==========================================================
# PMD -- WEATHER
# ==========================================================

@st.cache_data(ttl=60)
def get_pmd_weather():
    query = """
        SELECT
            city,
            province,
            category,
            temperature AS max_temperature,
            humidity,
            forecast_day_1 AS day1_forecast,
            forecast_day_2 AS day2_forecast,
            forecast_day_3 AS day3_forecast,
            scraped_at
        FROM pmd_daily_forecast
        ORDER BY scraped_at DESC
    """

    df = _read_sql(query)

    print("========== PMD WEATHER DEBUG ==========")
    print("Rows:", len(df))
    print(df.head())
    print("========================================")

    return df

@st.cache_data(ttl=60)
def get_pmd_forecast() -> pd.DataFrame:
    """
    Return PMD weather alerts (type, severity, duration, affected
    regions, forecast text), most recent first -- so `.iloc[0]`
    always gives the latest active alert, matching how every page
    consumes this function.
    """

    query = """
    SELECT
        alert_type,
        severity,
        duration,
        regions,
        forecast,
        scraped_at
    FROM pmd_weather_alerts
    ORDER BY scraped_at DESC
    """

    return _read_sql(query, parse_dates=["scraped_at"])


@st.cache_data(ttl=60)
def get_latest_weather() -> pd.DataFrame:
    """
    Return only the most recent reading per city (same shape as
    get_pmd_weather()), using SQL DISTINCT ON for efficiency instead
    of fetching everything and de-duplicating in pandas.
    """

    query = """
    SELECT DISTINCT ON (w.city)
        w.city,
        COALESCE(g.province, 'Unknown') AS province,
        w.category,
        w.max_temperature,
        w.humidity,
        w.day1_forecast,
        w.day2_forecast,
        w.day3_forecast,
        w.scraped_at
    FROM pmd_weather w
    LEFT JOIN geo_locations g
        ON LOWER(TRIM(w.city)) = LOWER(TRIM(g.name))
        OR LOWER(TRIM(w.city)) = LOWER(TRIM(g.name_alt))
    ORDER BY w.city, w.scraped_at DESC
    """

    return _read_sql(query, parse_dates=["scraped_at"])


@st.cache_data(ttl=60)
def get_weather_summary() -> pd.DataFrame:
    """
    Return a single-row DataFrame of national weather KPIs computed
    from the latest reading per city: avg_temperature, avg_humidity,
    max_temperature, min_temperature, city_count, province_count.

    Numeric casts happen in SQL (::numeric) since max_temperature /
    humidity are stored as text.
    """

    query = """
    WITH latest AS (
        SELECT DISTINCT ON (w.city)
            w.city,
            COALESCE(g.province, 'Unknown') AS province,
            NULLIF(w.max_temperature, '')::numeric AS max_temperature,
            NULLIF(w.humidity, '')::numeric AS humidity
        FROM pmd_weather w
        LEFT JOIN geo_locations g
            ON LOWER(TRIM(w.city)) = LOWER(TRIM(g.name))
            OR LOWER(TRIM(w.city)) = LOWER(TRIM(g.name_alt))
        ORDER BY w.city, w.scraped_at DESC
    )
    SELECT
        AVG(max_temperature) AS avg_temperature,
        AVG(humidity) AS avg_humidity,
        MAX(max_temperature) AS max_temperature,
        MIN(max_temperature) AS min_temperature,
        COUNT(DISTINCT city) AS city_count,
        COUNT(DISTINCT province) AS province_count
    FROM latest
    """

    return _read_sql(query)


# ==========================================================
# PDMA -- RAINFALL
# ==========================================================

@st.cache_data(ttl=60)
def get_pdma_rainfall() -> pd.DataFrame:
    """
    Return PDMA rainfall gauge readings: report_date, station,
    rainfall_mm.

    NOTE: pdma_rainfall_readings has no `scraped_at` column in the
    schema (only `created_at`), so none is selected here. Pages that
    conditionally check `if "scraped_at" in df.columns:` already
    fall back to `report_date` gracefully.
    """

    query = """
    SELECT
        report_date,
        station,
        rainfall_mm
    FROM pdma_rainfall_readings
    ORDER BY report_date
    """

    return _read_sql(query, parse_dates=["report_date"])


@st.cache_data(ttl=60)
def get_latest_rainfall() -> pd.DataFrame:
    """
    Return only the most recent reading per rainfall station, using
    SQL DISTINCT ON instead of de-duplicating in pandas.
    """

    query = """
    SELECT DISTINCT ON (station)
        report_date,
        station,
        rainfall_mm
    FROM pdma_rainfall_readings
    ORDER BY station, report_date DESC
    """

    return _read_sql(query, parse_dates=["report_date"])


@st.cache_data(ttl=60)
def get_rainfall_summary() -> pd.DataFrame:
    """
    Return a single-row DataFrame of national rainfall KPIs:
    total_rainfall_mm, avg_rainfall_mm, max_rainfall_mm, station_count.
    """

    query = """
    SELECT
        COALESCE(SUM(rainfall_mm), 0) AS total_rainfall_mm,
        COALESCE(AVG(rainfall_mm), 0) AS avg_rainfall_mm,
        COALESCE(MAX(rainfall_mm), 0) AS max_rainfall_mm,
        COUNT(DISTINCT station) AS station_count
    FROM pdma_rainfall_readings
    """

    return _read_sql(query)


# ==========================================================
# PDMA -- RIVER GAUGES
# ==========================================================

@st.cache_data(ttl=60)
def get_pdma_rivers() -> pd.DataFrame:
    """
    Return PDMA river gauge readings: report_datetime, station,
    river, current_level_ft, danger_level_ft, discharge_cusecs,
    flow_status.
    """

    query = """
    SELECT
        report_datetime,
        station,
        river,
        current_level_ft,
        danger_level_ft,
        discharge_cusecs,
        flow_status
    FROM pdma_gauge_readings
    ORDER BY report_datetime
    """

    return _read_sql(query, parse_dates=["report_datetime"])


@st.cache_data(ttl=60)
def get_latest_river_levels() -> pd.DataFrame:
    """
    Return only the most recent reading per river gauge station,
    using SQL DISTINCT ON instead of de-duplicating in pandas.
    """

    query = """
    SELECT DISTINCT ON (station)
        report_datetime,
        station,
        river,
        current_level_ft,
        danger_level_ft,
        discharge_cusecs,
        flow_status
    FROM pdma_gauge_readings
    ORDER BY station, report_datetime DESC
    """

    return _read_sql(query, parse_dates=["report_datetime"])


@st.cache_data(ttl=60)
def get_river_summary() -> pd.DataFrame:
    """
    Return a single-row DataFrame of national river-network KPIs,
    computed from the latest reading per station:
        station_count, river_count, danger_count, watch_count,
        normal_count
    Thresholds mirror the risk logic already used on the River page
    (>= danger_level_ft -> Danger, >= 80% of danger_level_ft -> Watch).
    """

    query = """
    WITH latest AS (
        SELECT DISTINCT ON (station)
            station,
            river,
            current_level_ft,
            danger_level_ft
        FROM pdma_gauge_readings
        ORDER BY station, report_datetime DESC
    )
    SELECT
        COUNT(DISTINCT station) AS station_count,
        COUNT(DISTINCT river) AS river_count,
        COUNT(*) FILTER (
            WHERE current_level_ft IS NOT NULL
              AND danger_level_ft IS NOT NULL
              AND current_level_ft >= danger_level_ft
        ) AS danger_count,
        COUNT(*) FILTER (
            WHERE current_level_ft IS NOT NULL
              AND danger_level_ft IS NOT NULL
              AND current_level_ft >= (danger_level_ft * 0.80)
              AND current_level_ft < danger_level_ft
        ) AS watch_count,
        COUNT(*) FILTER (
            WHERE current_level_ft IS NOT NULL
              AND danger_level_ft IS NOT NULL
              AND current_level_ft < (danger_level_ft * 0.80)
        ) AS normal_count
    FROM latest
    """

    return _read_sql(query)


# ==========================================================
# BACKWARD-COMPATIBLE ALIASES
# ==========================================================
# The dashboard pages currently import these exact names. Rather
# than rename every page (out of scope for this task -- "do NOT
# modify my dashboard pages"), the required get_ndma_*/get_pdma_*
# functions above are the real implementations, and these are thin
# aliases so no page needs to change.

get_casualties = get_ndma_casualties
get_damage = get_ndma_damage
get_rainfall = get_pdma_rainfall
get_gauge = get_pdma_rivers


# ==========================================================
# DASHBOARD SUMMARY (composite, used by Home.py)
# ==========================================================

@st.cache_data(ttl=60)
def get_dashboard_summary() -> dict:
    """
    Return the composite summary dict Home.py expects:
        {
            "kpis": {
                "total_deaths": int,
                "total_injured": int,
                "houses_damaged": int,
                "persons_rescued": int,
                "rainfall_stations": int,
                "rivers": int,
            },
            "last_update": Timestamp | None,
            "most_affected_province": pd.Series | None,
            "highest_rainfall": pd.Series | None,
            "hottest_city": pd.Series | None,
            "highest_river": pd.Series | None,
            "latest_alert": pd.Series | None,
        }

    This is intentionally a dict (not a DataFrame) because Home.py
    accesses it as summary["kpis"] / summary["last_update"] -- it
    reuses the functions above rather than duplicating any SQL.
    """

    ndma = get_ndma_summary()

    kpis = {
        "total_deaths": int(ndma["total_deaths"].iloc[0]) if not ndma.empty else 0,
        "total_injured": int(ndma["total_injured"].iloc[0]) if not ndma.empty else 0,
        "houses_damaged": int(ndma["total_houses_damaged"].iloc[0]) if not ndma.empty else 0,
        "persons_rescued": int(ndma["total_persons_rescued"].iloc[0]) if not ndma.empty else 0,
        "rainfall_stations": int(get_rainfall_summary()["station_count"].iloc[0])
        if not get_rainfall_summary().empty
        else 0,
        # NOTE: components/executive_cards.py:20 reads kpi["rivers_monitored"],
        # not kpi["rivers"] -- this key name must match exactly or the
        # Executive KPI Command Center raises a KeyError on every load.
        "rivers_monitored": int(get_river_summary()["station_count"].iloc[0])
        if not get_river_summary().empty
        else 0,
    }

    # ---- last_update: most recent successful pipeline run ----

    pipeline_df = _read_sql(
        "SELECT MAX(finished_at) AS last_update FROM pipeline_logs "
        "WHERE status = 'success'",
        parse_dates=["last_update"],
    )

    last_update = (
        pipeline_df["last_update"].iloc[0]
        if not pipeline_df.empty and pd.notna(pipeline_df["last_update"].iloc[0])
        else None
    )

    # ---- most affected province (by total deaths) ----

    casualties = get_ndma_casualties()

    most_affected_province = None

    if not casualties.empty:

        by_province = (
            casualties.groupby("province", as_index=False)["deaths"].sum()
        )

        if not by_province.empty:

            most_affected_province = by_province.loc[
                by_province["deaths"].idxmax()
            ]

    # ---- highest rainfall reading ----

    rainfall = get_pdma_rainfall()

    highest_rainfall = None

    if not rainfall.empty:

        highest_rainfall = rainfall.loc[rainfall["rainfall_mm"].idxmax()]

    # ---- hottest city ----

    weather = get_latest_weather()

    hottest_city = None

    if not weather.empty:

        weather = weather.copy()

        weather["max_temperature"] = pd.to_numeric(
            weather["max_temperature"], errors="coerce"
        )

        weather = weather.dropna(subset=["max_temperature"])

        if not weather.empty:

            hottest_city = weather.loc[weather["max_temperature"].idxmax()].copy()

            # NOTE: components/executive_summary.py reads hottest['temperature'],
            # not hottest['max_temperature'] (sections/weather.py, which reads
            # the full weather DataFrame, correctly expects max_temperature --
            # this alias is added only on this single extracted row, not on
            # get_latest_weather()'s actual returned columns).
            hottest_city["temperature"] = hottest_city["max_temperature"]

    # ---- highest river level ----

    rivers = get_latest_river_levels()

    highest_river = None

    if not rivers.empty:

        rivers_valid = rivers.dropna(subset=["current_level_ft"])

        if not rivers_valid.empty:

            highest_river = rivers_valid.loc[
                rivers_valid["current_level_ft"].idxmax()
            ]

    # ---- latest weather alert ----

    alerts = get_pmd_forecast()

    latest_alert = alerts.iloc[0] if not alerts.empty else None

    return {
        "kpis": kpis,
        "last_update": last_update,
        "most_affected_province": most_affected_province,
        "highest_rainfall": highest_rainfall,
        "hottest_city": hottest_city,
        "highest_river": highest_river,
        "latest_alert": latest_alert,
    }