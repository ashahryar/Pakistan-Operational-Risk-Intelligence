"""dashboard/ui/charts.py

One Plotly language for the whole dashboard (template "pori", the default) plus the analytical builders every page shares. Each builder answers ONE question,
puts date, geography, value, unit and source in the tooltip (never an internal id), and never draws a value that was not observed:

  time_series       -- "how did X change, and how complete is the history?": real date axis, 7d/30d/90d/All selectors (only windows the data can fill), a range
                       slider on request, unified hover, the latest observation marked, gaps left as gaps (lines are never joined across missing dates).
  ranked_bar        -- "which areas are highest right now?"
  animated_bars     -- "how did the picture build up report by report?": a play/pause slider that starts paused; refused (None) when it would be expensive.
  status_distribution / status_timeline / coverage_timeline -- risk status counts, one area's status history, and which stations reported over which dates.

Motion: filters re-render through Plotly with a 250 ms transition setting and a stable axis/legend structure; animation only ever runs when the user presses Play
(no autoplay), which also respects reduced-motion preferences.
"""

from __future__ import annotations

import textwrap
from typing import Optional, Sequence

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from dashboard.ui import tokens, viewport

P = tokens.PALETTE
SERIES = ["#60A5FA", "#F59E0B", "#34D399", "#C084FC", "#F472B6", "#94A3B8"]      # categorical, colour-blind-safe; never used to mean risk
MAX_FRAMES = 60                                                                # animations with more frames than this are not built
TRANSITION = dict(duration=250, easing="cubic-in-out")

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
    transition=TRANSITION,
)
pio.templates["pori"] = go.layout.Template(layout=_layout)
pio.templates.default = "pori"


def _wrap(text: str, width: int = 62) -> tuple[str, int]:
    """Source notes wrap onto several lines (a long single line is cut off on a narrow chart). -> (text with <br>, line count)"""
    lines = textwrap.wrap(text, width) or [""]
    return "<br>".join(lines), len(lines)


def style_fig(fig: go.Figure, title: str | None = None, height: int = 340, *, xtitle: str | None = None, ytitle: str | None = None, source: str | None = None,
              slider: bool = False, bottom: Optional[int] = None) -> go.Figure:
    """Apply the standard layout. `source` is written under the chart as a wrapped source note. On a phone an ordinary chart is capped in height."""
    if not slider:
        height = viewport.chart_height(height)
    fig.update_layout(template="pori", height=height, transition=TRANSITION, **({"title": dict(text=title)} if title else {}))
    if xtitle is not None:
        fig.update_xaxes(title_text=xtitle)
    if ytitle is not None:
        fig.update_yaxes(title_text=ytitle)
    if source:
        note, lines = _wrap(source)
        bottom = (bottom or (120 if slider else 78)) + 14 * (lines - 1)   # room for the x-axis title, the optional range slider and the (wrapped) source note
        m = fig.layout.margin
        top = m.t if m.t is not None else 44
        b = max(m.b or 0, bottom)
        fig.update_layout(margin=dict(l=m.l if m.l is not None else 8, r=m.r if m.r is not None else 8, t=top, b=b))
        plot_h = max(height - top - b, 1)
        fig.add_annotation(text=note, xref="paper", yref="paper", x=0, y=-(b - 30) / plot_h, showarrow=False, align="left",
                           font=dict(size=11, color=P["muted"]), xanchor="left", yanchor="top")
    return fig


def stack_top(fig: go.Figure, *, selector: bool = True, legend: bool = True) -> go.Figure:
    """Lay the range selector and the legend out as two rows above the plot (selector nearest the plot, legend above it) in paper coordinates computed from the final
    margins, so on a narrow chart a wrapping legend can never sit on the buttons or the title."""
    H, t, b = fig.layout.height or 340, fig.layout.margin.t or 44, fig.layout.margin.b or 8
    plot_h = max(H - t - b, 1)
    sel_h = 34 if selector else 0
    if selector:
        fig.update_xaxes(rangeselector=dict(x=0, xanchor="left", y=6 / plot_h, yanchor="bottom"))
    if legend:
        fig.update_layout(legend=dict(orientation="h", x=0, xanchor="left", y=(6 + sel_h + 6) / plot_h, yanchor="bottom"))
    return fig


