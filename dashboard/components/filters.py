from datetime import datetime

import pandas as pd
import streamlit as st


def _reset_filters(all_provinces, min_date, max_date):
    st.session_state["filter_provinces"] = list(all_provinces)
    st.session_state["filter_date_range"] = (min_date, max_date)
    st.session_state["filter_sources"] = ["NDMA", "PMD", "PDMA"]


def _apply_province_filter(df: pd.DataFrame, selected_provinces, all_provinces) -> pd.DataFrame:
    if df.empty or "province" not in df.columns:
        return df

    if set(selected_provinces) == set(all_provinces):
        return df

    return df[df["province"].isin(selected_provinces)]


def _apply_date_filter(df: pd.DataFrame, date_col: str, start, end) -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return df

    start_ts = pd.Timestamp(start)

    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    mask = (
        (df[date_col] >= start_ts)
        &
        (df[date_col] <= end_ts)
    )

    return df[mask]


def render_global_filters(
    casualties: pd.DataFrame,
    weather: pd.DataFrame,
    rainfall: pd.DataFrame,
    gauge: pd.DataFrame,
) -> dict:
    """
    Renders the Global Filters block (vertical, sidebar-width) and
    returns a dict:
        {
            "casualties": filtered copy of `casualties`,
            "weather":    filtered copy of `weather`,
            "rainfall":   filtered copy of `rainfall`,
            "gauge":      filtered copy of `gauge`,
            "show_ndma":  bool,
            "show_pmd":   bool,
            "show_pdma":  bool,
        }
    """

    # ----------------------------------------------------------
    # Build filter option sets from whatever data is available
    # ----------------------------------------------------------

    provinces = set()

    if not casualties.empty and "province" in casualties.columns:
        provinces.update(casualties["province"].dropna().unique())

    if not weather.empty and "province" in weather.columns:
        provinces.update(weather["province"].dropna().unique())

    all_provinces = sorted(provinces)

    date_values = []

    if not casualties.empty and "report_date" in casualties.columns:
        date_values += [casualties["report_date"].min(), casualties["report_date"].max()]

    if not weather.empty and "scraped_at" in weather.columns:
        date_values += [weather["scraped_at"].min(), weather["scraped_at"].max()]

    if not rainfall.empty and "report_date" in rainfall.columns:
        date_values += [rainfall["report_date"].min(), rainfall["report_date"].max()]

    if not gauge.empty and "report_datetime" in gauge.columns:
        date_values += [gauge["report_datetime"].min(), gauge["report_datetime"].max()]

    date_values = [d for d in date_values if pd.notna(d)]

    if date_values:
        min_date = min(date_values).date()
        max_date = max(date_values).date()
    else:
        min_date = max_date = datetime.now().date()

    # ----------------------------------------------------------
    # Session-state defaults (first run only)
    # ----------------------------------------------------------

    st.session_state.setdefault("filter_provinces", list(all_provinces))
    st.session_state.setdefault("filter_date_range", (min_date, max_date))
    st.session_state.setdefault("filter_sources", ["NDMA", "PMD", "PDMA"])

    # ----------------------------------------------------------
    # Filter UI — vertical, sidebar-width
    # ----------------------------------------------------------

    st.markdown("### 🎛 Global Filters")

    selected_provinces = st.multiselect(

        "Province",

        options=all_provinces,

        key="filter_provinces",

        help="Filters Disaster and Weather data by province. Rainfall "
             "and river gauge readings are not linked to a province "
             "in the source data.",

    )

    selected_range = st.date_input(

        "Date Range",

        key="filter_date_range",

        min_value=min_date,

        max_value=max_date,

        help="Filters records by report/observation date across all "
             "data sources.",

    )

    selected_sources = st.multiselect(

        "Source",

        options=["NDMA", "PMD", "PDMA"],

        key="filter_sources",

        help="NDMA = Disaster casualties · PMD = Weather · "
             "PDMA = Rainfall & River Gauges.",

    )

    st.button(

        "↺ Reset Filters",

        use_container_width=True,

        on_click=_reset_filters,

        args=(all_provinces, min_date, max_date),

    )

    # ----------------------------------------------------------
    # Normalize date range (date_input can return a single date
    # while the user is mid-selection)
    # ----------------------------------------------------------

    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date, end_date = min_date, max_date

    # ----------------------------------------------------------
    # Apply filters (row-level subsetting only)
    # ----------------------------------------------------------

    filtered_casualties = _apply_province_filter(
        casualties, selected_provinces, all_provinces
    )

    filtered_casualties = _apply_date_filter(
        filtered_casualties, "report_date", start_date, end_date
    )

    filtered_weather = _apply_province_filter(
        weather, selected_provinces, all_provinces
    )

    filtered_weather = _apply_date_filter(
        filtered_weather, "scraped_at", start_date, end_date
    )

    filtered_rainfall = _apply_date_filter(
        rainfall, "report_date", start_date, end_date
    )

    filtered_gauge = _apply_date_filter(
        gauge, "report_datetime", start_date, end_date
    )

    return {

        "casualties": filtered_casualties,

        "weather": filtered_weather,

        "rainfall": filtered_rainfall,

        "gauge": filtered_gauge,

        "show_ndma": "NDMA" in selected_sources,

        "show_pmd": "PMD" in selected_sources,

        "show_pdma": "PDMA" in selected_sources,

    }