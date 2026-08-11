import pandas as pd
import streamlit as st

from dashboard.charts import weather_charts as charts
from dashboard.utils.search import (
    render_search_box,
    filter_dataframe_by_search,
)

NO_OBSERVATION = "No Recent Observation"


def render_weather_section(weather: pd.DataFrame) -> None:

    # ==========================================================
    # HEADER
    # ==========================================================

    st.markdown("## 🌡️ 💧 Weather Indicators")

    if weather.empty:

        with st.container(border=True):

            st.markdown("### 📭 No Weather Data Available")

            st.caption(
                "No PMD weather observations are available "
                "for the current reporting period."
            )

        return

    # ==========================================================
    # DATA PREPARATION
    # ==========================================================

    has_temp = (
        "max_temperature" in weather.columns
        and weather["max_temperature"].notna().any()
    )

    has_humidity = (
        "humidity" in weather.columns
        and weather["humidity"].notna().any()
    )

    hottest = None
    coldest = None
    humid = None

    if has_temp:

        hottest = weather.loc[
            weather["max_temperature"].idxmax()
        ]

        coldest = weather.loc[
            weather["max_temperature"].idxmin()
        ]

    if has_humidity:

        humid = weather.loc[
            weather["humidity"].idxmax()
        ]

    total_cities = (
        weather["city"].nunique()
        if "city" in weather.columns
        else 0
    )

    total_provinces = (
        weather["province"].nunique()
        if "province" in weather.columns
        else 0
    )

    latest_observation = None

    if "scraped_at" in weather.columns:

        latest_observation = pd.to_datetime(
            weather["scraped_at"],
            errors="coerce",
        ).max()

    # ==========================================================
    # COMMAND CENTER KPIs
    # ==========================================================

    k1, k2, k3, k4, k5 = st.columns(5)

    # ----------------------------------------------------------
    # HOTTEST
    # ----------------------------------------------------------

    with k1:

        st.metric(

            "🔥 Hottest City",

            (
                hottest["city"]
                if hottest is not None
                else NO_OBSERVATION
            ),

            (
                f"{hottest['max_temperature']:.1f} °C"
                if hottest is not None
                else None
            ),

        )

    # ----------------------------------------------------------
    # HUMIDITY
    # ----------------------------------------------------------

    with k2:

        st.metric(

            "💧 Highest Humidity",

            (
                humid["city"]
                if humid is not None
                else NO_OBSERVATION
            ),

            (
                f"{humid['humidity']:.0f}%"
                if humid is not None
                else None
            ),

        )

    # ----------------------------------------------------------
    # CITIES
    # ----------------------------------------------------------

    with k3:

        st.metric(

            "🏙 Cities Monitored",

            total_cities,

            "Across Pakistan",

        )

    # ----------------------------------------------------------
    # OBSERVATIONS
    # ----------------------------------------------------------

    with k4:

        st.metric(

            "📡 Observations",

            f"{len(weather):,}",

            "Total records",

        )

    # ----------------------------------------------------------
    # LATEST
    # ----------------------------------------------------------

    with k5:

        if (
            latest_observation is not None
            and pd.notna(latest_observation)
        ):

            latest_text = latest_observation.strftime(
                "%d %b %Y"
            )

            latest_time = latest_observation.strftime(
                "%I:%M %p"
            )

            st.metric(
                "🕒 Latest Observation",
                latest_text,
                latest_time,
            )

        else:

            st.metric(
                "🕒 Latest Observation",
                NO_OBSERVATION,
            )

    st.divider()

    # ==========================================================
    # WEATHER INDICATORS
    # ==========================================================

    left, right = st.columns(
        [1, 1],
        gap="large",
    )

    # ==========================================================
    # TEMPERATURE RANKING
    # ==========================================================

    with left:

        st.markdown(
            "#### 🔥 Temperature Ranking"
        )

        if has_temp:

            fig = charts.temperature_ranking_bar(
                weather
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False
                },
            )

        else:

            st.info(NO_OBSERVATION)

    # ==========================================================
    # HUMIDITY TREND
    # ==========================================================

    with right:

        st.markdown(
            "#### 💧 Humidity Trend"
        )

        if (
            has_humidity
            and "scraped_at" in weather.columns
        ):

            fig = charts.humidity_trend_line(
                weather
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False
                },
            )

        else:

            st.info(
                "Humidity trend requires "
                "observation timestamps."
            )

    st.divider()

    # ==========================================================
    # TEMPERATURE TREND
    # ==========================================================

    st.markdown(
        "### 📈 Temperature Trend"
    )

    if (
        has_temp
        and "scraped_at" in weather.columns
    ):

        fig = charts.temperature_trend_line(
            weather
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False
            },
        )

    else:

        st.info(
            "Temperature trend requires "
            "observation timestamps."
        )

    st.divider()

    # ==========================================================
    # EXECUTIVE WEATHER INSIGHTS
    # ==========================================================

    st.markdown(
        "### 🛰️ Executive Weather Insights"
    )

    i1, i2, i3 = st.columns(
        3,
        gap="large",
    )

    # ==========================================================
    # HEAT SIGNAL
    # ==========================================================

    with i1:

        with st.container(
            border=True
        ):

            st.markdown(
                "### 🔥 Heat Signal"
            )

            if hottest is not None:

                city = hottest.get(
                    "city",
                    "Unknown",
                )

                province = hottest.get(
                    "province",
                    "Unknown",
                )

                temperature = hottest.get(
                    "max_temperature"
                )

                st.markdown(
                    f"""
**City**

{city}

**Province**

{province}

**Temperature**

### {temperature:.1f} °C
"""
                )

                if temperature >= 45:

                    st.error(
                        "🔴 Extreme Heat Zone"
                    )

                elif temperature >= 40:

                    st.warning(
                        "🟠 High Temperature Zone"
                    )

                else:

                    st.success(
                        "🟢 Normal Temperature Range"
                    )

            else:

                st.info(
                    NO_OBSERVATION
                )

    # ==========================================================
    # HUMIDITY SIGNAL
    # ==========================================================

    with i2:

        with st.container(
            border=True
        ):

            st.markdown(
                "### 💧 Humidity Signal"
            )

            if humid is not None:

                city = humid.get(
                    "city",
                    "Unknown",
                )

                humidity_value = humid.get(
                    "humidity"
                )

                st.markdown(
                    f"""
**City**

{city}

**Humidity**

### {humidity_value:.0f}%
"""
                )

                if humidity_value >= 80:

                    st.error(
                        "🔴 Very High Humidity"
                    )

                elif humidity_value >= 60:

                    st.warning(
                        "🟡 Elevated Humidity"
                    )

                else:

                    st.success(
                        "🟢 Moderate Humidity"
                    )

            else:

                st.info(
                    NO_OBSERVATION
                )

    # ==========================================================
    # OBSERVATION NETWORK
    # ==========================================================

    with i3:

        with st.container(
            border=True
        ):

            st.markdown(
                "### 🌍 Observation Network"
            )

            st.markdown(
                f"""
**Cities**

### {total_cities}

**Provinces**

### {total_provinces}

**Observations**

### {len(weather):,}
"""
            )

            if total_cities >= 40:

                st.success(
                    "🟢 Strong Data Coverage"
                )

            elif total_cities >= 20:

                st.warning(
                    "🟡 Moderate Data Coverage"
                )

            else:

                st.info(
                    "🔵 Limited Data Coverage"
                )

    st.divider()

    # ==========================================================
    # PMD FORECAST DATASET
    # ==========================================================

    st.markdown(
        "### 📅 PMD Three-Day Forecast"
    )

    search_term = render_search_box(

        "Search City or Province",

        key="weather_table_search",

        placeholder=(
            "Enter city or province name..."
        ),

    )

    forecast = weather.copy()

    if "max_temperature" in forecast.columns:

        forecast = forecast.sort_values(
            "max_temperature",
            ascending=False,
        )

    forecast = filter_dataframe_by_search(

        forecast,

        search_term,

        columns=[
            "city",
            "province",
        ],

    )

    display_cols = [

        c

        for c in [

            "city",
            "province",
            "max_temperature",
            "humidity",
            "day1_forecast",
            "day2_forecast",
            "day3_forecast",

        ]

        if c in forecast.columns

    ]

    st.dataframe(

        forecast[display_cols],

        hide_index=True,

        use_container_width=True,

        height=420,

        column_config={

            "city":
                st.column_config.TextColumn(
                    "🏙 City",
                    width="medium",
                ),

            "province":
                st.column_config.TextColumn(
                    "Province",
                    width="medium",
                ),

            "max_temperature":
                st.column_config.ProgressColumn(
                    "Temperature",
                    min_value=0,
                    max_value=55,
                    format="%.1f °C",
                ),

            "humidity":
                st.column_config.ProgressColumn(
                    "Humidity",
                    min_value=0,
                    max_value=100,
                    format="%.0f %%",
                ),

            "day1_forecast":
                st.column_config.TextColumn(
                    "Tomorrow"
                ),

            "day2_forecast":
                st.column_config.TextColumn(
                    "Day 2"
                ),

            "day3_forecast":
                st.column_config.TextColumn(
                    "Day 3"
                ),

        },

    )

    st.divider()

    # ==========================================================
    # EXPORT
    # ==========================================================

    with st.container(
        border=True
    ):

        st.markdown(
            "### 📥 Export PMD Weather Dataset"
        )

        e1, e2, e3, e4 = st.columns(4)

        with e1:

            st.metric(
                "Records",
                f"{len(weather):,}",
            )

        with e2:

            st.metric(
                "Cities",
                total_cities,
            )

        with e3:

            st.metric(
                "Latest Temperature",

                (
                    f"{weather['max_temperature'].max():.1f} °C"
                    if has_temp
                    else NO_OBSERVATION
                ),

            )

        with e4:

            st.download_button(

                label="⬇ Download CSV",

                data=weather.to_csv(
                    index=False
                ).encode("utf-8"),

                file_name="pmd_weather.csv",

                mime="text/csv",

                use_container_width=True,

                key="download_weather_home",

            )