def map_layout(fig: go.Figure, height: int = 600) -> go.Figure:
    """The one map language: satellite basemap (see dashboard/ui/maps.py), light boundaries, no colour bar (a labelled legend is rendered as HTML)."""
    fig.update_layout(template="pori", height=height, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, uirevision="pori-map")      # uirevision keeps zoom/pan across filter changes
    return fig


def _span_days(dates: pd.Series) -> int:
    d = pd.to_datetime(dates).dropna()
    return int((d.max() - d.min()).days) if len(d) else 0


def range_buttons(span_days: int) -> list[dict]:
    """7d / 30d / 90d / All -- only windows the history can actually fill (a 30-day button over 12 days of data would be a lie about coverage)."""
    buttons = [dict(count=n, label=f"{n}d", step="day", stepmode="backward") for n in (7, 30, 90) if span_days > n]
    return buttons + [dict(step="all", label="All")]


def time_series(df: pd.DataFrame, x: str, series: dict[str, str], *, title: str, unit: str, source: str, height: int = 360, slider: bool = False,
                geography: Optional[str] = None, mode: str = "lines+markers", fill: bool = False) -> Optional[go.Figure]:
    """Interactive time series, or None when there is nothing to draw. `series` maps a label to a column. Missing values stay missing: no gap is bridged."""
    if df is None or df.empty or x not in df:
        return None
    slider = slider and not viewport.is_phone()
    d = df.dropna(subset=[x]).sort_values(x)
    if d.empty:
        return None
    d[x] = pd.to_datetime(d[x])
    fig = go.Figure()
    for i, (label, col) in enumerate(series.items()):
        if col not in d:
            continue
        colour = SERIES[i % len(SERIES)]
        fig.add_trace(go.Scatter(
            x=d[x], y=d[col], name=label, mode=mode, connectgaps=False, line=dict(color=colour, width=2, shape="linear"), marker=dict(size=5),
            fill="tozeroy" if fill and i == 0 else None, fillcolor="rgba(96,165,250,0.12)" if fill and i == 0 else None,
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>%{{y:,.1f}} {unit}" + (f"<br>{geography}" if geography else "") + f"<br><i>{source}</i><extra></extra>"))
    first_col = next((c for c in series.values() if c in d), None)
    last = d.dropna(subset=[first_col]).tail(1) if first_col else d.iloc[0:0]
    latest_text = ""
    if not last.empty:
        lx, ly = last[x].iloc[0], last[first_col].iloc[0]
        latest_text = f" · latest observation {lx:%d %b %Y}"
        fig.add_vline(x=lx, line=dict(color=P["muted"], width=1, dash="dot"))
        fig.add_trace(go.Scatter(x=[lx], y=[ly], mode="markers", name="Latest observation", marker=dict(size=11, symbol="diamond", color=P["accent"], line=dict(color=P["bg"], width=1)),
                                 hovertemplate=f"<b>Latest observation</b><br>{lx:%d %b %Y}<br>{ly:,.1f} {unit}<br><i>{source}</i><extra></extra>"))
    span = _span_days(d[x])
    fig.update_xaxes(type="date", tickformat="%d %b", nticks=6, rangeselector=dict(buttons=range_buttons(span), bgcolor=P["elevated"], activecolor=P["primary"], font=dict(color=P["text"], size=12)),
                     rangeslider=dict(visible=slider, thickness=0.06, bgcolor=P["surface"]))
    fig.update_layout(hovermode="x unified", yaxis_title=unit, margin=dict(l=8, r=16, t=128, b=8))
    out = style_fig(fig, title, height + (110 if slider else 0), source=f"Source: {source} · {d[x].nunique()} report dates between {d[x].min():%d %b %Y} and {d[x].max():%d %b %Y}{latest_text}"
                     + (" · gaps are dates with no report" if span > d[x].nunique() * 1.5 else ""), slider=slider)
    return stack_top(out)


def ranked_bar(df: pd.DataFrame, label: str, value: str, *, title: str, unit: str, source: str, n: int = 15, height: Optional[int] = None,
               highlight: Optional[str] = None, as_of: Optional[str] = None) -> Optional[go.Figure]:
    """Horizontal ranked bars of the top `n` rows. The tooltip names the entity, the value with its unit, the date and the source."""
    if df is None or df.empty or label not in df or value not in df:
        return None
    d = df.dropna(subset=[value]).sort_values(value, ascending=False).head(n).iloc[::-1]
    if d.empty:
        return None
    colours = [P["accent"] if (highlight and r == highlight) else P["primary"] for r in d[label]]
    fig = go.Figure(go.Bar(x=d[value], y=d[label], orientation="h", marker_color=colours, text=[f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}" for v in d[value]],
                           textposition="outside", cliponaxis=False,
                           hovertemplate="<b>%{y}</b><br>%{x:,.1f} " + unit + (f"<br>as of {as_of}" if as_of else "") + f"<br><i>{source}</i><extra></extra>"))
    fig.update_layout(margin=dict(l=8, r=40, t=44, b=8), showlegend=False)
    return style_fig(fig, title, height or max(220, 28 * len(d) + 90), xtitle=unit, ytitle="", source=f"Source: {source}" + (f" · as of {as_of}" if as_of else ""))


def animated_bars(df: pd.DataFrame, category: str, value: str, frame: str, *, title: str, unit: str, source: str, top: int = 10, height: int = 400,
                  frame_label: str = "%d %b %Y", max_frames: int = MAX_FRAMES) -> Optional[go.Figure]:
    """Bars per category that step through `frame` values (dates) with a play/pause button and a slider; it never autoplays and the value axis is fixed so
    movement means change. Returns None when there are no frames or more than `max_frames` (the caller then keeps the static chart)."""
    if df is None or df.empty or any(c not in df for c in (category, value, frame)):
        return None
    d = df.dropna(subset=[value]).copy()
    d[frame] = pd.to_datetime(d[frame])
    frames = sorted(d[frame].unique())
    if not frames or len(frames) > max_frames:
        return None
    cats = list(d.groupby(category)[value].max().sort_values(ascending=False).head(top).index)[::-1]
    vmax = float(d[value].max()) * 1.12 or 1.0
    by = {f: d[d[frame] == f].set_index(category)[value] for f in frames}

    def bar(f):
        s = by[f].reindex(cats)
        return go.Bar(x=s.values, y=cats, orientation="h", marker_color=P["primary"], customdata=[f"{pd.Timestamp(f):{frame_label}}"] * len(cats),
                      hovertemplate="<b>%{y}</b><br>%{x:,.1f} " + unit + "<br>%{customdata}" + f"<br><i>{source}</i><extra></extra>")

    fig = go.Figure(data=[bar(frames[-1])], frames=[go.Frame(data=[bar(f)], name=f"{pd.Timestamp(f):{frame_label}}") for f in frames])
    steps = [dict(method="animate", label=f"{pd.Timestamp(f):%d %b}", args=[[f"{pd.Timestamp(f):{frame_label}}"], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                                                                                                      transition=dict(duration=250))]) for f in frames]
    plot_h = max(height + 60 - 70 - 170, 1)
    ctrl_y = -78 / plot_h                                                # controls sit below the axis title, above the source note
    fig.update_layout(
        xaxis=dict(range=[0, vmax], title=unit), yaxis=dict(title=""), showlegend=False,
        updatemenus=[dict(type="buttons", direction="left", x=0, y=ctrl_y, xanchor="left", yanchor="top", active=-1, bgcolor=P["elevated"], bordercolor=P["border"],
                          font=dict(color=P["text"], size=12), pad=dict(l=2, r=2, t=2, b=2),
                          buttons=[dict(label="Play", method="animate", args=[None, dict(frame=dict(duration=450, redraw=True), transition=dict(duration=250), fromcurrent=True)]),
                                   dict(label="Pause", method="animate", args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False), transition=dict(duration=0))])])],
        sliders=[dict(active=len(frames) - 1, steps=steps, x=0.18, len=0.8, y=ctrl_y, yanchor="top", currentvalue=dict(prefix="Report date: ", font=dict(color=P["text_2"], size=12), xanchor="left"),
                      bgcolor=P["surface"], bordercolor=P["border"], activebgcolor=P["primary"], tickcolor=P["muted"], font=dict(color=P["muted"], size=10), ticklen=3)])
    sub = f"Source: {source} · {len(frames)} report dates · axis fixed at 0–{vmax:,.0f} {unit} · press Play to step through"
    fig = style_fig(fig, f"{title}<br><sup style='color:{P['muted']}'>{sub}</sup>", height + 60, slider=True, bottom=170)     # the source sits in the subtitle: nothing collides with the slider
    fig.update_layout(margin=dict(l=8, r=8, t=70, b=170))
    return fig


