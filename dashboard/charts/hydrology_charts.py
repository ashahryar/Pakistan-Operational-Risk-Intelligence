import pandas as pd
import plotly.graph_objects as go


# ==========================================================
# COLORS
# ==========================================================

BLUE = "#0ea5e9"
DARK_BLUE = "#0369a1"

RED = "#ef4444"
YELLOW = "#f59e0b"
GREEN = "#22c55e"

GRID = "rgba(120,132,150,0.14)"


# ==========================================================
# BASE LAYOUT
# ==========================================================

def _base(fig, title, height=400):

    fig.update_layout(

        title=dict(
            text=title,
            font=dict(
                size=16,
                family="Inter, Segoe UI, Arial",
            ),
            x=0.01,
            xanchor="left",
        ),

        height=height,

        paper_bgcolor="rgba(0,0,0,0)",

        plot_bgcolor="rgba(0,0,0,0)",

        margin=dict(
            l=20,
            r=35,
            t=55,
            b=35,
        ),

        font=dict(
            family="Inter, Segoe UI, Arial",
        ),

        hoverlabel=dict(
            font_size=13,
        ),

    )

    return fig


# ==========================================================
# 1. RIVER STATUS DISTRIBUTION
# ==========================================================

def river_status_distribution_bar(status_summary):

    order = [
        "Normal",
        "Watch",
        "Danger",
    ]

    df = status_summary.copy()

    df["Status"] = pd.Categorical(
        df["Status"],
        categories=order,
        ordered=True,
    )

    df = df.sort_values("Status")

    colors = []

    for status in df["Status"]:

        if status == "Normal":
            colors.append(GREEN)

        elif status == "Watch":
            colors.append(YELLOW)

        else:
            colors.append(RED)

    fig = go.Figure()

    fig.add_trace(

        go.Bar(

            x=df["Stations"],

            y=df["Status"],

            orientation="h",

            marker=dict(
                color=colors,
                line=dict(width=0),
            ),

            text=df["Stations"],

            texttemplate="%{text}",

            textposition="outside",

            hovertemplate=(
                "<b>%{y}</b><br>"
                "Stations: %{x}<extra></extra>"
            ),

        )

    )

    fig.update_xaxes(
        title="Stations",
        showgrid=True,
        gridcolor=GRID,
        rangemode="tozero",
    )

    fig.update_yaxes(
        title="",
        showgrid=False,
    )

    fig.update_layout(
        showlegend=False,
        bargap=0.35,
    )

    return _base(
        fig,
        "🛰 River Status Distribution",
        300,
    )


# ==========================================================
# 2. FLOOD RISK GAUGE
# ==========================================================

def flood_risk_gauge(risk_score):

    risk_score = max(
        0,
        min(
            float(risk_score),
            100,
        ),
    )

    if risk_score < 35:

        bar_color = GREEN

    elif risk_score < 70:

        bar_color = YELLOW

    else:

        bar_color = RED

    fig = go.Figure(

        go.Indicator(

            mode="gauge+number",

            value=risk_score,

            number={
                "suffix": "/100",
                "font": {
                    "size": 34,
                },
            },

            gauge={

                "axis": {
                    "range": [0, 100],
                    "tickwidth": 1,
                    "tickcolor": "#64748b",
                },

                "bar": {
                    "color": bar_color,
                    "thickness": 0.35,
                },

                "bgcolor": "rgba(0,0,0,0)",

                "steps": [

                    {
                        "range": [0, 35],
                        "color": "rgba(34,197,94,0.12)",
                    },

                    {
                        "range": [35, 70],
                        "color": "rgba(245,158,11,0.12)",
                    },

                    {
                        "range": [70, 100],
                        "color": "rgba(239,68,68,0.12)",
                    },

                ],

                "threshold": {

                    "line": {
                        "color": RED,
                        "width": 3,
                    },

                    "thickness": 0.8,

                    "value": 70,

                },

            },

        )

    )

    return _base(
        fig,
        "🚨 National Flood Risk Indicator",
        300,
    )


