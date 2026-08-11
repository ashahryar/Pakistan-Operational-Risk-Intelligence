import pandas as pd
import streamlit as st

from dashboard.components.filters import render_global_filters


def render_sidebar(
    casualties: pd.DataFrame,
    weather: pd.DataFrame,
    rainfall: pd.DataFrame,
    gauge: pd.DataFrame,
) -> dict:
    """
    Renders the full sidebar (Navigation + Global Filters + About
    Platform) and returns the filters dict produced by
    render_global_filters() — see components/filters.py for its shape.
    """

    with st.sidebar:

        # ==========================================================
        # NAVIGATION
        # ==========================================================

        st.image(
            "https://img.icons8.com/color/96/pakistan.png",
            width=70
        )

        st.markdown("## PORI Platform")

        st.caption("Operational Risk Intelligence")

        st.divider()

        st.success("● System Online")

        st.write("")

        st.markdown("### Connected Sources")

        st.write("✅ NDMA")

        st.write("✅ PMD")

        st.write("✅ PDMA")

        st.divider()

        st.markdown("### Infrastructure")

        st.write("⚡ Airflow")

        st.write("☁ AWS S3")

        st.write("🐘 PostgreSQL")

        st.write("📊 Streamlit")

        st.divider()

        # ==========================================================
        # GLOBAL FILTERS
        # ==========================================================

        filters = render_global_filters(casualties, weather, rainfall, gauge)

        st.divider()

        # ==========================================================
        # ABOUT PLATFORM
        # ==========================================================

        with st.expander("ℹ️ About Platform", expanded=False):

            st.markdown("""

**Pakistan Operational Risk Intelligence Platform**

A real-time disaster intelligence system monitoring operational
risks across Pakistan.

---

**Integrated Government Sources**
- NDMA Pakistan
- PMD Pakistan
- PDMA Punjab

---

**Purpose**

Real-time disaster, weather, and flood intelligence for national
operational risk monitoring.

---

**Technologies Used**
- Python
- PostgreSQL
- Apache Airflow
- Amazon S3
- AWS Glue
- Streamlit
- Plotly

---

**Version**

Executive Dashboard v2.0

""")

        st.divider()

        st.markdown("### Version")

        st.caption("Executive Dashboard v2.0")

    return filters