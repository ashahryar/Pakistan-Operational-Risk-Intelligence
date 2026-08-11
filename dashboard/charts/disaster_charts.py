import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ---------------------------------------------------------------------
# Shared visual language
# ---------------------------------------------------------------------

_FONT = dict(
    family="Inter, Segoe UI, Arial, sans-serif"
)

_DEATHS_COLOR = "#ef4444"
_INJURED_COLOR = "#2563eb"

_GRID_COLOR = "rgba(120,132,150,0.14)"

_RISK_SCALE = [
    [0.0, "#fee2e2"],
    [0.30, "#fecaca"],
    [0.55, "#fca5a5"],
    [0.75, "#f87171"],
    [1.0, "#b91c1c"],
]


# ---------------------------------------------------------------------
# Base layout
# ---------------------------------------------------------------------

def _apply_base_layout(fig, title, height):

    fig.update_layout(

        title=dict(
            text=title,
            font=dict(
                size=15,
                **_FONT
            ),
            x=0.01,
            xanchor="left",
        ),

        font=_FONT,

        height=height,

        paper_bgcolor="rgba(0,0,0,0)",

        plot_bgcolor="rgba(0,0,0,0)",

        margin=dict(
            l=20,
            r=25,
            t=48,
            b=25,
        ),

        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family=_FONT["family"],
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            title=None,
        ),

    )

    return fig


# ---------------------------------------------------------------------
# 1. Province Risk Ranking
# ---------------------------------------------------------------------

def province_risk_ranking_bar(
    province_summary: pd.DataFrame
):

    ranked = province_summary.copy()

    ranked["risk_score"] = (
        ranked["deaths"] * 5
        + ranked["injured"]
    )

    ranked = (
        ranked
        .sort_values(
            "risk_score",
            ascending=True
        )
    )

    fig = px.bar(

        ranked,

        x="risk_score",

        y="province",

        orientation="h",

        color="risk_score",

        color_continuous_scale=_RISK_SCALE,

        custom_data=[
            "deaths",
            "injured",
        ],

    )

    fig.update_traces(

        text=ranked["risk_score"],

        texttemplate="%{text:.0f}",

        textposition="outside",

        cliponaxis=False,

        marker_line_width=0,

        hovertemplate=(
            "<b>%{y}</b><br>"
            "Operational Risk: %{x:.0f}<br>"
            "Deaths: %{customdata[0]:,.0f}<br>"
            "Injured: %{customdata[1]:,.0f}"
            "<extra></extra>"
        ),

    )

    fig.update_layout(

        coloraxis_showscale=False,

        xaxis_title="Operational Risk Score",

        yaxis_title="",

        bargap=0.32,

    )

    fig.update_xaxes(

        showgrid=True,

        gridcolor=_GRID_COLOR,

        zeroline=False,

    )

    fig.update_yaxes(

        showgrid=False,

        automargin=True,

    )

    return _apply_base_layout(
        fig,
        "🏆 Province Risk Ranking",
        360,
    )


# ---------------------------------------------------------------------
# 2. Deaths vs Injured
# ---------------------------------------------------------------------

def deaths_vs_injured_grouped_bar(
    province_summary: pd.DataFrame
):

    ordered = (
        province_summary
        .sort_values(
            "deaths",
            ascending=False
        )
    )

    fig = go.Figure()

    # Deaths

    fig.add_trace(

        go.Bar(

            x=ordered["province"],

            y=ordered["deaths"],

            name="Deaths",

            marker=dict(
                color=_DEATHS_COLOR,
                line_width=0,
            ),

            hovertemplate=(
                "<b>%{x}</b><br>"
                "Deaths: %{y:,.0f}"
                "<extra></extra>"
            ),

        )

    )

    # Injured

    fig.add_trace(

        go.Bar(

            x=ordered["province"],

            y=ordered["injured"],

            name="Injured",

            marker=dict(
                color=_INJURED_COLOR,
                line_width=0,
            ),

            hovertemplate=(
                "<b>%{x}</b><br>"
                "Injured: %{y:,.0f}"
                "<extra></extra>"
            ),

        )

    )

    fig.update_layout(

        barmode="group",

        bargap=0.28,

        bargroupgap=0.08,

        xaxis_title="",

        yaxis_title="People",

        showlegend=True,

    )

    fig.update_xaxes(

        showgrid=False,

        tickangle=-15,

    )

    fig.update_yaxes(

        showgrid=True,

        gridcolor=_GRID_COLOR,

        zeroline=False,

    )

    return _apply_base_layout(

        fig,

        "⚖ Deaths vs Injured by Province",

        360,

    )


# ---------------------------------------------------------------------
# 3. National Casualty Trend
# ---------------------------------------------------------------------