# ==========================================================
# 3. RIVER GAUGE COMPARISON
# ==========================================================

def gauge_comparison_bar(gauge):

    df = gauge.copy()

    required = [
        "station",
        "current_level_ft",
        "danger_level_ft",
    ]

    df = df.dropna(
        subset=[
            c for c in required
            if c in df.columns
        ]
    )

    if df.empty:

        return _base(
            go.Figure(),
            "📊 River Gauge Comparison",
            360,
        )

    # ------------------------------------------------------
    # Keep top 12 by current level
    # ------------------------------------------------------

    df = (
        df.sort_values(
            "current_level_ft",
            ascending=False,
        )
        .head(12)
        .sort_values(
            "current_level_ft",
            ascending=True,
        )
    )

    fig = go.Figure()

    # ------------------------------------------------------
    # Current level
    # ------------------------------------------------------

    fig.add_trace(

        go.Bar(

            y=df["station"],

            x=df["current_level_ft"],

            orientation="h",

            name="Current Level",

            marker_color=BLUE,

            text=df["current_level_ft"],

            texttemplate="%{text:.1f} ft",

            textposition="outside",

            hovertemplate=(
                "<b>%{y}</b><br>"
                "Current: %{x:.2f} ft"
                "<extra></extra>"
            ),

        )

    )

    # ------------------------------------------------------
    # Danger threshold as markers
    # ------------------------------------------------------

    fig.add_trace(

        go.Scatter(

            y=df["station"],

            x=df["danger_level_ft"],

            mode="markers",

            name="Danger Threshold",

            marker=dict(
                color=RED,
                size=11,
                symbol="line-ns-open",
                line=dict(
                    width=3,
                ),
            ),

            hovertemplate=(
                "<b>%{y}</b><br>"
                "Danger threshold: %{x:.2f} ft"
                "<extra></extra>"
            ),

        )

    )

    fig.update_layout(

        xaxis_title="Water Level (ft)",

        yaxis_title="",

        barmode="overlay",

        showlegend=True,

        legend=dict(
            orientation="h",
            y=1.08,
            x=1,
            xanchor="right",
        ),

    )

    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRID,
        rangemode="tozero",
    )

    fig.update_yaxes(
        showgrid=False,
    )

    return _base(
        fig,
        "📊 Current River Level vs Danger Threshold",
        max(360, len(df) * 34),
    )


# ==========================================================
# 4. RIVER RISK RANKING
# ==========================================================

def river_risk_ranking_bar(gauge):

    df = gauge.copy()

    if "risk_pct" not in df.columns:

        df["risk_pct"] = (
            df["current_level_ft"]
            / df["danger_level_ft"]
            * 100
        )

    df = df.replace(
        [float("inf"), -float("inf")],
        pd.NA,
    )

    df = df.dropna(
        subset=[
            "station",
            "risk_pct",
        ]
    )

    if df.empty:

        return _base(
            go.Figure(),
            "🌊 River Risk Ranking",
            360,
        )

    # ------------------------------------------------------
    # Top 12
    # ------------------------------------------------------

    df = (
        df.sort_values(
            "risk_pct",
            ascending=False,
        )
        .head(12)
        .sort_values(
            "risk_pct",
            ascending=True,
        )
    )

    # ------------------------------------------------------
    # Visual cap
    #
    # Actual value remains available in hover.
    # This prevents 8000% values destroying chart scale.
    # ------------------------------------------------------

    df["display_risk"] = df["risk_pct"].clip(
        upper=150
    )

    colors = []

    for value in df["risk_pct"]:

        if value >= 100:

            colors.append(RED)

        elif value >= 90:

            colors.append(YELLOW)

        else:

            colors.append(GREEN)

    fig = go.Figure()

    fig.add_trace(

        go.Bar(

            x=df["display_risk"],

            y=df["station"],

            orientation="h",

            marker=dict(
                color=colors,
                line=dict(width=0),
            ),

            text=[
                (
                    f"{v:.0f}%"
                    if v <= 150
                    else ">150%"
                )
                for v in df["risk_pct"]
            ],

            textposition="outside",

            hovertemplate=(
                "<b>%{y}</b><br>"
                "Risk: %{customdata:.1f}%"
                "<extra></extra>"
            ),

            customdata=df["risk_pct"],

        )

    )

    # ------------------------------------------------------
    # Threshold lines
    # ------------------------------------------------------

    fig.add_vline(
        x=90,
        line_dash="dash",
        line_color=YELLOW,
        line_width=2,
        annotation_text="Watch",
        annotation_position="top",
    )

    fig.add_vline(
        x=100,
        line_dash="dash",
        line_color=RED,
        line_width=2,
        annotation_text="Danger",
        annotation_position="top",
    )

    fig.update_xaxes(
        title="Current Level as % of Danger Threshold",
        range=[0, 150],
        showgrid=True,
        gridcolor=GRID,
    )

    fig.update_yaxes(
        title="",
        showgrid=False,
    )

    return _base(
        fig,
        "🌊 River Risk Ranking",
        max(360, len(df) * 34),
    )


