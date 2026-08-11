from datetime import datetime

import pandas as pd
import streamlit as st


def render_footer(
    casualties: pd.DataFrame,
    weather: pd.DataFrame,
    rainfall: pd.DataFrame,
    gauge: pd.DataFrame,
) -> None:

    # ==========================================================
    # DATA EXPORT CENTER
    # ==========================================================

    st.markdown("## 📥 Data Export Center")

    left, center, right = st.columns(3)

    # ---------------------------------------------------------
    # NDMA
    # ---------------------------------------------------------

    with left:

        with st.container(border=True):

            st.markdown("##### 🚨 NDMA Disaster Data")

            if not casualties.empty:

                st.metric(
                    "Records",
                    f"{len(casualties):,}"
                )

                st.download_button(

                    "⬇ Download NDMA CSV",

                    casualties.to_csv(index=False).encode(),

                    "ndma_dataset.csv",

                    "text/csv",

                    use_container_width=True,

                    key="download_ndma_final",

                )

            else:

                st.info("Dataset unavailable")

    # ---------------------------------------------------------
    # PMD
    # ---------------------------------------------------------

    with center:

        with st.container(border=True):

            st.markdown("##### 🌤 PMD Weather Data")

            if not weather.empty:

                st.metric(

                    "Records",

                    f"{len(weather):,}"

                )

                st.download_button(

                    "⬇ Download Weather CSV",

                    weather.to_csv(index=False).encode(),

                    "weather_dataset.csv",

                    "text/csv",

                    use_container_width=True,

                    key="download_weather_final",

                )

            else:

                st.info("Dataset unavailable")

    # ---------------------------------------------------------
    # PDMA
    # ---------------------------------------------------------

    with right:

        with st.container(border=True):

            st.markdown("##### 🌊 Hydrology Data")

            total = len(rainfall) + len(gauge)

            st.metric(

                "Records",

                f"{total:,}"

            )

            if not gauge.empty:

                st.download_button(

                    "⬇ Download River CSV",

                    gauge.to_csv(index=False).encode(),

                    "river_monitoring.csv",

                    "text/csv",

                    use_container_width=True,

                    key="download_river_final",

                )

            else:

                st.info("Dataset unavailable")

    st.divider()

    # ==========================================================
    # PROFESSIONAL FOOTER
    # ==========================================================

    st.markdown("""

---

<div style="text-align:center;padding:20px">

<h3>
🇵🇰 Pakistan Operational Risk Intelligence Platform
</h3>

<p style="font-size:17px">

Real-Time Disaster • Weather • Flood • Operational Risk Intelligence

</p>

</div>

""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.metric("Version", "2.0")

    with c2:

        st.metric("Environment", "Production")

    with c3:

        st.metric("Status", "🟢 Online")

    with c4:

        st.metric(
            "Updated",
            datetime.now().strftime("%H:%M")
        )

    st.caption(
        """
Developed as a Data Engineering Platform for real-time operational risk monitoring across Pakistan.

Government Data Sources:
- NDMA
- PMD
- PDMA Punjab

Dashboard refreshes automatically every 60 seconds.
"""
    )

    st.divider()

    # ==========================================================
    # END OF DASHBOARD
    # ==========================================================

    st.markdown(
        """
<div style='text-align:center;
padding:25px;
border-radius:15px;
background:linear-gradient(90deg,#2563eb,#1d4ed8);
color:white;'>

<h2 style='margin-bottom:8px;'>
Pakistan Operational Risk Intelligence Platform
</h2>

<p style='font-size:18px;'>

Real-Time Disaster • Weather • Flood • Operational Risk Intelligence

</p>

<p>

Developed using Modern Data Engineering & Cloud Technologies

</p>

</div>
""",
        unsafe_allow_html=True,
    )