def heatmap(z: pd.DataFrame, *, title: str, unit: str, source: str, height: Optional[int] = None, xlabel: str = "", ylabel: str = "", zmin: Optional[float] = None,
            fmt: str = ",.0f") -> Optional[go.Figure]:
    """Matrix of intensity (rows x columns). Missing cells stay empty (grey), never 0. One sequential blue scale: intensity, not risk."""
    if z is None or z.empty:
        return None
    zz = z.astype(float)
    xs = [str(c)[:10] if not isinstance(c, str) else c for c in zz.columns]
    fig = go.Figure(go.Heatmap(z=zz.values, x=xs, y=[str(i) for i in zz.index], colorscale=[[0, "#13213A"], [0.35, "#1D4ED8"], [0.7, "#60A5FA"], [1, "#E0F2FE"]], zmin=zmin,
                               xgap=1, ygap=1, hoverongaps=False, colorbar=dict(title=dict(text=unit, font=dict(size=11)), thickness=10, tickfont=dict(size=11)),
                               hovertemplate="<b>%{y}</b><br>%{x}<br>%{z:" + fmt + "} " + unit + "<br><i>" + source + "</i><extra></extra>"))
    fig.update_xaxes(title_text=xlabel, side="bottom", showgrid=False)
    fig.update_yaxes(title_text=ylabel, autorange="reversed", showgrid=False)
    return style_fig(fig, title, height or max(260, 26 * len(zz.index) + 140), source=f"Source: {source} · empty cells = no value reported (not zero)")