# ==========================================================
# 5. RAINFALL
# ==========================================================

def top_rainfall_stations_bar(rainfall):

    df = rainfall.copy()

    df["rainfall_mm"] = pd.to_numeric(
        df["rainfall_mm"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "station",
            "rainfall_mm",
        ]
    )

    df = (
        df.sort_values(
            "rainfall_mm",
            ascending=False,
        )
        .head(10)
        .sort_values(
            "rainfall_mm",
        )
    )

    fig = go.Figure()

    fig.add_trace(

        go.Bar(

            x=df["rainfall_mm"],

            y=df["station"],

            orientation="h",

            marker=dict(
                color=BLUE,
                line=dict(width=0),
            ),

            text=df["rainfall_mm"],

            texttemplate="%{text:.1f} mm",

            textposition="outside",

            hovertemplate=(
                "<b>%{y}</b><br>"
                "Rainfall: %{x:.1f} mm"
                "<extra></extra>"
            ),

        )

    )

    fig.update_xaxes(
        title="Rainfall (mm)",
        showgrid=True,
        gridcolor=GRID,
    )

    fig.update_yaxes(
        title="",
        showgrid=False,
    )

    return _base(
        fig,
        "🌧 Top Rainfall Stations",
        380,
    )


# ==========================================================
# 6. DISCHARGE
# ==========================================================

def discharge_bar(gauge):

    if "discharge_cusecs" not in gauge.columns:

        return None

    df = gauge.copy()

    df["discharge_cusecs"] = pd.to_numeric(
        df["discharge_cusecs"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "station",
            "discharge_cusecs",
        ]
    )

    if df.empty:

        return None

    df = (
        df.sort_values(
            "discharge_cusecs",
            ascending=False,
        )
        .head(10)
        .sort_values(
            "discharge_cusecs",
        )
    )

    fig = go.Figure()

    fig.add_trace(

        go.Bar(

            x=df["discharge_cusecs"],

            y=df["station"],

            orientation="h",

            marker=dict(
                color=DARK_BLUE,
                line=dict(width=0),
            ),

            text=df["discharge_cusecs"],

            texttemplate="%{text:.0f}",

            textposition="outside",

            hovertemplate=(
                "<b>%{y}</b><br>"
                "Discharge: %{x:.0f} cusecs"
                "<extra></extra>"
            ),

        )

    )

    fig.update_xaxes(
        title="Discharge (Cusecs)",
        showgrid=True,
        gridcolor=GRID,
    )

    fig.update_yaxes(
        title="",
        showgrid=False,
    )

    return _base(
        fig,
        "💧 Top Water Discharge Stations",
        380,
    )