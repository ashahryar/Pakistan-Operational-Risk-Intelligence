import pandas as pd
import streamlit as st

from dashboard.charts import disaster_charts as charts


def render_disaster_section(
    casualties: pd.DataFrame
) -> None:

    # ==========================================================
    # HEADER
    # ==========================================================

    st.markdown(
        "## 🚨 Executive Disaster Intelligence Center"
    )

    if casualties.empty:

        st.info(
            "No disaster records available."
        )

        return

    # ==========================================================
    # DATA PREPARATION
    # ==========================================================

    province_summary = (

        casualties

        .groupby(
            "province",
            as_index=False
        )

        .agg(
            deaths=("deaths", "sum"),
            injured=("injured", "sum"),
        )

        .reset_index(drop=True)

    )

    province_summary["risk_score"] = (

        province_summary["deaths"] * 5
        + province_summary["injured"]

    )

    province_summary = (

        province_summary

        .sort_values(
            "risk_score",
            ascending=False
        )

        .reset_index(drop=True)

    )

    # ==========================================================
    # EXECUTIVE KPIs
    # ==========================================================

    most_affected = province_summary.iloc[0]

    total_deaths = int(
        casualties["deaths"].sum()
    )

    total_injured = int(
        casualties["injured"].sum()
    )

    if "district" in casualties.columns:

        districts_affected = (
            casualties["district"]
            .dropna()
            .nunique()
        )

    else:

        districts_affected = (
            province_summary["province"]
            .nunique()
        )

    latest_report = casualties[
        "report_date"
    ].max()

    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:

        st.metric(
            "🚨 Most Affected",
            most_affected["province"],
        )

    with k2:

        st.metric(
            "💀 Total Deaths",
            f"{total_deaths:,}",
        )

    with k3:

        st.metric(
            "🤕 Total Injured",
            f"{total_injured:,}",
        )

    with k4:

        st.metric(
            "🗺 Districts Affected",
            f"{districts_affected:,}",
        )

    with k5:

        st.metric(
            "📅 Latest Report",
            str(latest_report),
        )

    st.divider()

    # ==========================================================
    # PROVINCE RISK + TOP AFFECTED
    # ==========================================================

    left, right = st.columns(
        [2.15, 1]
    )

    # ----------------------------------------------------------
    # PROVINCE RISK
    # ----------------------------------------------------------

    with left:

        fig = charts.province_risk_ranking_bar(
            province_summary
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False
            },
        )

    # ----------------------------------------------------------
    # TOP AFFECTED PROVINCES
    # ----------------------------------------------------------

    with right:

        with st.container(
            border=True
        ):

            st.markdown(
                "##### 🏅 Top Affected Provinces"
            )

            top5 = (
                province_summary
                .head(5)
                .reset_index(drop=True)
            )

            medals = [
                "🥇",
                "🥈",
                "🥉",
                "4️⃣",
                "5️⃣",
            ]

            for i, row in top5.iterrows():

                col1, col2 = st.columns(
                    [0.45, 2.55]
                )

                with col1:

                    st.markdown(
                        f"""
                        <div style="
                            font-size:18px;
                            text-align:center;
                            padding-top:5px;
                        ">
                        {medals[i]}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with col2:

                    st.markdown(
                        f"""
                        <div style="
                            font-size:14px;
                            font-weight:600;
                            margin-bottom:1px;
                        ">
                        {row['province']}
                        </div>

                        <div style="
                            font-size:11px;
                            opacity:0.7;
                            margin-bottom:4px;
                        ">
                        Risk Score: {row['risk_score']:,.0f}
                        </div>

                        <div style="
                            font-size:11px;
                        ">
                        🔴 {row['deaths']:,.0f}
                        &nbsp;&nbsp;
                        🔵 {row['injured']:,.0f}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                if i < len(top5) - 1:

                    st.markdown(
                        """
                        <hr style="
                            margin:8px 0;
                            border:0;
                            border-top:
                            1px solid
                            rgba(120,132,150,0.18);
                        ">
                        """,
                        unsafe_allow_html=True,
                    )

    st.divider()

    # ==========================================================
    # NATIONAL CASUALTY TREND
    # ==========================================================

    fig = charts.casualty_trend_line(
        casualties
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": False
        },
    )

    st.divider()

    # ==========================================================
    # HEATMAP + PROVINCE COMPARISON
    # ==========================================================

    left, right = st.columns(
        [1.55, 1]
    )

    # ----------------------------------------------------------
    # HEATMAP
    # ----------------------------------------------------------

    with left:

        fig = charts.disaster_heatmap(
            province_summary
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False
            },
        )

    # ----------------------------------------------------------
    # DEATH VS INJURED
    # ----------------------------------------------------------

    with right:

        fig = charts.deaths_vs_injured_grouped_bar(
            province_summary
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False
            },
        )

    st.divider()

    # ==========================================================
    # LATEST DISASTER DATASET
    # ==========================================================

    st.markdown(
        "##### 📋 Latest Disaster Dataset"
    )

    show_cols = [

        c

        for c in [

            "report_date",
            "province",
            "district",
            "deaths",
            "injured",
            "houses_damaged",
            "persons_rescued",

        ]

        if c in casualties.columns

    ]

    display = (

        casualties[show_cols]

        .sort_values(
            "report_date",
            ascending=False
        )

    )

    st.dataframe(

        display,

        use_container_width=True,

        height=350,

        hide_index=True,

        row_height=28,

        column_config={

            "report_date":
                st.column_config.DatetimeColumn(
                    "📅 Date",
                    format="DD MMM HH:mm",
                ),

            "province":
                st.column_config.TextColumn(
                    "Province",
                    width="small",
                ),

            "district":
                st.column_config.TextColumn(
                    "District",
                    width="small",
                ),

            "deaths":
                st.column_config.NumberColumn(
                    "💀 Deaths",
                    format="%d",
                ),

            "injured":
                st.column_config.NumberColumn(
                    "🤕 Injured",
                    format="%d",
                ),

            "houses_damaged":
                st.column_config.NumberColumn(
                    "🏠 Houses",
                    format="%d",
                ),

            "persons_rescued":
                st.column_config.NumberColumn(
                    "🚑 Rescued",
                    format="%d",
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
            "##### 📥 Export Disaster Dataset"
        )

        e1, e2, e3, e4 = st.columns(
            [1, 1, 1, 1.35]
        )

        with e1:

            st.metric(
                "Records",
                f"{len(casualties):,}",
            )

        with e2:

            st.metric(
                "Provinces",
                casualties[
                    "province"
                ].nunique(),
            )

        with e3:

            st.metric(
                "Latest Report",
                str(latest_report),
            )

        with e4:

            st.download_button(

                label="⬇ Download CSV",

                data=(
                    casualties
                    .to_csv(index=False)
                    .encode("utf-8")
                ),

                file_name=(
                    "ndma_disaster_dataset.csv"
                ),

                mime="text/csv",

                use_container_width=True,

                key="download_ndma_home",

            )

    # ==========================================================
    # FOOTER
    # ==========================================================

    st.caption(
        f"Disaster intelligence coverage: "
        f"{len(casualties):,} records • "
        f"{province_summary['province'].nunique()} provinces • "
        f"{districts_affected:,} affected districts"
    )