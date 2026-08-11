import pandas as pd
import streamlit as st

from dashboard.charts import hydrology_charts as charts


NO_DATA = "No Recent Observation"


# ==========================================================
# RIVER RISK CLASSIFICATION
# ==========================================================

def classify_status(current, danger):
    """
    Classify current river level against danger threshold.

    < 90%  -> Normal
    90-99% -> Watch
    >=100% -> Danger
    """

    try:

        current = float(current)
        danger = float(danger)

    except (TypeError, ValueError):

        return "Unknown"

    if pd.isna(current) or pd.isna(danger):
        return "Unknown"

    if danger <= 0:
        return "Unknown"

    ratio = current / danger

    if ratio >= 1.0:
        return "Danger"

    elif ratio >= 0.90:
        return "Watch"

    return "Normal"


# ==========================================================
# MAIN HYDROLOGY SECTION
# ==========================================================

def render_hydrology_section(
    rainfall: pd.DataFrame,
    gauge: pd.DataFrame,
) -> None:

    st.markdown("## 🌊 Executive Hydrology Intelligence")

    # ======================================================
    # EMPTY STATE
    # ======================================================

    if rainfall.empty and gauge.empty:

        with st.container(border=True):

            st.markdown("### 📭 No Hydrology Data Available")

            st.caption(
                "No PDMA rainfall or river gauge readings were found "
                "for the current reporting period."
            )

        return

    # ======================================================
    # RAINFALL PREPARATION
    # ======================================================

    station_count = 0
    highest_rain_value = None

    if not rainfall.empty:

        if "station" in rainfall.columns:

            station_count = rainfall["station"].nunique()

        if "rainfall_mm" in rainfall.columns:

            rainfall["rainfall_mm"] = pd.to_numeric(
                rainfall["rainfall_mm"],
                errors="coerce",
            )

            if rainfall["rainfall_mm"].notna().any():

                highest_rain_value = rainfall[
                    "rainfall_mm"
                ].max()

    # ======================================================
    # GAUGE PREPARATION
    # ======================================================

    gauge_clean = gauge.copy()

    if not gauge_clean.empty:

        # --------------------------------------------------
        # Convert numeric columns
        # --------------------------------------------------

        for col in [
            "current_level_ft",
            "danger_level_ft",
            "discharge_cusecs",
        ]:

            if col in gauge_clean.columns:

                gauge_clean[col] = pd.to_numeric(
                    gauge_clean[col],
                    errors="coerce",
                )

        # --------------------------------------------------
        # Latest reading per station
        # --------------------------------------------------

        if (
            "report_datetime" in gauge_clean.columns
            and "station" in gauge_clean.columns
        ):

            gauge_clean["report_datetime"] = pd.to_datetime(
                gauge_clean["report_datetime"],
                errors="coerce",
            )

            gauge_clean = (
                gauge_clean
                .sort_values("report_datetime")
                .drop_duplicates(
                    subset=["station"],
                    keep="last",
                )
            )

        elif "station" in gauge_clean.columns:

            gauge_clean = gauge_clean.drop_duplicates(
                subset=["station"],
                keep="last",
            )

        # --------------------------------------------------
        # Risk classification
        # --------------------------------------------------

        gauge_clean["status"] = gauge_clean.apply(
            lambda row: classify_status(
                row.get("current_level_ft"),
                row.get("danger_level_ft"),
            ),
            axis=1,
        )

        # --------------------------------------------------
        # Risk percentage
        # --------------------------------------------------

        gauge_clean["risk_pct"] = (
            gauge_clean["current_level_ft"]
            / gauge_clean["danger_level_ft"]
            * 100
        )

        gauge_clean.loc[
            gauge_clean["danger_level_ft"] <= 0,
            "risk_pct"
        ] = None

    # ======================================================
    # COUNTS
    # ======================================================

    if not gauge_clean.empty:

        normal_count = int(
            (gauge_clean["status"] == "Normal").sum()
        )

        watch_count = int(
            (gauge_clean["status"] == "Watch").sum()
        )

        danger_count = int(
            (gauge_clean["status"] == "Danger").sum()
        )

        classified_count = int(
            gauge_clean["status"].isin(
                ["Normal", "Watch", "Danger"]
            ).sum()
        )

        river_count = (
            gauge_clean["river"].nunique()
            if "river" in gauge_clean.columns
            else 0
        )

    else:

        normal_count = 0
        watch_count = 0
        danger_count = 0
        classified_count = 0
        river_count = 0

    # ======================================================
    # NETWORK HEALTH
    # ======================================================

    network_health = (

        normal_count / classified_count * 100

        if classified_count > 0

        else 0

    )

    # ======================================================
    # NATIONAL RISK SCORE
    # ======================================================

    if classified_count > 0:

        risk_score = round(
            (
                danger_count * 100
                + watch_count * 50
            )
            / classified_count
        )

    else:

        risk_score = 0

    # ======================================================
    # HIGHEST RIVER LEVEL
    # ======================================================

    highest_level_value = None

    if (
        not gauge_clean.empty
        and "current_level_ft" in gauge_clean.columns
        and gauge_clean["current_level_ft"].notna().any()
    ):

        highest_level_value = gauge_clean[
            "current_level_ft"
        ].max()

    # ======================================================
    # LATEST UPDATE
    # ======================================================

    latest_update = None

    if (
        not gauge_clean.empty
        and "report_datetime" in gauge_clean.columns
    ):

        latest_update = gauge_clean[
            "report_datetime"
        ].max()

    # ======================================================
    # EXECUTIVE KPIs
    # ======================================================

    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:

        st.metric(
            "🌊 Highest River Level",
            (
                f"{highest_level_value:.2f} ft"
                if pd.notna(highest_level_value)
                else NO_DATA
            ),
        )

    with k2:

        st.metric(
            "🌧 Highest Rainfall",
            (
                f"{highest_rain_value:.1f} mm"
                if pd.notna(highest_rain_value)
                else NO_DATA
            ),
        )

    with k3:

        st.metric(
            "🔴 Danger Rivers",
            danger_count,
        )

    with k4:

        st.metric(
            "🟡 Watch Rivers",
            watch_count,
        )

    with k5:

        st.metric(
            "🕒 Latest Update",
            (
                latest_update.strftime(
                    "%d %b %I:%M %p"
                )
                if pd.notna(latest_update)
                else NO_DATA
            ),
        )

    st.divider()

    # ======================================================
    # RIVER STATUS + FLOOD RISK
    # ======================================================

    left, right = st.columns([1.05, 0.95])

    # ======================================================
    # RIVER STATUS
    # ======================================================

    with left:

        st.markdown("##### 🛰 River Status Overview")

        if not gauge_clean.empty:

            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric(
                    "🟢 Normal",
                    normal_count,
                )

            with c2:
                st.metric(
                    "🟡 Watch",
                    watch_count,
                )

            with c3:
                st.metric(
                    "🔴 Danger",
                    danger_count,
                )

            status_summary = pd.DataFrame({
                "Status": [
                    "Normal",
                    "Watch",
                    "Danger",
                ],
                "Stations": [
                    normal_count,
                    watch_count,
                    danger_count,
                ],
            })

            fig = charts.river_status_distribution_bar(
                status_summary
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False,
                },
            )

            st.caption(
                f"Network health: {network_health:.0f}% "
                f"of classified stations are normal."
            )

        else:

            st.info(
                "No classified river gauge readings available."
            )

    # ======================================================
    # FLOOD RISK
    # ======================================================

    with right:

        st.markdown("##### 🚨 Flood Risk Indicators")

        fig = charts.flood_risk_gauge(
            risk_score
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False,
            },
        )

        if risk_score >= 70:

            st.error(
                f"🔴 High flood risk indicator: "
                f"{risk_score}/100"
            )

        elif risk_score >= 35:

            st.warning(
                f"🟡 Moderate flood risk indicator: "
                f"{risk_score}/100"
            )

        else:

            st.success(
                f"🟢 Low flood risk indicator: "
                f"{risk_score}/100"
            )

    st.divider()

    # ======================================================
    # RIVER GAUGE INTELLIGENCE
    # ======================================================

    st.markdown("##### 📊 River Gauge Intelligence")

    if not gauge_clean.empty:

        fig = charts.gauge_comparison_bar(
            gauge_clean
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False,
            },
        )

        fig = charts.river_risk_ranking_bar(
            gauge_clean
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False,
            },
        )

    else:

        st.info(
            "No river gauge readings are available."
        )

    st.divider()

    # ======================================================
    # RAINFALL + DISCHARGE
    # ======================================================

    left, right = st.columns(2)

    with left:

        st.markdown("##### 🌧 Rainfall Intelligence")

        if not rainfall.empty:

            fig = charts.top_rainfall_stations_bar(
                rainfall
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False,
                },
            )

            st.caption(
                f"{station_count} rainfall stations monitored."
            )

        else:

            st.info(
                "No rainfall readings available."
            )

    with right:

        st.markdown("##### 💧 Discharge Intelligence")

        if not gauge_clean.empty:

            fig = charts.discharge_bar(
                gauge_clean
            )

            if fig is not None:

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={
                        "displayModeBar": False,
                    },
                )

            else:

                st.info(
                    "Discharge readings are not available."
                )

        else:

            st.info(
                "No river gauge data available."
            )

    st.divider()

    # ======================================================
    # HYDROLOGY INSIGHTS
    # ======================================================

    st.markdown("##### 🎯 Hydrology Insights")

    i1, i2, i3 = st.columns(3)

    # ------------------------------------------------------
    # RAINFALL HOTSPOT
    # ------------------------------------------------------

    with i1:

        if (
            not rainfall.empty
            and "rainfall_mm" in rainfall.columns
            and rainfall["rainfall_mm"].notna().any()
        ):

            rain = rainfall.loc[
                rainfall["rainfall_mm"].idxmax()
            ]

            st.info(
                f"""
### 🌧 Rainfall Hotspot

**Station:** {rain['station']}

**Rainfall:**  
{rain['rainfall_mm']:.1f} mm

**Stations Monitored:**  
{station_count}
"""
            )

        else:

            st.info(
                "### 🌧 Rainfall Hotspot\n\n"
                "No rainfall data available."
            )

    # ------------------------------------------------------
    # RIVER HOTSPOT
    # ------------------------------------------------------

    with i2:

        if (
            not gauge_clean.empty
            and gauge_clean["current_level_ft"].notna().any()
        ):

            river = gauge_clean.loc[
                gauge_clean["current_level_ft"].idxmax()
            ]

            status = river["status"]

            icon = {
                "Danger": "🔴",
                "Watch": "🟡",
                "Normal": "🟢",
            }.get(
                status,
                "⚪",
            )

            st.info(
                f"""
### 🌊 River Hotspot

**River:** {river.get('river', 'Unknown')}

**Station:** {river.get('station', 'Unknown')}

**Current Level:**  
{river['current_level_ft']:.2f} ft

**Status:**  
{icon} {status}
"""
            )

        else:

            st.info(
                "### 🌊 River Hotspot\n\n"
                "No river level data available."
            )

    # ------------------------------------------------------
    # NETWORK
    # ------------------------------------------------------

    with i3:

        if danger_count > 0:

            status_label = "🔴 High Risk"

        elif watch_count > 0:

            status_label = "🟡 Monitoring"

        else:

            status_label = "🟢 Normal"

        st.success(
            f"""
### 📡 Network Status

**Rivers Monitored:**  
{river_count}

**Classified Stations:**  
{classified_count}

**Network Health:**  
{network_health:.0f}%

**Current Status:**  
{status_label}
"""
        )

    st.divider()

    # ======================================================
    # EXECUTIVE ASSESSMENT
    # ======================================================

    st.markdown("##### 🧭 Executive Hydrology Assessment")

    with st.container(border=True):

        if danger_count > 0:

            st.error(
                f"🔴 **Immediate Attention:** "
                f"{danger_count} station(s) are above "
                f"the danger threshold."
            )

        elif watch_count > 0:

            st.warning(
                f"🟡 **Enhanced Monitoring:** "
                f"{watch_count} station(s) are approaching "
                f"their danger threshold."
            )

        elif classified_count > 0:

            st.success(
                "🟢 **Current River Conditions:** "
                "All classified river stations are within "
                "normal levels."
            )

        else:

            st.info(
                "⚪ **Assessment Limited:** "
                "Insufficient river gauge data."
            )

    st.divider()

    # ======================================================
    # DATASET
    # ======================================================

    st.markdown("##### 🌊 River Monitoring Dataset")

    if not gauge_clean.empty:

        display = gauge_clean.copy()

        display["Risk"] = display["status"].map({
            "Danger": "🔴 Danger",
            "Watch": "🟡 Watch",
            "Normal": "🟢 Normal",
            "Unknown": "⚪ Unknown",
        })

        search = st.text_input(
            "🔍 Search River / Station",
            placeholder="Enter station or river name...",
            key="hydrology_river_search",
        )

        if search:

            q = search.lower()

            mask = (
                display["station"]
                .astype(str)
                .str.lower()
                .str.contains(q, na=False)
            )

            if "river" in display.columns:

                mask |= (
                    display["river"]
                    .astype(str)
                    .str.lower()
                    .str.contains(q, na=False)
                )

            display = display[mask]

        if "risk_pct" in display.columns:

            display = display.sort_values(
                "risk_pct",
                ascending=False,
            )

        cols = [
            "station",
            "river",
            "current_level_ft",
            "danger_level_ft",
            "risk_pct",
            "discharge_cusecs",
            "flow_status",
            "Risk",
        ]

        cols = [
            c for c in cols
            if c in display.columns
        ]

        st.dataframe(
            display[cols],
            hide_index=True,
            use_container_width=True,
            height=450,
            column_config={

                "station": st.column_config.TextColumn(
                    "📍 Station",
                ),

                "river": st.column_config.TextColumn(
                    "🌊 River",
                ),

                "current_level_ft": st.column_config.NumberColumn(
                    "Current",
                    format="%.2f ft",
                ),

                "danger_level_ft": st.column_config.NumberColumn(
                    "Danger",
                    format="%.2f ft",
                ),

                "risk_pct": st.column_config.NumberColumn(
                    "Risk",
                    format="%.0f%%",
                ),

                "discharge_cusecs": st.column_config.NumberColumn(
                    "Discharge",
                    format="%.0f",
                ),

                "flow_status": st.column_config.TextColumn(
                    "Flow",
                ),

                "Risk": st.column_config.TextColumn(
                    "Risk Status",
                ),
            },
        )

    else:

        st.info(
            "No river monitoring records are available."
        )

    # ======================================================
    # FOOTER
    # ======================================================

    st.caption(
        f"Hydrology coverage: "
        f"{station_count} rainfall stations • "
        f"{river_count} rivers • "
        f"{classified_count} classified gauge stations"
    )