def casualty_trend_line(
    casualties: pd.DataFrame
):

    trend = (

        casualties

        .groupby(
            "report_date",
            as_index=False
        )[[
            "deaths",
            "injured"
        ]]

        .sum()

        .sort_values(
            "report_date"
        )

    )

    fig = go.Figure()

    # Deaths

    fig.add_trace(

        go.Scatter(

            x=trend["report_date"],

            y=trend["deaths"],

            mode="lines+markers",

            name="Deaths",

            line=dict(
                width=3,
                color=_DEATHS_COLOR,
                shape="spline",
                smoothing=0.25,
            ),

            marker=dict(
                size=5,
            ),

            fill="tozeroy",

            fillcolor="rgba(239,68,68,0.07)",

            hovertemplate=(
                "Deaths: %{y:,.0f}"
                "<extra></extra>"
            ),

        )

    )

    # Injured

    fig.add_trace(

        go.Scatter(

            x=trend["report_date"],

            y=trend["injured"],

            mode="lines+markers",

            name="Injured",

            line=dict(
                width=3,
                color=_INJURED_COLOR,
                shape="spline",
                smoothing=0.25,
            ),

            marker=dict(
                size=5,
            ),

            fill="tozeroy",

            fillcolor="rgba(37,99,235,0.05)",

            hovertemplate=(
                "Injured: %{y:,.0f}"
                "<extra></extra>"
            ),

        )

    )

    fig.update_layout(

        hovermode="x unified",

        xaxis_title="",

        yaxis_title="Affected People",

    )

    fig.update_xaxes(

        showgrid=False,

        zeroline=False,

    )

    fig.update_yaxes(

        showgrid=True,

        gridcolor=_GRID_COLOR,

        zeroline=False,

    )

    return _apply_base_layout(

        fig,

        "📈 National Casualty Trend",

        390,

    )


# ---------------------------------------------------------------------
# 4. IMPROVED DISASTER HEATMAP
# ---------------------------------------------------------------------

def disaster_heatmap(
    province_summary: pd.DataFrame
):

    matrix = province_summary.copy()

    matrix["risk_score"] = (
        matrix["deaths"] * 5
        + matrix["injured"]
    )

    # ---------------------------------------------------------------
    # Sort provinces by overall risk
    # ---------------------------------------------------------------

    matrix = (
        matrix
        .sort_values(
            "risk_score",
            ascending=False
        )
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------------
    # Raw values
    # ---------------------------------------------------------------

    deaths = matrix["deaths"].astype(float)

    injured = matrix["injured"].astype(float)

    risk = matrix["risk_score"].astype(float)

    # ---------------------------------------------------------------
    # Normalize EACH metric independently to 0-100.
    #
    # This is the important fix.
    #
    # Previously Risk Score had a much larger numerical range and
    # completely dominated the heatmap.
    # ---------------------------------------------------------------

    def normalize(series):

        maximum = series.max()

        if maximum == 0 or pd.isna(maximum):

            return pd.Series(
                [0] * len(series),
                index=series.index,
            )

        return (
            series / maximum
        ) * 100

    normalized_deaths = normalize(deaths)

    normalized_injured = normalize(injured)

    normalized_risk = normalize(risk)

    z = [

        normalized_deaths.tolist(),

        normalized_injured.tolist(),

        normalized_risk.tolist(),

    ]

    # ---------------------------------------------------------------
    # Raw values shown inside cells
    # ---------------------------------------------------------------

    text = [

        [
            f"{int(v):,}"
            for v in deaths
        ],

        [
            f"{int(v):,}"
            for v in injured
        ],

        [
            f"{int(v):,}"
            for v in risk
        ],

    ]

    # ---------------------------------------------------------------
    # Heatmap
    # ---------------------------------------------------------------

    fig = go.Figure(

        go.Heatmap(

            z=z,

            x=matrix["province"],

            y=[
                "Deaths",
                "Injured",
                "Risk Score",
            ],

            text=text,

            texttemplate="%{text}",

            textfont=dict(
                size=12,
                color="#111827",
            ),

            colorscale=[

                [0.00, "#f8fafc"],

                [0.20, "#fecaca"],

                [0.45, "#fca5a5"],

                [0.70, "#f87171"],

                [1.00, "#b91c1c"],

            ],

            zmin=0,

            zmax=100,

            xgap=4,

            ygap=4,

            colorbar=dict(

                title="Intensity",

                thickness=12,

                len=0.80,

                ticksuffix="%",

            ),

            customdata=[

                [
                    deaths.iloc[i]
                    for i in range(len(matrix))
                ],

                [
                    injured.iloc[i]
                    for i in range(len(matrix))
                ],

                [
                    risk.iloc[i]
                    for i in range(len(matrix))
                ],

            ],

            hovertemplate=(
                "<b>%{x}</b><br>"
                "%{y}: %{z:.0f}% intensity"
                "<extra></extra>"
            ),

        )

    )

    fig.update_layout(

        xaxis_title="Province",

        yaxis_title="",

        margin=dict(
            l=70,
            r=25,
            t=48,
            b=45,
        ),

    )

    fig.update_xaxes(

        showgrid=False,

        tickangle=-15,

    )

    fig.update_yaxes(

        showgrid=False,

        autorange="reversed",

    )

    return _apply_base_layout(

        fig,

        "🔥 Disaster Intensity Heatmap",

        300,

    )