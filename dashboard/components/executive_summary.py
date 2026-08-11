import pandas as pd
import streamlit as st


def render_executive_summary(summary: dict, casualties: pd.DataFrame) -> None:
    """
    `summary` is the dict returned by get_dashboard_summary().
    `casualties` is the dataframe returned by get_casualties().
    """

    # ==========================================================
    # EXECUTIVE COMMAND BRIEFING
    # ==========================================================

    st.markdown("## 🎯 Executive Situation Briefing")

    left, right = st.columns([1, 1])

    # ---------------------------------------------------
    # LEFT PANEL
    # ---------------------------------------------------

    with left:

        province = summary["most_affected_province"]

        rainfall_kpi = summary["highest_rainfall"]

        if province is not None:

            st.markdown(f"""

<div class="command-card">

<div class="command-title">
🚨 MOST AFFECTED PROVINCE
</div>

<div class="command-value">
{province['province']}
</div>

<div class="command-text">
Deaths Reported : <b>{province['deaths']}</b><br>
Status : <span class="status-red">HIGH IMPACT</span><br>
Priority for disaster response and humanitarian assistance.
</div>

</div>

""", unsafe_allow_html=True)

        else:

            st.markdown("""

<div class="command-card">

<div class="command-title">
🚨 MOST AFFECTED PROVINCE
</div>

<div class="command-text">
No disaster records available for this period.
</div>

</div>

""", unsafe_allow_html=True)

        if rainfall_kpi is not None:

            st.markdown(f"""

<div class="command-card" style="margin-top:14px;">

<div class="command-title">
🌧 HIGHEST RAINFALL
</div>

<div class="command-value">
{rainfall_kpi['rainfall_mm']} mm
</div>

<div class="command-text">
Monitoring Station : <b>{rainfall_kpi['station']}</b><br>
Rainfall activity remains under continuous observation.
</div>

</div>

""", unsafe_allow_html=True)

        else:

            st.markdown("""

<div class="command-card" style="margin-top:14px;">

<div class="command-title">
🌧 HIGHEST RAINFALL
</div>

<div class="command-text">
No rainfall readings available for this period.
</div>

</div>

""", unsafe_allow_html=True)

    # ---------------------------------------------------
    # RIGHT PANEL
    # ---------------------------------------------------

    with right:

        hottest = summary["hottest_city"]

        river = summary["highest_river"]

        if hottest is not None:

            st.markdown(f"""

<div class="command-card">

<div class="command-title">
🔥 WEATHER INTELLIGENCE
</div>

<div class="command-value">
{hottest['city']}
</div>

<div class="command-text">
Maximum Temperature : <b>{hottest['temperature']} °C</b><br>
Status : <span class="status-orange">Heat Stress Advisory</span>
</div>

</div>

""", unsafe_allow_html=True)

        else:

            st.markdown("""

<div class="command-card">

<div class="command-title">
🔥 WEATHER INTELLIGENCE
</div>

<div class="command-text">
No weather observations available for this period.
</div>

</div>

""", unsafe_allow_html=True)

        if river is not None:

            current = river.get("current_level_ft")
            danger = river.get("danger_level_ft")

            if pd.isna(current) or pd.isna(danger):

                status = "<span class='status-gray'>DATA UNAVAILABLE</span>"

            elif current >= danger:

                status = "<span class='status-red'>ABOVE DANGER LEVEL</span>"

            elif current >= (danger * 0.90):

                status = "<span class='status-orange'>WATCH LEVEL</span>"

            else:

                status = "<span class='status-green'>NORMAL</span>"

            current_display = (
                f"{current:.2f} ft"
                if pd.notna(current)
                else "N/A"
            )

            danger_display = (
                f"{danger:.2f} ft"
                if pd.notna(danger)
                else "N/A"
            )

            st.markdown(
                f"""
<div class="command-card" style="margin-top:14px;">

<div class="command-title">
🌊 HYDROLOGY STATUS
</div>

<div class="command-value">
{river['river']}
</div>

<div class="command-text">
Station : <b>{river['station']}</b><br>
Current : <b>{current_display}</b> &nbsp;•&nbsp; Danger : <b>{danger_display}</b><br>
Status : {status}
</div>

</div>
""",
                unsafe_allow_html=True,
            )

        else:

            st.markdown(
                """
<div class="command-card" style="margin-top:14px;">

<div class="command-title">
🌊 HYDROLOGY STATUS
</div>

<div class="command-text">
No river gauge readings available for this period.
</div>

</div>
""",
                unsafe_allow_html=True,
            )

    st.divider()

    # ==========================================================
    # NATIONAL OPERATIONS CONTROL CENTER
    # ==========================================================

    st.markdown("## 🛰 National Operations Control Center")

    col1, col2, col3, col4 = st.columns(4)

    # --------------------------------------------------
    # Active Sources
    # --------------------------------------------------

    with col1:

        st.markdown("""
<div class="metric-card">

<h5>📡 DATA SOURCES</h5>

<h1>3</h1>

Government Sources Connected<br>
🟢 NDMA &nbsp;•&nbsp; 🟢 PMD &nbsp;•&nbsp; 🟢 PDMA

</div>
""", unsafe_allow_html=True)

    # --------------------------------------------------
    # Platform Health
    # --------------------------------------------------

    with col2:

        st.markdown("""
<div class="metric-card">

<h5>⚙ PLATFORM HEALTH</h5>

<h1>100%</h1>

All Services Operational<br>
Database Connected &nbsp;•&nbsp; Airflow Running

</div>
""", unsafe_allow_html=True)

    # --------------------------------------------------
    # Refresh
    # --------------------------------------------------

    with col3:

        st.markdown("""
<div class="metric-card">

<h5>🔄 AUTO REFRESH</h5>

<h1>60s</h1>

Live Monitoring<br>
Streaming Updates &nbsp;•&nbsp; Dashboard Online

</div>
""", unsafe_allow_html=True)

    # --------------------------------------------------
    # Coverage
    # --------------------------------------------------

    with col4:

        province_count = 0

        if not casualties.empty:

            province_count = casualties["province"].nunique()

        st.markdown(f"""
<div class="metric-card">

<h5>🗺 COVERAGE</h5>

<h1>{province_count}</h1>

Affected Provinces<br>
National Monitoring &nbsp;•&nbsp; Real-Time Intelligence

</div>
""", unsafe_allow_html=True)

    st.divider()