def status_by_group(df: pd.DataFrame, group: str, status: str, *, title: str, source: str = "PORI risk engine (provisional thresholds)", height: Optional[int] = None) -> Optional[go.Figure]:
    """Stacked horizontal bars: for each group (e.g. province) how many areas fall in each operational status. Colours and glyph labels come from the shared status palette."""
    if df is None or df.empty or group not in df or status not in df:
        return None
    t = df.groupby([group, status]).size().unstack(fill_value=0)
    order = [s for s in ("CRITICAL", "HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA", "NO_SIGNAL", "NO_RISK_DATA") if s in t.columns]
    if not order:
        return None
    t = t[order].loc[t[order].sum(axis=1).sort_values().index]
    fig = go.Figure([go.Bar(y=t.index, x=t[s], name=tokens.status_text(s), orientation="h", marker_color=tokens.status_fill(s),
                            hovertemplate="<b>%{y}</b><br>" + tokens.status_text(s) + ": %{x} areas<br><i>" + source + "</i><extra></extra>") for s in order])
    fig.update_layout(barmode="stack", legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), margin=dict(l=8, r=16, t=112, b=8))
    return style_fig(fig, title, height or max(240, 30 * len(t) + 150), xtitle="Areas", ytitle="", source=f"Source: {source}")


def status_distribution(counts: dict[str, int], *, title: str = "Areas by operational status", source: str = "PORI risk engine (provisional thresholds)",
                        height: int = 260) -> Optional[go.Figure]:
    """Counts per status, ordered critical -> no risk record, labelled with glyph + name (colour is never the only signal)."""
    order = [s for s in ("CRITICAL", "HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA", "NO_SIGNAL", "NO_RISK_DATA") if counts.get(s)]
    if not order:
        return None
    labels = [tokens.status_text(s) for s in order]
    fig = go.Figure(go.Bar(x=[counts[s] for s in order], y=labels, orientation="h", marker_color=[tokens.status_fill(s) for s in order],
                           text=[counts[s] for s in order], textposition="outside", cliponaxis=False,
                           hovertemplate="<b>%{y}</b><br>%{x} areas<br><i>" + source + "</i><extra></extra>"))
    fig.update_layout(yaxis=dict(autorange="reversed"), showlegend=False, margin=dict(l=8, r=36, t=44, b=8))
    return style_fig(fig, title, height, xtitle="Areas", ytitle="", source=f"Source: {source}")


