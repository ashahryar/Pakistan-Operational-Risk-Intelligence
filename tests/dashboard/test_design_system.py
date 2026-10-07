"""Task 42 -- the design system: contrast of every token pair, one status language (glyph + label, never colour alone), freshness wording, KPI n/a handling."""

import re
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from dashboard.ui import components as C  # noqa: E402
from dashboard.ui import tokens  # noqa: E402
from dashboard.utils.freshness import describe  # noqa: E402

DASH = Path(__file__).resolve().parents[2] / "dashboard"
P = tokens.PALETTE


def _channel(c):
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("fg", ["text", "text_2", "muted", "primary", "info", "success", "warning", "danger", "critical", "unavailable", "insufficient", "accent"])
@pytest.mark.parametrize("bg", ["bg", "surface", "elevated"])
def test_every_text_colour_meets_wcag_aa_on_every_surface(fg, bg):
    assert contrast(P[fg], P[bg]) >= 4.5, f"{fg} on {bg}: {contrast(P[fg], P[bg]):.2f}"


@pytest.mark.parametrize("status", list(tokens.STATUS))
def test_every_status_badge_text_is_readable_on_its_tinted_fill(status):
    _, _, fill, text, _ = tokens.STATUS[status]
    blended = "#" + "".join(f"{round(int(P['surface'][i:i + 2], 16) * 0.8 + int(fill[i:i + 2], 16) * 0.2):02X}" for i in (1, 3, 5))      # fill at 20% over the surface
    assert contrast(text, blended) >= 4.5


def test_the_css_tokens_equal_the_python_tokens():
    css = (DASH / "styles" / "design_system.css").read_text(encoding="utf-8")
    pairs = {"bg": "--bg", "surface": "--surface", "elevated": "--elevated", "border": "--border", "text": "--text", "text_2": "--text-2", "muted": "--muted",
             "primary": "--primary", "accent": "--accent", "success": "--success", "warning": "--warning", "danger": "--danger"}
    for key, name in pairs.items():
        m = re.search(re.escape(name) + r":\s*(#[0-9A-Fa-f]{6})", css)
        assert m and m.group(1).lower() == P[key].lower(), name


def test_every_status_has_a_distinct_glyph_and_label_so_colour_is_never_the_only_signal():
    glyphs = [tokens.status_glyph(s) for s in tokens.STATUS]
    labels = [tokens.status_label(s) for s in tokens.STATUS]
    assert len(set(glyphs)) == len(glyphs) and len(set(labels)) == len(labels)
    assert all(tokens.status_text(s).startswith(tokens.status_glyph(s)) for s in tokens.STATUS)
    html = C.status_badge_html("INSUFFICIENT_DATA")
    assert "Insufficient data" in html and "○" in html and 'aria-hidden="true"' in html
    assert len({tokens.FRESHNESS[s][1] for s in tokens.FRESHNESS}) == len(tokens.FRESHNESS)


def test_risk_map_colours_come_from_the_single_status_palette():
    from dashboard.utils.risk_map_helpers import NO_DATA, STATUS_COLORS, STATUS_ORDER
    assert all(STATUS_COLORS[s] == tokens.status_fill(s) for s in STATUS_ORDER + [NO_DATA])


def test_freshness_wording_shows_the_real_date_and_never_a_bare_colour():
    row = {"domain": "ndma", "date_kind": "report_date", "latest_data_date": "2026-09-30", "last_ingestion_at": "2026-10-07T10:00:00", "source_state": "available"}
    assert C.freshness_text(describe(row, date(2026, 10, 1))) == "Latest available · 30 Sep 2026"
    assert C.freshness_text(describe(row, date(2026, 11, 1))).startswith("Stale · latest successful snapshot 30 Sep 2026 (32 days old)")
    pmd = {**row, "domain": "pmd_weather", "latest_data_date": "2026-08-12T00:00:16", "source_state": "unavailable"}
    assert C.freshness_text(describe(pmd, date(2026, 10, 7))) == "Source unavailable — latest successful snapshot: 12 Aug 2026"
    assert C.freshness_text(describe({**row, "latest_data_date": None}, date(2026, 10, 7))) == "No observations available"
    assert C.freshness_text(describe(None)) == "Freshness unavailable"
    assert "30 Sep 2026" in C.freshness_chip_html(describe(row, date(2026, 10, 1)))


def test_kpis_show_na_for_missing_and_a_real_zero_as_zero():
    import numpy as np
    vals = {label: shown for label, shown, _ in C.kpi_values([("a", None), ("b", 0), ("c", 199.0), ("d", np.float64(556.0)), ("e", ""), ("f", 12345)])}
    assert vals == {"a": "n/a", "b": "0", "c": "199", "d": "556", "e": "n/a", "f": "12,345"}


def test_components_escape_their_inputs():
    html = C.notice_html("info", "<script>x</script>", "<b>y</b>")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<img" not in C.provenance_html(source="<img src=x>")


def test_one_plotly_template_and_no_legacy_template_in_pages():
    import plotly.io as pio

    from dashboard.ui import charts  # noqa: F401
    assert pio.templates.default == "pori"
    for path in DASH.rglob("*.py"):
        assert 'template="plotly_dark"' not in path.read_text(encoding="utf-8"), path.name


def test_every_page_uses_the_shared_shell():
    for p in sorted((DASH / "pages").glob("*.py")) + [DASH / "Home.py"]:
        assert "shell.begin(" in p.read_text(encoding="utf-8"), f"{p.name} does not use the shared shell"


def test_navigation_groups_cover_every_page_once():
    from dashboard.ui import shell
    listed = [path for _, items in shell.NAV for _, path in items]
    actual = ["Home.py"] + [f"pages/{p.name}" for p in sorted((DASH / "pages").glob("*.py"))]
    assert sorted(listed) == sorted(actual)
    assert [g for g, _ in shell.NAV] == ["Overview", "National monitoring", "Operational intelligence", "AI & evidence"]
    assert not any("Task" in label for _, items in shell.NAV for label, _ in items)


def test_css_is_a_single_line_so_markdown_cannot_print_it_as_text():
    from dashboard.ui import shell
    css = shell.minified_css()
    assert "\n" not in css and "/*" not in css and ":focus-visible" in css and "prefers-reduced-motion" in css
