"""
dashboard/sections/geo_intelligence.py

Phase 1 / Task 12 (ADR-0001) -- Geographic Observation Intelligence
section: surfaces Task 11's geo.resolved_observation_counts view (real
observation volume resolved to Task 10's canonical province/district
geography) on the Home dashboard, matching the existing section
pattern (dashboard/sections/disaster.py etc.) -- st.metric KPI row,
one Plotly chart, one data table, a caption footer.

Read-only: the DataFrame this renders is produced entirely by
dashboard/db.py::get_geo_summary() (a single SELECT against the view)
-- nothing here writes to the database.
"""

import pandas as pd
import streamlit as st

from dashboard.charts import geo_charts as charts
from dashboard.utils.geo_helpers import summarize_geo_observations


def render_geo_intelligence_section(geo_summary: pd.DataFrame) -> None:

    st.markdown("## 🗺 Geographic Observation Intelligence")

    if geo_summary.empty:

        st.info(
            "No resolved geographic observations available yet -- "
            "run scripts/geo/resolve_observations.py (Task 10)."
        )

        return

    stats = summarize_geo_observations(geo_summary)

    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.metric(
            "📊 Resolved Observations",
            f"{stats['total_observations']:,}",
        )

    with k2:
        st.metric(
            "🗺 Admin Units Covered",
            f"{stats['admin_unit_count']:,}",
        )

    with k3:
        st.metric(
            "🏷 Data Sources",
            f"{geo_summary['source'].nunique():,}",
        )

    with k4:
        st.metric(
            "🧭 Domains Resolved",
            f"{geo_summary['domain'].nunique():,}",
        )

    st.divider()

    left, right = st.columns([2, 1])

    with left:

        fig = charts.geo_observation_bar(stats["by_admin_unit"])

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
        )

    with right:

        with st.container(border=True):

            st.markdown("##### 🧾 Source / Domain Breakdown")

            st.dataframe(
                stats["by_source_domain"],
                use_container_width=True,
                hide_index=True,
                height=350,
                row_height=28,
                column_config={
                    "source": st.column_config.TextColumn(
                        "Source", width="small",
                    ),
                    "domain": st.column_config.TextColumn(
                        "Domain",
                    ),
                    "observation_count": st.column_config.NumberColumn(
                        "Observations", format="%d",
                    ),
                },
            )

    st.caption(
        f"Geographic resolution coverage (Task 10/11): "
        f"{stats['total_observations']:,} real observations resolved "
        f"to {stats['admin_unit_count']:,} canonical admin units across "
        f"{geo_summary['source'].nunique()} sources. Ambiguous/unresolved "
        f"raw values are intentionally excluded, never guessed."
    )
