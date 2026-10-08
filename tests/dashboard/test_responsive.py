"""Task 43 -- responsive behaviour: phone detection, phone-sized charts and maps, and the responsive CSS contract (breakpoints, KPI rows, touch targets, no overflow hack)."""

import re
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")

from dashboard.ui import charts as ch  # noqa: E402
from dashboard.ui import maps, shell, viewport  # noqa: E402

DASH = Path(__file__).resolve().parents[2] / "dashboard"
CSS = (DASH / "styles" / "design_system.css").read_text(encoding="utf-8")

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
ANDROID_PHONE = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
ANDROID_TABLET = "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
IPAD = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def test_phone_detection_separates_phones_from_tablets_and_desktops():
    assert viewport.is_phone(IPHONE) and viewport.is_phone(ANDROID_PHONE)
    assert not viewport.is_phone(IPAD) and not viewport.is_phone(ANDROID_TABLET) and not viewport.is_phone(DESKTOP) and not viewport.is_phone("")


def test_no_user_agent_outside_a_session_means_not_a_phone():
    assert viewport.user_agent() == "" and viewport.is_phone() is False


def test_chart_height_is_capped_only_on_phones_and_never_below_240():
    assert viewport.chart_height(470, IPHONE) == 360 and viewport.chart_height(200, IPHONE) == 240 and viewport.chart_height(300, IPHONE) == 300
    assert viewport.chart_height(470, DESKTOP) == 470 and viewport.chart_height(470, IPAD) == 470


def test_map_size_shrinks_on_phones_only():
    assert viewport.map_size(620, 860, IPHONE) == (420, 380) and viewport.map_size(580, 1300, IPHONE) == (420, 380)
    assert viewport.map_size(620, 860, DESKTOP) == (620, 860) and viewport.map_size(300, 300, IPHONE) == (300, 300)


@pytest.fixture
def phone(monkeypatch):
    monkeypatch.setattr(viewport, "user_agent", lambda: IPHONE)


def df():
    return pd.DataFrame({"d": pd.date_range("2026-06-01", periods=40), "v": range(40)})


def test_on_a_phone_ordinary_charts_get_shorter_and_the_range_slider_is_dropped(phone):
    fig = ch.time_series(df(), "d", {"Deaths": "v"}, title="t", unit="people", source="NDMA", height=360, slider=True)
    assert fig.layout.height == 360 and fig.layout.xaxis.rangeslider.visible is False          # no +110 px slider on a phone
    assert [b["label"] for b in fig.layout.xaxis.rangeselector.buttons][-1] == "All"            # the 7d / 30d / 90d / All buttons stay
    tall = ch.style_fig(ch.go.Figure(), "t", 500)
    assert tall.layout.height == 360


def test_on_desktop_the_slider_and_height_are_unchanged():
    fig = ch.time_series(df(), "d", {"Deaths": "v"}, title="t", unit="people", source="NDMA", height=360, slider=True)
    assert fig.layout.height == 470 and fig.layout.xaxis.rangeslider.visible is True


def test_source_notes_wrap_so_a_narrow_chart_does_not_cut_them_off():
    fig = ch.style_fig(ch.go.Figure(), "t", 340, source="Source: " + "NDMA situation reports · 94 report dates between 27 Jun 2026 and 30 Sep 2026 · latest observation 30 Sep 2026")
    note = fig.layout.annotations[0].text
    assert note.count("<br>") >= 1 and all(len(line) <= 70 for line in note.split("<br>"))
    one = ch.style_fig(ch.go.Figure(), "t", 340, source="Source: PDMA")
    assert fig.layout.margin.b > one.layout.margin.b                                            # a wrapped note gets more room


def test_legend_and_range_selector_are_stacked_in_separate_rows_above_the_plot():
    fig = ch.time_series(df(), "d", {"Deaths": "v", "Injured": "v"}, title="t", unit="people", source="NDMA", height=360)
    sel_y, leg_y = fig.layout.xaxis.rangeselector.y, fig.layout.legend.y
    assert leg_y > sel_y > 0 and fig.layout.legend.x == 0                                       # legend sits above the buttons and cannot overlap them


def test_phone_map_is_shorter_and_fitted_to_the_phone_width(phone):
    poly = {"type": "Polygon", "coordinates": [[[61, 24], [77, 24], [77, 37], [61, 37], [61, 24]]]}
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "id": 1, "geometry": poly, "properties": {"admin_unit_id": 1, "admin_unit_name": "A", "province": "P",
                                                                                                                  "risk_status": "LOW", "risk_date": "2026-09-16"}}]}
    fig = maps.risk_choropleth(fc, height=620, width=860)
    assert fig.layout.height == 420 and fig.layout.map.zoom < maps.fit_view({"west": 60, "east": 78, "south": 23, "north": 38}, 860, 620)["zoom"]


# ---- the CSS contract
def test_breakpoints_cover_laptop_tablet_phone_and_narrow_phone():
    for bp in ("max-width:1100px", "max-width:820px", "max-width:768px", "max-width:480px", "max-width:359px", "pointer:coarse"):
        assert bp in CSS, bp


def test_kpi_rows_stay_two_across_on_tablets_and_phones_and_one_across_when_very_narrow():
    assert 'flex:1 1 calc(50% - 12px)!important' in CSS and "flex-direction:row!important" in CSS
    narrow = CSS[CSS.index("@media (max-width:359px)"):]
    assert "flex-basis:100%!important" in narrow


def test_non_kpi_rows_stack_below_820_px_and_legacy_row_direction_is_overridden_for_kpi_rows_only():
    stack = CSS[CSS.index("@media (max-width:820px)"):CSS.index("@media (max-width:768px)")]
    assert ":not(:has([data-testid=\"stMetric\"], .tile-value, .ob-tile-value))" in stack and "flex:1 1 100%!important" in stack


def test_touch_targets_are_44px_and_phone_text_floor_is_12px():
    block = CSS[CSS.index("@media (max-width:768px)"):CSS.index("@media (max-width:480px)")]
    assert "min-height:44px" in block and ".tile-label" in block and "font-size:12px" in block
    coarse = CSS[CSS.index("@media (pointer:coarse)"):]
    assert "min-height:44px" in coarse and "maplibregl-map" in coarse and "min-width:40px" in coarse


def test_horizontal_overflow_is_not_hidden_by_the_shared_css():
    assert "overflow-x:hidden" not in CSS.replace(" ", "")


def test_plotly_toolbar_is_hidden_on_touch_for_charts_but_kept_for_maps_and_uses_the_stable_test_id():
    assert '[data-testid="stPlotlyChart"]:not(:has(.maplibregl-map)) .modebar-container{display:none!important;}' in CSS
    assert ".js-plotly-plot" not in CSS[CSS.index("Responsive layer"):]                       # that class is not present on every Plotly mount


def test_multiselect_tags_and_legacy_kpi_values_wrap_instead_of_clipping():
    assert '[data-baseweb="tag"] span{white-space:normal' in CSS
    assert ".tile-value, .ob-tile-value{white-space:normal!important" in CSS


def test_the_stylesheet_still_minifies_to_one_balanced_line():
    css = shell.minified_css()
    assert "\n" not in css and css.count("{") == css.count("}") and re.search(r"@media \(max-width:359px\)", css)


def test_home_lets_streamlit_collapse_the_sidebar_on_phones():
    home = (DASH / "Home.py").read_text(encoding="utf-8")
    assert 'initial_sidebar_state="auto"' in home and 'initial_sidebar_state="expanded"' not in home
