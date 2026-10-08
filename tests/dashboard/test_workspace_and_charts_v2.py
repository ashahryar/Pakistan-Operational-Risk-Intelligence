"""Task 42 (third pass) -- deterministic Workspace summaries, fit-to-data map bounds, heatmaps, status-by-province, emoji-free legacy pages."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("streamlit")

from dashboard.sections import impact_views, rainfall_views  # noqa: E402
from dashboard.ui import charts as ch  # noqa: E402
from dashboard.ui import maps  # noqa: E402
from dashboard.utils import summary_helpers as S  # noqa: E402

DASH = Path(__file__).resolve().parents[2] / "dashboard"


def agent_body(**kw):
    rec = {"admin_unit_name": "Lahore", "risk_status": "LOW", "risk_date": "2026-09-15", "observed_signal_count": 1, "missing_signal_count": 5, "data_coverage_pct": 16.67,
           "risk_score": None, "signals": {"rainfall": None, "air_quality": 0.17, "gauge": None}}
    return {"risk_context": {"status": "AVAILABLE", "record": rec}, "geography": {"unit": {"name": "Lahore"}}, "documentary_evidence": [], "retrieval": None, **kw}


def test_summary_states_only_what_the_api_returned_and_never_a_score():
    text = " ".join(S.operational_summary(agent_body()))
    assert "Lahore" in text and "Low" in text and "2026-09-15" in text and "not a probability" in text
    assert "1 of 6 signal groups" in text and "16.67%" in text
    assert "Observed: air quality" in text and "Not observed: rainfall, gauge" in text
    assert "Numeric risk score: not computed" in text and "risk engine reports" not in text


def test_summary_reports_missing_context_forecast_and_withheld_documents_plainly():
    b = agent_body(risk_context={"status": "NO_RISK_CONTEXT", "reason": "no area resolved"}, components={"ml": {"status": "INSUFFICIENT_DATA", "reason": "0 observed days; at least 180 needed"}},
                   retrieval={"relevance": {"low_relevance_count": 15}})
    lines = S.operational_summary(b)
    assert any("No risk record could be retrieved" in x and "no area resolved" in x for x in lines)
    assert any(x.startswith("No forecast: 0 observed days") for x in lines)
    assert any("No document passage passed the relevance check" in x and "15 loosely matching" in x for x in lines)
    assert S.operational_summary({}) == []


def test_summary_lists_documents_that_passed_the_relevance_check():
    docs = [{"title": "NDMA Sitrep 12", "document_date": "2026-07-05"}, {"title": "PDMA Daily", "document_date": None}]
    line = S.operational_summary(agent_body(documentary_evidence=docs))[-1]
    assert line.startswith("2 document passage(s) passed the relevance check") and "NDMA Sitrep 12 (2026-07-05)" in line and "PDMA Daily (an unstated date)" in line


def test_extractive_passages_are_verbatim_truncated_and_in_the_apis_order():
    ev = [{"title": "A", "source": "ndma", "document_date": "2026-07-05", "snippet": "x" * 400}, {"title": "B", "source": "pdma", "document_date": None, "snippet": "short\ntext"}]
    p = S.extractive_passages(ev, n=2, chars=100)
    assert [x["title"] for x in p] == ["A", "B"] and p[0]["excerpt"] == "x" * 100 + "…" and p[1]["excerpt"] == "short text" and p[1]["date"] == "undated" and p[0]["source"] == "NDMA"
    assert S.extractive_passages([], 3) == [] and "> short text" in S.passage_markdown(p[1])


def test_enable_hint_names_the_real_settings_and_examples_exist():
    assert all(k in S.ENABLE_HINT for k in ("PORI_LLM_PROVIDER", "PORI_LLM_MODEL", "PORI_LLM_API_KEY")) and "authoritative" in S.ENABLE_HINT
    assert len(S.EXAMPLES) >= 3 and S.example_line().startswith("Examples to try:")


# ---- map fits its data
def test_map_bounds_fit_the_drawn_boundaries_not_a_fixed_zoom():
    poly = lambda x0, y0: {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]]}  # noqa: E731
    gj = {"features": [{"geometry": poly(66, 24)}, {"geometry": {"type": "MultiPolygon", "coordinates": [poly(74, 36)["coordinates"]]}}, {"geometry": None}]}
    b = maps.view_bounds(gj, pad=0.5)
    assert b == {"west": 65.5, "east": 75.5, "south": 23.5, "north": 37.5} and maps.view_bounds({"features": []}) is None
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "id": 1, "geometry": poly(70, 30), "properties": {"admin_unit_id": 1, "admin_unit_name": "L", "province": "P",
                                                                                                                        "risk_status": "LOW", "risk_date": "2026-09-16"}}]}
    fig = maps.risk_choropleth(fc, width=1300, height=460)
    assert abs(fig.layout.map.center.lon - 70.5) < 0.01 and 2 < fig.layout.map.zoom < 12


# ---- advanced charts
def test_heatmap_leaves_missing_cells_empty_and_labels_intensity_not_risk():
    z = pd.DataFrame({"w1": [1.0, np.nan], "w2": [5.0, 2.0]}, index=["KP", "Sindh"])
    fig = ch.heatmap(z, title="t", unit="people", source="NDMA")
    assert np.isnan(fig.data[0].z[1][0]) and fig.data[0].z[0][1] == 5.0 and fig.data[0].hoverongaps is False
    assert "people" in fig.data[0].hovertemplate and "NDMA" in fig.data[0].hovertemplate and "not zero" in " ".join(fig.layout.annotations[0].text.replace("<br>"," ").split())
    assert ch.heatmap(pd.DataFrame(), title="t", unit="u", source="s") is None


def test_weekly_increment_matrix_sums_what_a_weeks_reports_added_and_keeps_empty_weeks_empty():
    df = pd.DataFrame({"report_date": pd.to_datetime(["2026-06-29", "2026-07-01", "2026-07-14"]), "province": ["KP", "KP", "Sindh"], "deaths": [2.0, 3.0, 4.0]})
    m = impact_views.weekly_increment_matrix(df, "deaths")
    assert m.loc["KP", "29 Jun"] == 5.0 and m.loc["Sindh", "13 Jul"] == 4.0 and np.isnan(m.loc["Sindh", "29 Jun"]) and np.isnan(m.loc["KP", "13 Jul"])
    assert list(m.index)[0] == "KP"


def test_station_month_matrix_uses_the_highest_reading_and_keeps_missing_months_empty():
    d = pd.DataFrame({"report_date": pd.to_datetime(["2026-06-01", "2026-06-20", "2026-08-02"]), "station": ["Lahore", "Lahore", "Lahore"], "rainfall_mm": [4.0, 9.0, 1.0]})
    m = rainfall_views.station_month_matrix(d)
    assert m.loc["Lahore", "Jun 2026"] == 9.0 and np.isnan(m.loc["Lahore", "Jul 2026"]) and m.loc["Lahore", "Aug 2026"] == 1.0


def test_status_by_group_stacks_statuses_with_the_shared_palette_and_labels():
    from dashboard.ui import tokens
    df = pd.DataFrame({"province": ["Punjab"] * 3 + ["Sindh"], "status": ["LOW", "LOW", "INSUFFICIENT_DATA", "NO_RISK_DATA"]})
    fig = ch.status_by_group(df, "province", "status", title="t")
    names = [t.name for t in fig.data]
    assert names == [tokens.status_text("LOW"), tokens.status_text("INSUFFICIENT_DATA"), tokens.status_text("NO_RISK_DATA")]
    assert fig.data[0].marker.color == tokens.status_fill("LOW") and fig.layout.barmode == "stack"
    assert ch.status_by_group(pd.DataFrame(columns=["province", "status"]), "province", "status", title="t") is None


def test_animation_controls_use_dark_styling_and_the_slider_has_room():
    fig = ch.animated_bars(pd.DataFrame([{"d": pd.Timestamp("2026-06-0%d" % i), "k": "A", "v": float(i)} for i in range(1, 5)]), "k", "v", "d", title="t", unit="u", source="s")
    um = fig.layout.updatemenus[0]
    assert um.bgcolor == ch.P["elevated"] and um.active == -1 and fig.layout.margin.b >= 150 and fig.layout.sliders[0].activebgcolor == ch.P["primary"]


# ---- legacy pages are emoji-free (status glyphs are text symbols from the design system)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF☀-⛿✅❌✨]")


@pytest.mark.parametrize("rel", ["pages/1_NDMA_Casualties.py", "pages/2_NDMA_Damage.py", "pages/3_PMD_Weather.py", "pages/4_PDMA_Rainfall.py", "charts/disaster_charts.py",
                                 "sections/geo_intelligence.py", "components/alerts.py"])
def test_legacy_pages_carry_no_emoji_outside_the_browser_tab_icon(rel):
    for n, line in enumerate((DASH / rel).read_text(encoding="utf-8").split("\n"), 1):
        if "page_icon" in line:
            continue
        assert not EMOJI.search(line), f"{rel}:{n} still has an emoji: {line.strip()[:80]}"


def test_fit_view_shows_the_whole_extent_in_wide_and_narrow_containers():
    pak = {"west": 60.5, "east": 77.5, "south": 23.0, "north": 37.5}
    wide, narrow = maps.fit_view(pak, 1300, 460), maps.fit_view(pak, 700, 620)
    assert wide["zoom"] < 6 and narrow["zoom"] < wide["zoom"] + 1                                     # a short wide container is height-limited, a narrow one width-limited
    for v in (wide, narrow):
        assert 28 < v["center"]["lat"] < 32 and abs(v["center"]["lon"] - 69.0) < 0.01
    # at that zoom the data's extent fits the container (Mercator, 512 px tiles)
    import math
    merc = lambda lat: math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))  # noqa: E731
    for (w, h), v in (((1300, 460), wide), ((700, 620), narrow)):
        world = 512 * 2 ** v["zoom"]
        assert world * (pak["east"] - pak["west"]) / 360 <= w and world * (merc(pak["north"]) - merc(pak["south"])) / (2 * math.pi) <= h