def status_timeline(rows: Sequence[dict], area: str, *, height: int = 240) -> Optional[go.Figure]:
    """One area's operational status over the dates the engine produced a row for. Statuses are categories, not a score; no line implies a trend between dates."""
    pts = [(r["risk_date"], r["risk_status"]) for r in rows or [] if r.get("risk_date") and r.get("risk_status")]
    if not pts:
        return None
    df = pd.DataFrame(pts, columns=["date", "status"]).drop_duplicates().sort_values("date")
    df["date"] = pd.to_datetime(df["date"])
    levels = [s for s in ("CRITICAL", "HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA", "NO_SIGNAL") if s in set(df["status"])]
    df["label"] = df["status"].map(tokens.status_text)
    fig = go.Figure(go.Scatter(x=df["date"], y=df["label"], mode="markers", marker=dict(size=11, symbol="square", color=[tokens.status_fill(s) for s in df["status"]],
                                                                                       line=dict(color=P["text_2"], width=1)),
                               hovertemplate=f"<b>{area}</b><br>%{{x|%d %b %Y}}<br>%{{y}}<br><i>PORI risk engine (provisional)</i><extra></extra>"))
    fig.update_yaxes(categoryorder="array", categoryarray=[tokens.status_text(s) for s in levels][::-1])
    fig.update_xaxes(type="date", tickformat="%d %b", rangeselector=dict(buttons=range_buttons(_span_days(df["date"])), bgcolor=P["elevated"], activecolor=P["primary"],
                                                                         font=dict(color=P["text"], size=12)))
    if _span_days(df["date"]) <= 14:
        fig.update_xaxes(dtick="D1", tickformat="%d %b")                # a short history gets one tick per day, never repeated day labels
    return style_fig(fig, f"{area}: status by risk date", height, source=f"Source: PORI risk engine · {df['date'].nunique()} dated record(s) · a status, not a score")


def coverage_timeline(stations: pd.DataFrame, *, name: str, start: str, end: str, group: str, title: str, source: str, height: Optional[int] = None) -> Optional[go.Figure]:
    """Which stations reported over which date range (first -> latest observation). A range, not proof of daily continuity: the caption says so."""
    if stations is None or stations.empty or any(c not in stations for c in (name, start, end, group)):
        return None
    d = stations.dropna(subset=[start, end]).copy()
    if d.empty:
        return None
    d[start], d[end] = pd.to_datetime(d[start]), pd.to_datetime(d[end])
    d = d.sort_values([group, name])
    fig = go.Figure()
    for i, g in enumerate(dict.fromkeys(d[group])):
        part = d[d[group] == g]
        fig.add_trace(go.Bar(base=part[start], x=(part[end] - part[start]).dt.total_seconds() * 1000 + 86_400_000, y=part[name], orientation="h", name=g,
                             marker_color=SERIES[i % len(SERIES)], customdata=list(zip(part[start].dt.strftime("%d %b %Y"), part[end].dt.strftime("%d %b %Y"))),
                             hovertemplate="<b>%{y}</b><br>" + g + "<br>first %{customdata[0]} → latest %{customdata[1]}<br><i>" + source + "</i><extra></extra>"))
    fig.update_xaxes(type="date", tickformat="%d %b")
    fig.update_layout(barmode="overlay", yaxis=dict(autorange="reversed"), margin=dict(l=8, r=16, t=128, b=8),
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, xanchor="left"))
    return style_fig(fig, title, height or max(300, 18 * len(d) + 110), source=f"Source: {source} · each bar spans first to latest observation; it does not mean a report on every day")
