import streamlit as st


def render_executive_cards(kpi: dict) -> None:
    """
    `kpi` is `summary["kpis"]` from get_dashboard_summary().
    """

    # ==========================================================
    # EXECUTIVE KPI COMMAND CENTER
    # ==========================================================

    st.markdown("## 🎯 National Operational Risk Overview")

    total_deaths = kpi["total_deaths"]
    total_injured = kpi["total_injured"]
    houses = kpi["houses_damaged"]
    rescued = kpi["persons_rescued"]
    rainfall_stations = kpi["rainfall_stations"]
    rivers = kpi["rivers_monitored"]

    # Card styling (background, border, hover, typography) lives in the
    # shared design system at styles/style.css (.metric-box, .metric-title,
    # .metric-number, .metric-desc) so every KPI card across the app stays
    # visually consistent and theme-aware (light/dark).

    c1, c2, c3 = st.columns(3)

    with c1:

        st.markdown(f"""
<div class="metric-box">

<div class="metric-title">
💀 Total Deaths
</div>

<div class="metric-number">
{total_deaths:,}
</div>

<div class="metric-desc">
National Fatalities
</div>

</div>
""", unsafe_allow_html=True)

    with c2:

        st.markdown(f"""
<div class="metric-box">

<div class="metric-title">
🤕 Injured People
</div>

<div class="metric-number">
{total_injured:,}
</div>

<div class="metric-desc">
Reported Nationwide
</div>

</div>
""", unsafe_allow_html=True)

    with c3:

        st.markdown(f"""
<div class="metric-box">

<div class="metric-title">
🏠 Houses Damaged
</div>

<div class="metric-number">
{houses:,}
</div>

<div class="metric-desc">
Infrastructure Impact
</div>

</div>
""", unsafe_allow_html=True)

    c4, c5, c6 = st.columns(3)

    with c4:

        st.markdown(f"""
<div class="metric-box">

<div class="metric-title">
🚁 Persons Rescued
</div>

<div class="metric-number">
{rescued:,}
</div>

<div class="metric-desc">
Emergency Response
</div>

</div>
""", unsafe_allow_html=True)

    with c5:

        st.markdown(f"""
<div class="metric-box">

<div class="metric-title">
🌧 Rainfall Stations
</div>

<div class="metric-number">
{rainfall_stations:,}
</div>

<div class="metric-desc">
Live Monitoring
</div>

</div>
""", unsafe_allow_html=True)

    with c6:

        st.markdown(f"""
<div class="metric-box">

<div class="metric-title">
🌊 River Stations
</div>

<div class="metric-number">
{rivers:,}
</div>

<div class="metric-desc">
Hydrology Network
</div>

</div>
""", unsafe_allow_html=True)

    st.divider()
