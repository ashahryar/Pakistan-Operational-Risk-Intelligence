"""
dashboard/charts/geo_charts.py

Phase 1 / Task 12 (ADR-0001) -- chart(s) for the Geographic Observation
Intelligence section. Mirrors the existing dark-theme visual language
already established in dashboard/charts/disaster_charts.py (same
template, font, grid color, base-layout shape) without importing that
module's private helper -- kept self-contained so no existing chart
file is touched.
"""

import pandas as pd
import plotly.express as px

_FONT = dict(family="Inter, Segoe UI, Arial, sans-serif")

_TEXT_COLOR = "#dde3e7"
_TEXT_MUTED = "#bbc9cf"
_GRID_COLOR = "rgba(133,147,153,0.14)"

_GEO_SCALE = [
    [0.0, "#2f3639"],
    [0.35, "#3c6e71"],
    [0.65, "#2aa198"],
    [1.0, "#6fe7dc"],
]


def _apply_base_layout(fig, title, height):

    fig.update_layout(
        template="pori",
        title=dict(
            text=title,
            font=dict(size=15, color=_TEXT_COLOR, **_FONT),
            x=0.01,
            xanchor="left",
        ),
        font=dict(color=_TEXT_MUTED, **_FONT),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=25, t=48, b=25),
        hoverlabel=dict(
            bgcolor="#1a2123",
            bordercolor="#3c494e",
            font_size=12,
            font_color=_TEXT_COLOR,
            font_family=_FONT["family"],
        ),
        showlegend=False,
    )

    return fig


def geo_observation_bar(by_admin_unit: pd.DataFrame, top_n: int = 15):
    """
    Horizontal bar chart of resolved observation counts by canonical
    admin unit (province or district), top `top_n` by volume.
    """

    ranked = (
        by_admin_unit.sort_values("observation_count", ascending=False)
        .head(top_n)
        .sort_values("observation_count", ascending=True)
    )

    fig = px.bar(
        ranked,
        x="observation_count",
        y="admin_unit_name",
        orientation="h",
        color="observation_count",
        color_continuous_scale=_GEO_SCALE,
        custom_data=["level"],
    )

    fig.update_traces(
        text=ranked["observation_count"],
        texttemplate="%{text:,.0f}",
        textposition="outside",
        cliponaxis=False,
        marker_line_width=0,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Resolved observations: %{x:,.0f}<br>"
            "Level: %{customdata[0]}"
            "<extra></extra>"
        ),
    )

    fig.update_layout(
        coloraxis_showscale=False,
        xaxis_title="Resolved Observations",
        yaxis_title="",
        bargap=0.32,
    )

    fig.update_xaxes(showgrid=True, gridcolor=_GRID_COLOR, zeroline=False)
    fig.update_yaxes(showgrid=False, automargin=True)

    return _apply_base_layout(
        fig, "🗺 Resolved Observations by Admin Unit", 400
    )
