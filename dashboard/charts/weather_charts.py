import pandas as pd
import plotly.graph_objects as go


# ==========================================================
# SHARED VISUAL LANGUAGE
# ==========================================================

_FONT = dict(
    family="Inter, Segoe UI, Arial, sans-serif"
)

_HOT_COLOR = "#ff7a18"
_HUMIDITY_COLOR = "#38bdf8"
_COLD_COLOR = "#38bdf8"

_GRID_COLOR = "rgba(148,163,184,0.10)"

_TEMP_SCALE = [
    [0.00, "#fef3c7"],
    [0.35, "#fbbf24"],
    [0.65, "#fb923c"],
    [1.00, "#ef4444"],
]


# ==========================================================
# BASE LAYOUT
# ==========================================================

def _apply_base_layout(fig, title, height):

    fig.update_layout(

        title=dict(
            text=title,
            font=dict(
                size=15,
                color="#f8fafc",
                **_FONT,
            ),
            x=0.02,
            xanchor="left",
        ),

        font=dict(
            family=_FONT["family"],
            color="#e5e7eb",
        ),

        height=height,

        paper_bgcolor="rgba(0,0,0,0)",

        plot_bgcolor="rgba(0,0,0,0)",

        margin=dict(
            l=55,
            r=35,
            t=55,
            b=45,
        ),

        hoverlabel=dict(
            bgcolor="#111827",
            bordercolor="#334155",
            font=dict(
                color="#f8fafc",
                size=12,
            ),
        ),

        showlegend=False,

    )

    return fig


# ==========================================================
# GET LATEST OBSERVATION PER CITY
# ==========================================================

def _latest_city_weather(weather):

    df = weather.copy()

    if "scraped_at" in df.columns:

        df["scraped_at"] = pd.to_datetime(
            df["scraped_at"],
            errors="coerce",
        )

        df = df.sort_values(
            "scraped_at"
        )

        if "city" in df.columns:

            df = df.drop_duplicates(
                subset=["city"],
                keep="last",
            )

    return df


# ==========================================================
# TEMPERATURE RANKING
# ==========================================================

def temperature_ranking_bar(weather: pd.DataFrame):

    df = _latest_city_weather(weather)

    if (
        "max_temperature" not in df.columns
        or "city" not in df.columns
    ):

        return go.Figure()

    top = (

        df.dropna(
            subset=["max_temperature"]
        )

        .sort_values(
            "max_temperature",
            ascending=False,
        )

        .head(10)

        .sort_values(
            "max_temperature",
            ascending=True,
        )

    )

    if top.empty:

        return go.Figure()

    fig = go.Figure()

    fig.add_trace(

        go.Bar(

            x=top["max_temperature"],

            y=top["city"],

            orientation="h",

            marker=dict(

                color=top["max_temperature"],

                colorscale=_TEMP_SCALE,

                showscale=False,

                line=dict(
                    width=0
                ),

            ),

            text=top["max_temperature"],

            texttemplate="%{text:.1f}°C",

            textposition="outside",

            cliponaxis=False,

            customdata=(
                top["province"]
                if "province" in top.columns
                else None
            ),

            hovertemplate=(

                "<b>%{y}</b><br>"

                "Temperature: %{x:.1f}°C"

                "<extra></extra>"

            ),

        )

    )

    max_temp = float(
        top["max_temperature"].max()
    )

    fig.update_xaxes(

        title="Temperature (°C)",

        range=[
            0,
            max_temp + max(5, max_temp * 0.12),
        ],

        showgrid=True,

        gridcolor=_GRID_COLOR,

        zeroline=False,

    )

    fig.update_yaxes(

        showgrid=False,

        automargin=True,

    )

    fig.update_layout(
        bargap=0.22,
    )

    return _apply_base_layout(
        fig,
        "🌡 Pakistan Temperature Ranking",
        410,
    )


# ==========================================================
# DAILY HUMIDITY TREND
# ==========================================================

