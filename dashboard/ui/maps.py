"""dashboard/ui/maps.py

Task 42 -- the one map language: Plotly choropleth over the COD-AB boundaries, filled with the shared risk-status palette (dashboard/ui/tokens.py), each
status also named in the hover text and in the legend (never colour alone), unresolved/no-record areas drawn in the neutral "No risk record" fill,
a thicker outline on the selected area, no colour bar. A geography with no boundary is never drawn.
"""

from __future__ import annotations

from typing import Optional

import plotly.graph_objects as go

from dashboard.ui import tokens
from dashboard.ui.charts import map_layout
from dashboard.utils.risk_map_helpers import NO_DATA, STATUS_ORDER, map_frame, mapped_geojson

ATTRIBUTION = "Boundaries: COD-AB v01 (2022-09-09, CC BY-IGO), a third-party dataset that is not government-certified. Basemap © OpenStreetMap contributors © CARTO."


def risk_choropleth(fc: dict, *, selected_id: Optional[int] = None, height: int = 600, zoom: float = 4.3) -> Optional[go.Figure]:
    """Figure for a risk FeatureCollection, or None when no area has a boundary (the caller shows an empty state)."""
    frame = map_frame(fc)
    if frame.empty:
        return None
    gj = mapped_geojson(fc)
    fig = go.Figure()
    for status in [s for s in STATUS_ORDER + [NO_DATA] if s in set(frame["status"])]:
        part = frame[frame["status"] == status]
        text = [f"<b>{r.admin_unit_name}</b><br>{tokens.status_glyph(status)} {tokens.status_label(status)}<br>{r.province or '—'} · "
                f"{('risk date ' + str(r.risk_date)) if r.risk_date else 'no risk record'}<br>Numeric score: not computed" for r in part.itertuples()]
        fig.add_trace(go.Choroplethmap(
            geojson=gj, locations=part["admin_unit_id"], featureidkey="properties.admin_unit_id", z=[1] * len(part), showscale=False,
            colorscale=[[0, tokens.status_fill(status)], [1, tokens.status_fill(status)]], marker=dict(opacity=0.78, line=dict(color="#0B1220", width=0.6)),
            name=f"{tokens.status_glyph(status)} {tokens.status_label(status)}", showlegend=False, hovertext=text, hoverinfo="text"))
    if selected_id is not None and selected_id in set(frame["admin_unit_id"]):
        fig.add_trace(go.Choroplethmap(
            geojson=gj, locations=[selected_id], featureidkey="properties.admin_unit_id", z=[1], showscale=False,
            colorscale=[[0, "rgba(255,255,255,0)"], [1, "rgba(255,255,255,0)"]], marker=dict(opacity=1, line=dict(color="#FFFFFF", width=3)),
            name="Selected area", showlegend=False, hoverinfo="skip"))
    fig.update_layout(map=dict(style="carto-positron", zoom=zoom, center=dict(lat=30.4, lon=69.5)), height=height, clickmode="event+select")
    return map_layout(fig, height)
