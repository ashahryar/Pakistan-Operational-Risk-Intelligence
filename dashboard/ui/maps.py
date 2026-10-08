"""dashboard/ui/maps.py

Task 42 -- the one map language: Plotly choropleth over the COD-AB boundaries, filled with the shared risk-status palette (dashboard/ui/tokens.py), each
status also named in the hover text and in the legend (never colour alone), unresolved/no-record areas drawn in the neutral "No risk record" fill,
a thicker outline on the selected area, no colour bar. A geography with no boundary is never drawn.
"""

from __future__ import annotations

import math
from typing import Optional

import plotly.graph_objects as go

from dashboard.ui import tokens, viewport
from dashboard.ui.charts import map_layout
from dashboard.utils.risk_map_helpers import NO_DATA, STATUS_ORDER, map_frame, mapped_geojson

ATTRIBUTION = ("Boundaries: COD-AB v01 (2022-09-09, CC BY-IGO), a third-party dataset that is not government-certified. "
               "Satellite imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community; place names: Esri.")

# Satellite basemap as raster tiles (no API token). Place labels are a second raster layer so districts can be located on the imagery.
SATELLITE_LAYERS = [
    dict(below="traces", sourcetype="raster", source=["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
         sourceattribution="Esri, Maxar, Earthstar Geographics"),
    dict(below="traces", sourcetype="raster", opacity=0.9, source=["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"]),
]
BOUNDARY_LINE = "#F8FAFC"        # light outlines separate the status fills from the imagery
SELECTED_LINE = "#22D3EE"        # cyan: distinct from every status colour


def _walk(coords):
    if coords and isinstance(coords[0], (int, float)):
        yield coords
    else:
        for c in coords or []:
            yield from _walk(c)


def view_bounds(gj: dict, pad: float = 0.6) -> Optional[dict]:
    """West/east/south/north of every drawn boundary (padded), so the initial view fits the data in any container size instead of using a fixed zoom."""
    xs, ys = [], []
    for f in gj.get("features", []):
        for lon, lat, *_ in _walk((f.get("geometry") or {}).get("coordinates")):
            xs.append(lon)
            ys.append(lat)
    if not xs:
        return None
    return dict(west=min(xs) - pad, east=max(xs) + pad, south=min(ys) - pad, north=max(ys) + pad)


def fit_view(b: dict, width_px: int, height_px: int, margin: float = 0.2) -> dict:
    """Centre and zoom (Web Mercator, 512 px tiles) at which `b` fills a width x height container, with a small safety margin. Plotly's own `bounds` only limits panning."""
    merc = lambda lat: math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))  # noqa: E731
    dx = max(b["east"] - b["west"], 1e-6)
    dy = max(merc(b["north"]) - merc(b["south"]), 1e-6)
    zoom = min(math.log2(width_px * 360 / (512 * dx)), math.log2(height_px * 2 * math.pi / (512 * dy))) - margin
    mid_y = (merc(b["north"]) + merc(b["south"])) / 2
    return dict(center=dict(lat=math.degrees(2 * math.atan(math.exp(mid_y)) - math.pi / 2), lon=(b["east"] + b["west"]) / 2), zoom=round(zoom, 2))


def risk_choropleth(fc: dict, *, selected_id: Optional[int] = None, height: int = 600, width: int = 1000, zoom: float = 4.3) -> Optional[go.Figure]:
    """Figure for a risk FeatureCollection, or None when no area has a boundary (the caller shows an empty state)."""
    height, width = viewport.map_size(height, width)             # a phone gets a shorter map fitted to the phone's width
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
            colorscale=[[0, tokens.status_fill(status)], [1, tokens.status_fill(status)]], marker=dict(opacity=0.62, line=dict(color=BOUNDARY_LINE, width=0.8)),
            name=f"{tokens.status_glyph(status)} {tokens.status_label(status)}", showlegend=False, hovertext=text, hoverinfo="text"))
    if selected_id is not None and selected_id in set(frame["admin_unit_id"]):
        fig.add_trace(go.Choroplethmap(
            geojson=gj, locations=[selected_id], featureidkey="properties.admin_unit_id", z=[1], showscale=False,
            colorscale=[[0, "rgba(255,255,255,0)"], [1, "rgba(255,255,255,0)"]], marker=dict(opacity=1, line=dict(color=SELECTED_LINE, width=3.5)),
            name="Selected area", showlegend=False, hoverinfo="skip"))
    bounds = view_bounds(gj)
    view = fit_view(bounds, width, height) if bounds else dict(zoom=zoom, center=dict(lat=30.4, lon=69.5))
    fig.update_layout(map=dict(style="white-bg", layers=SATELLITE_LAYERS, **view), height=height, clickmode="event+select")
    return map_layout(fig, height)