def humidity_trend_line(weather: pd.DataFrame):

    if (
        "scraped_at" not in weather.columns
        or "humidity" not in weather.columns
    ):

        return go.Figure()

    df = weather.copy()

    df["scraped_at"] = pd.to_datetime(
        df["scraped_at"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "scraped_at",
            "humidity",
        ]
    )

    if df.empty:

        return go.Figure()

    # IMPORTANT:
    # Daily average instead of every raw observation

    df["date"] = df["scraped_at"].dt.date

    trend = (

        df.groupby("date", as_index=False)

        ["humidity"]

        .mean()

        .sort_values("date")

    )

    fig = go.Figure()

    fig.add_trace(

        go.Scatter(

            x=trend["date"],

            y=trend["humidity"],

            mode="lines+markers",

            line=dict(

                color=_HUMIDITY_COLOR,

                width=3,

                shape="spline",

                smoothing=0.5,

            ),

            marker=dict(

                size=6,

                color=_HUMIDITY_COLOR,

                line=dict(
                    width=2,
                    color="#0f172a",
                ),

            ),

            fill="tozeroy",

            fillcolor="rgba(56,189,248,0.08)",

            hovertemplate=(

                "<b>%{x|%d %b %Y}</b><br>"

                "Average Humidity: %{y:.0f}%"

                "<extra></extra>"

            ),

        )

    )

    fig.update_xaxes(

        title="",

        showgrid=False,

        zeroline=False,

    )

    fig.update_yaxes(

        title="Humidity (%)",

        range=[0, 100],

        showgrid=True,

        gridcolor=_GRID_COLOR,

        zeroline=False,

    )

    fig.update_layout(

        hovermode="x unified",

    )

    return _apply_base_layout(

        fig,

        "💧 Humidity Trend (Daily Average)",

        360,

    )


# ==========================================================
# DAILY TEMPERATURE TREND
# ==========================================================

def temperature_trend_line(weather: pd.DataFrame):

    if (
        "scraped_at" not in weather.columns
        or "max_temperature" not in weather.columns
    ):

        return go.Figure()

    df = weather.copy()

    df["scraped_at"] = pd.to_datetime(
        df["scraped_at"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "scraped_at",
            "max_temperature",
        ]
    )

    if df.empty:

        return go.Figure()

    # IMPORTANT:
    # Convert raw observations into daily national average

    df["date"] = df["scraped_at"].dt.date

    trend = (

        df.groupby("date", as_index=False)

        ["max_temperature"]

        .mean()

        .sort_values("date")

    )

    fig = go.Figure()

    fig.add_trace(

        go.Scatter(

            x=trend["date"],

            y=trend["max_temperature"],

            mode="lines+markers",

            line=dict(

                color=_HOT_COLOR,

                width=3,

                shape="spline",

                smoothing=0.5,

            ),

            marker=dict(

                size=6,

                color=_HOT_COLOR,

                line=dict(
                    width=2,
                    color="#0f172a",
                ),

            ),

            fill="tozeroy",

            fillcolor="rgba(255,122,24,0.08)",

            hovertemplate=(

                "<b>%{x|%d %b %Y}</b><br>"

                "Average Temperature: %{y:.1f}°C"

                "<extra></extra>"

            ),

        )

    )

    fig.update_xaxes(

        title="",

        showgrid=False,

        zeroline=False,

    )

    fig.update_yaxes(

        title="Temperature (°C)",

        showgrid=True,

        gridcolor=_GRID_COLOR,

        zeroline=False,

    )

    fig.update_layout(

        hovermode="x unified",

    )

    return _apply_base_layout(

        fig,

        "🌡 Temperature Trend (Daily Average)",

        360,

    )


# ==========================================================
# TEMPERATURE VS HUMIDITY
# ==========================================================

def temperature_vs_humidity_scatter(weather: pd.DataFrame):

    df = _latest_city_weather(weather)

    if not all(
        c in df.columns
        for c in [
            "max_temperature",
            "humidity",
            "city",
        ]
    ):

        return go.Figure()

    df = df.dropna(
        subset=[
            "max_temperature",
            "humidity",
        ]
    )

    fig = go.Figure()

    fig.add_trace(

        go.Scatter(

            x=df["max_temperature"],

            y=df["humidity"],

            mode="markers",

            marker=dict(

                size=11,

                color=df["max_temperature"],

                colorscale=_TEMP_SCALE,

                showscale=False,

                line=dict(
                    width=1,
                    color="#ffffff",
                ),

            ),

            customdata=(

                df[
                    [
                        "city",
                        "province",
                    ]
                ]

                if "province" in df.columns

                else df[["city"]]

            ),

            hovertemplate=(

                "<b>%{customdata[0]}</b><br>"

                "Temperature: %{x:.1f}°C<br>"

                "Humidity: %{y:.0f}%"

                "<extra></extra>"

            ),

        )

    )

    fig.update_xaxes(

        title="Temperature (°C)",

        showgrid=True,

        gridcolor=_GRID_COLOR,

    )

    fig.update_yaxes(

        title="Humidity (%)",

        range=[0, 100],

        showgrid=True,

        gridcolor=_GRID_COLOR,

    )

    return _apply_base_layout(

        fig,

        "🌡💧 Temperature vs Humidity",

        400,

    )