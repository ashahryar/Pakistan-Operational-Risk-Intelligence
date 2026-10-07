"""Task 42 (visualization pass) -- the analytical chart builders: honest gaps, cumulative-vs-increment semantics, no autoplay, no internal ids in tooltips,
bounded animation, motion CSS limits."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("streamlit")

from dashboard.sections import impact_views, rainfall_views, weather_views  # noqa: E402
from dashboard.ui import charts as ch  # noqa: E402
from dashboard.utils.rag_helpers import evidence_rows  # noqa: E402

CSS = (Path(__file__).resolve().parents[2] / "dashboard" / "styles" / "design_system.css").read_text(encoding="utf-8")


def hovers(fig):
    out = []
    for t in fig.data:
        out.append(getattr(t, "hovertemplate", None) or " ".join(getattr(t, "hovertext", None) or []))
    for f in fig.frames:
        out += [getattr(t, "hovertemplate", "") or "" for t in f.data]
    return " ".join(str(x) for x in out)


# ---- time series
def test_range_buttons_only_offer_windows_the_history_can_fill():
    assert [b["label"] for b in ch.range_buttons(5)] == ["All"]
    assert [b["label"] for b in ch.range_buttons(20)] == ["7d", "All"]
    assert [b["label"] for b in ch.range_buttons(400)] == ["7d", "30d", "90d", "All"]


def test_time_series_keeps_gaps_and_missing_values_and_marks_the_latest_observation():
    df = pd.DataFrame({"d": pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-20"]), "v": [1.0, np.nan, 3.0]})
    fig = ch.time_series(df, "d", {"Rain": "v"}, title="t", unit="mm", source="PDMA", slider=True)
    t = fig.data[0]
    assert t.connectgaps is False and np.isnan(list(t.y)[1]) and list(t.y)[2] == 3.0         # nothing interpolated, nothing bridged
    marker = [tr for tr in fig.data if tr.name == "Latest observation"][0]
    assert marker.x[0] == pd.Timestamp("2026-06-20") and marker.y[0] == 3.0 and "latest observation 20 Jun 2026" in fig.layout.annotations[-1].text
    assert fig.layout.hovermode == "x unified" and fig.layout.xaxis.rangeslider.visible is True
    assert any("gaps are dates with no report" in (a.text or "") for a in fig.layout.annotations)       # sparse history is made visible
    assert "mm" in t.hovertemplate and "PDMA" in t.hovertemplate and "%d %b %Y" in t.hovertemplate


def test_time_series_without_data_is_none_not_an_empty_frame():
    assert ch.time_series(pd.DataFrame(columns=["d", "v"]), "d", {"x": "v"}, title="t", unit="u", source="s") is None
    assert ch.time_series(None, "d", {"x": "v"}, title="t", unit="u", source="s") is None


# ---- ranked bars / tooltips
def test_ranked_bar_names_entity_unit_date_and_source_never_an_internal_id():
    df = pd.DataFrame({"area": ["Lahore", "Multan", "Sialkot"], "n": [5.0, 9.0, 1.0], "admin_unit_id": [30, 31, 32]})
    fig = ch.ranked_bar(df, "area", "n", title="t", unit="mm", source="PDMA", as_of="14 Jul 2026", n=2)
    assert list(fig.data[0].y) == ["Lahore", "Multan"] and list(fig.data[0].x) == [5.0, 9.0]       # top 2, largest last (drawn at the top)
    h = fig.data[0].hovertemplate
    assert "mm" in h and "14 Jul 2026" in h and "PDMA" in h and "admin_unit_id" not in h
    assert ch.ranked_bar(pd.DataFrame({"area": [], "n": []}), "area", "n", title="t", unit="u", source="s") is None


# ---- animation
def frames_df(n_dates):
    dates = pd.date_range("2026-06-01", periods=n_dates, freq="D")
    return pd.DataFrame([{"d": d, "k": k, "v": float(i + j + 1)} for i, d in enumerate(dates) for j, k in enumerate(["A", "B", "C"])])


def test_animation_never_autoplays_has_play_pause_a_fixed_axis_and_real_frames():
    fig = ch.animated_bars(frames_df(10), "k", "v", "d", title="t", unit="mm", source="S", top=3)
    assert len(fig.frames) == 10 and [b.label for b in fig.layout.updatemenus[0].buttons] == ["Play", "Pause"]
    assert fig.layout.xaxis.range[0] == 0 and fig.layout.xaxis.range[1] > 11                         # axis fixed across frames: movement means change
    assert not any("autoplay" in str(x).lower() for x in (fig.layout.to_plotly_json(), ))
    assert fig.layout.sliders[0].active == 9                                                          # starts on the latest real report, paused
    assert "S" in hovers(fig) and "mm" in hovers(fig)


def test_animation_is_refused_when_it_would_be_expensive():
    assert ch.animated_bars(frames_df(ch.MAX_FRAMES + 1), "k", "v", "d", title="t", unit="u", source="s") is None
    assert ch.animated_bars(pd.DataFrame(columns=["d", "k", "v"]), "k", "v", "d", title="t", unit="u", source="s") is None


def test_missing_category_in_a_frame_has_no_bar_not_a_zero():
    df = frames_df(3)
    df = df[~((df["k"] == "B") & (df["d"] == df["d"].min()))]
    fig = ch.animated_bars(df, "k", "v", "d", title="t", unit="u", source="s", top=3)
    first = [f for f in fig.frames if f.name.startswith("01 Jun")][0]
    xs = list(first.data[0].x)
    assert any(np.isnan(x) for x in xs) and 0 not in xs


# ---- risk status views
def test_status_distribution_labels_every_bar_with_glyph_and_name():
    fig = ch.status_distribution({"INSUFFICIENT_DATA": 50, "LOW": 4, "NO_RISK_DATA": 14})
    labels = list(fig.data[0].y)
    assert labels == ["● Low", "○ Insufficient data", "· No risk record"] and list(fig.data[0].x) == [4, 50, 14]
    assert ch.status_distribution({}) is None


def test_status_timeline_is_categorical_and_makes_no_trend_claim():
    rows = [{"risk_date": "2026-09-01", "risk_status": "LOW"}, {"risk_date": "2026-09-16", "risk_status": "INSUFFICIENT_DATA"}, {"risk_date": None, "risk_status": "HIGH"}]
    fig = ch.status_timeline(rows, "Lahore")
    assert fig.data[0].mode == "markers" and len(fig.data[0].x) == 2                                 # only dated, statused rows; markers, no connecting line
    assert "Lahore" in fig.data[0].hovertemplate and "a status, not a score" in fig.layout.annotations[0].text
    assert ch.status_timeline([], "x") is None


def test_coverage_timeline_spans_first_to_latest_and_says_it_is_a_range():
    st_df = pd.DataFrame({"s": ["A", "B"], "a": ["2026-06-15", "2026-07-01"], "b": ["2026-10-07", "2026-09-01"], "r": ["RAVI", "INDUS"]})
    fig = ch.coverage_timeline(st_df, name="s", start="a", end="b", group="r", title="t", source="PDMA")
    assert {t.name for t in fig.data} == {"RAVI", "INDUS"} and "does not mean a report on every day" in fig.layout.annotations[0].text
    assert ch.coverage_timeline(pd.DataFrame(columns=["s", "a", "b", "r"]), name="s", start="a", end="b", group="r", title="t", source="x") is None


# ---- NDMA semantics
def ndma_increments():
    return pd.DataFrame({"report_date": pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-01", "2026-07-03"]),
                         "province": ["Punjab", "Punjab", "Punjab", "Sindh", "Sindh"], "deaths": [5.0, 3.0, np.nan, 2.0, 4.0]})


def test_cumulative_is_the_running_total_and_missing_stays_missing():
    long = impact_views.cumulative_long(ndma_increments(), "deaths")
    pj = long[long["province"] == "Punjab"].set_index("report_date")["cumulative"]
    assert list(pj) == [5.0, 8.0, 8.0]                                           # 5, +3, then NaN increment: the last reported total is carried, not summed again
    sd = long[long["province"] == "Sindh"].set_index("report_date")["cumulative"]
    assert sd[pd.Timestamp("2026-07-02")] == 2.0 and sd[pd.Timestamp("2026-07-03")] == 6.0       # Sindh did not report on 2 Jul: its 1 Jul total persists
    never = impact_views.cumulative_long(pd.DataFrame({"report_date": pd.to_datetime(["2026-07-01"]), "province": ["GB"], "deaths": [np.nan]}), "deaths")
    assert never["cumulative"].isna().all()                                       # a province that never reported is missing, not 0


def test_national_cumulative_sums_provinces_latest_totals_not_reports():
    nat = impact_views.national_cumulative(impact_views.cumulative_long(ndma_increments(), "deaths")).set_index("report_date")["cumulative"]
    assert list(nat) == [7.0, 10.0, 14.0]                                         # (5+2), (8+2), (8+6): never a sum of every report


def test_weekly_checkpoints_are_real_report_dates():
    long = impact_views.cumulative_long(ndma_increments(), "deaths")
    cp = impact_views.weekly_checkpoints(long)
    assert set(cp["report_date"]) <= set(long["report_date"]) and cp["report_date"].nunique() == 1


# ---- rainfall / weather
def test_rainfall_name_kinds_and_intensity_bands():
    assert rainfall_views.name_kind("Stations") == "header" and rainfall_views.name_kind("Attock, Gujranwala, Jhelum") == "list" and rainfall_views.name_kind("Lahore") == "station"
    bands = rainfall_views.intensity_counts(pd.Series([0, 0, 0.5, 3, 7, 12, 30, 80, np.nan]))
    assert dict(zip(bands["band"], bands["readings"])) == {"0 mm (reported dry)": 2, "Trace to 1 mm": 1, "1–5 mm": 1, "5–10 mm": 1, "10–25 mm": 1, "25–50 mm": 1, "50 mm and over": 1}


def test_unknown_and_null_provinces_are_both_unresolved():
    out = weather_views.normalise_province(pd.Series(["Punjab", "Unknown", None, " ", "unknown"]))
    assert list(out) == ["Punjab", "Unresolved", "Unresolved", "Unresolved", "Unresolved"]


def test_weather_snapshot_helpers():
    df = pd.DataFrame({"scraped_at": ["2026-08-12 00:00", "2026-08-12 00:00"], "day1_forecast": ["Sunny", "Sunny"]})
    assert weather_views.snapshot_date(df) == pd.Timestamp("2026-08-12") and weather_views.condition_counts(df).iloc[0].tolist() == ["Sunny", 2]


# ---- evidence cards
def test_evidence_rows_show_status_source_date_geography_relevance_and_provenance():
    e = {"chunk_id": "c1", "title": "NDMA Sitrep 12", "source": "ndma", "document_date": "2026-07-05", "geography": {}, "relevance": {"score": 0.03, "method": "hybrid_rrf", "relevance_type": "hybrid_rrf"},
         "source_reference": {"file_path": "data/parsed/a.json"}}
    rows = evidence_rows([e, {**e, "chunk_id": "c2", "document_date": None, "relevance": None, "source_reference": None}], {"c1"})
    assert rows[0] == {"Status": "Cited", "Source": "NDMA", "Document": "NDMA Sitrep 12", "Date": "2026-07-05", "Geography": "not stated",
                       "Relevance": "hybrid_rrf (score 0.03)", "Provenance": "data/parsed/a.json"}
    assert rows[1]["Status"] == "Retrieved" and rows[1]["Date"] == "undated" and rows[1]["Relevance"] == "not stated" and rows[1]["Provenance"] == "no source reference"
    assert evidence_rows([], set()) == []


# ---- the design contract
def test_motion_is_short_purposeful_and_respects_reduced_motion():
    m = re.search(r"animation:pori-rise ([0-9.]+)s", CSS)
    assert m and float(m.group(1)) <= 0.3                                                         # 150-300 ms
    assert "@keyframes pori-rise" in CSS and "infinite" not in CSS
    reduced = CSS[CSS.index("@media (prefers-reduced-motion:reduce)"):]
    assert "animation:none" in reduced and "transition:none" in reduced


def test_transition_setting_is_in_the_shared_template_and_in_every_styled_figure():
    import plotly.io as pio
    assert pio.templates["pori"].layout.transition.duration == 250
    fig = ch.style_fig(ch.go.Figure(), "t", 200)
    assert fig.layout.transition.duration == 250
    assert ch.map_layout(ch.go.Figure()).layout.uirevision == "pori-map"                          # zoom/pan survive a filter change


def test_text_font_rule_does_not_break_the_icon_font():
    assert 'stIconMaterial"]' in CSS and "Material Symbols Rounded" in CSS
    assert CSS.index("Material Symbols Rounded") > CSS.index(".stApp span, .stApp div[data-testid")      # the icon override comes after the text-font rule so it wins
