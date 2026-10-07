"""dashboard/ui/charts.py

Task 42 -- one Plotly style for the whole dashboard (registered as the template "pori" and made the default). Charts follow the skill's chart guidance:
subtle gridlines, labelled axes with units, tooltips with exact values, a legend near the chart, readable type, no 3D, no decorative gauges, no gradients.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from dashboard.ui import tokens

P = tokens.PALETTE
# categorical series colours (colour-blind-safe set; never used to mean risk)
SERIES = ["#60A5FA", "#F59E0B", "#34D399", "#C084FC", "#F472B6", "#94A3B8"]

_layout = go.Layout(
    font=dict(family="Fira Sans, Segoe UI, sans-serif", size=13, color=P["text_2"]),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=SERIES,
    title=dict(font=dict(size=15, color=P["text"]), x=0, xanchor="left"),
    margin=dict(l=8, r=8, t=44, b=8),
    xaxis=dict(gridcolor="#1E2B42", linecolor=P["border"], zerolinecolor=P["border"], tickfont=dict(size=12), title=dict(font=dict(size=12))),
    yaxis=dict(gridcolor="#1E2B42", linecolor=P["border"], zerolinecolor=P["border"], tickfont=dict(size=12), title=dict(font=dict(size=12))),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=12)),
    hoverlabel=dict(bgcolor=P["elevated"], bordercolor=P["border"], font=dict(family="Fira Sans, sans-serif", size=13, color=P["text"])),
)
pio.templates["pori"] = go.layout.Template(layout=_layout)
pio.templates.default = "pori"


def style_fig(fig: go.Figure, title: str | None = None, height: int = 340, *, xtitle: str | None = None, ytitle: str | None = None, source: str | None = None) -> go.Figure:
    """Apply the standard layout. `source` is written under the chart as a source note."""
    fig.update_layout(template="pori", height=height, **({"title": dict(text=title)} if title else {}))
    if xtitle is not None:
        fig.update_xaxes(title_text=xtitle)
    if ytitle is not None:
        fig.update_yaxes(title_text=ytitle)
    if source:
        fig.add_annotation(text=source, xref="paper", yref="paper", x=0, y=-0.18, showarrow=False, font=dict(size=11, color=P["muted"]), xanchor="left")
    return fig


def map_layout(fig: go.Figure, height: int = 600) -> go.Figure:
    """The one map language: light-grey basemap for contrast with status fills, thin boundaries, no colour bar (a labelled legend is rendered instead)."""
    fig.update_layout(template="pori", height=height, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)      # the labelled legend is rendered as HTML (glyph + label) next to the map
    fig.update_traces(marker_line_color="#0B1220", marker_line_width=0.6, selector=dict(type="choroplethmap"))
    return fig
