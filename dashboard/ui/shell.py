"""dashboard/ui/shell.py

Task 42 -- the application shell shared by every page: theme injection, the grouped sidebar navigation, the application bar (identity and an honest data
freshness summary) and the page header with the domain's freshness chips.

Usage in a page, right after st.set_page_config():
    shell.begin("PMD Weather", "Forecast snapshots published by the Pakistan Meteorological Department.", domain="pmd_weather")
    ... page content ...
    shell.finish()          # legacy pages that inject their own CSS: re-assert the shared tokens last
"""

from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path
from typing import Optional

import streamlit as st

from dashboard.ui import charts as _charts  # noqa: F401  (registers the "pori" Plotly template as the default)
from dashboard.ui import components as C
from dashboard.ui import tokens
from dashboard.utils.api_cache import render_refresh_control
from dashboard.utils.freshness import describe, freshness_rows

_CSS = Path(__file__).resolve().parents[1] / "styles" / "design_system.css"

# (group, [(label, page file relative to the entry script)])
NAV = [
    ("Overview", [("Executive Overview", "Home.py")]),
    ("National monitoring", [("NDMA Casualties", "pages/1_NDMA_Casualties.py"), ("NDMA Damage", "pages/2_NDMA_Damage.py"),
                             ("PMD Weather", "pages/3_PMD_Weather.py"), ("PDMA Rainfall", "pages/4_PDMA_Rainfall.py"),
                             ("River & Gauge Network", "pages/5_PDMA_Rivers.py")]),
    ("Operational intelligence", [("Risk Map", "pages/6_Risk_Map.py")]),
    ("AI & evidence", [("Intelligence Workspace", "pages/7_Operational_Intelligence.py")]),
]


def minified_css() -> str:
    """The stylesheet on ONE line: a blank line inside <style> would end Streamlit's HTML block and print the rest as text."""
    css = re.sub(r"/\*.*?\*/", "", _CSS.read_text(encoding="utf-8"), flags=re.S)
    return " ".join(line.strip() for line in css.splitlines() if line.strip())


def inject_css() -> None:
    st.markdown(f'<link href="{tokens.FONT_URL}" rel="stylesheet"><style>{minified_css()}</style>', unsafe_allow_html=True)


def summary_counts(rows: dict) -> dict:
    """{state: count} over the freshness domains the API returned (the risk domain included). Pure given `rows`."""
    counts: dict = {}
    for row in rows.values():
        counts[describe(row)["state"]] = counts.get(describe(row)["state"], 0) + 1
    return counts


def summary_text(counts: dict) -> str:
    if not counts:
        return "Freshness unavailable (the API did not answer)"
    parts = [f"{counts[s]} {label}" for s, label in (("current", "current"), ("stale", "stale"), ("source_unavailable", "source unavailable"), ("no_data", "no data"))
             if counts.get(s)]
    return " · ".join(parts) or "Freshness unavailable"


def sidebar(rows: dict) -> None:
    with st.sidebar:
        st.markdown('<div class="pori-brand"><div class="pori-brand-mark" aria-hidden="true">PK</div><div><div class="pori-brand-name">PORI</div>'
                    '<div class="pori-brand-sub">Operational Risk Intelligence</div></div></div>', unsafe_allow_html=True)
        for group, items in NAV:
            st.markdown(f'<div class="pori-nav-group">{escape(group)}</div>', unsafe_allow_html=True)
            for label, path in items:
                try:
                    st.page_link(path, label=label)
                except Exception:           # a single page run outside the multipage entry point (tests): the link target is unknown
                    st.markdown(f"<div style='padding:6px 12px;color:var(--text-2)'>{escape(label)}</div>", unsafe_allow_html=True)
        render_refresh_control()
        st.markdown(f'<div class="pori-side-fresh"><b>Data freshness</b><br>{escape(summary_text(summary_counts(rows)))}</div>', unsafe_allow_html=True)


def appbar(rows: dict) -> None:
    env = os.getenv("PORI_ENV")
    env_html = f'<span class="pori-chip"><span class="g" aria-hidden="true">▣</span>{escape(env)}</span>' if env else ""
    counts = summary_counts(rows)
    state = "current" if counts and set(counts) == {"current"} else ("unknown" if not counts else "stale")
    chip = f'<span class="pori-chip"><span class="g" aria-hidden="true">{tokens.FRESHNESS[state][1]}</span><span>{escape(summary_text(counts))}</span></span>'
    st.markdown(
        f'<div class="pori-appbar"><div><div class="t"><b>Pakistan Operational Risk Intelligence</b></div>'
        f'<div class="d">Published NDMA, PDMA and PMD bulletins, placed on one administrative geography, with the evidence behind every status. Decision support only.</div></div>'
        f'<div class="pori-chips" style="margin:0">{env_html}{chip}</div></div>', unsafe_allow_html=True)


def page_header(title: str, subtitle: str, domain: Optional[str], rows: dict) -> None:
    st.markdown(f'<h1 class="pori-page-title">{escape(title)}</h1><p class="pori-page-sub">{escape(subtitle)}</p>', unsafe_allow_html=True)
    if not domain:
        return
    d = describe(rows.get(domain))
    chips = [C.freshness_chip_html(d)]
    if d["last_ingestion"]:
        chips.append(f'<span class="pori-chip">Last successful ingestion <span class="v">{escape(C._fmt_date(d["last_ingestion"]))}</span></span>')
    if d["source_status"]:
        glyph, colour = ("●", tokens.PALETTE["success"]) if d["source_status"] == "available" else ("✕", tokens.PALETTE["danger"])
        chips.append(f'<span class="pori-chip"><span class="g" style="color:{colour}" aria-hidden="true">{glyph}</span>Source {escape(d["source_status"])}</span>')
    st.markdown(f'<div class="pori-chips">{"".join(chips)}</div>', unsafe_allow_html=True)
    if d["state"] == "source_unavailable":
        C.notice("unavail", "Source unavailable", f"{d['note'] or 'Ingestion is disabled or the last run failed.'} Figures below are the last successful snapshot, not current conditions.")
    elif d["state"] == "stale":
        C.notice("warn", "Data is stale", f"{d['note'] or 'No newer data has been ingested.'}")
    elif d["state"] == "no_data":
        C.empty_state("No observations available", d["note"] or "This domain has no ingested rows.")
    elif d["note"]:
        C.notice("info", "Source note", d["note"])


def note(text: str) -> None:
    """The page's source and method note, in the shared notice style."""
    C.notice("info", "Source and method", text.removeprefix("Source: "))


def begin(title: str, subtitle: str, domain: Optional[str] = None) -> dict:
    """Theme, sidebar, application bar and page header. Returns the freshness rows (domain -> API row) for the page to reuse."""
    inject_css()
    rows = freshness_rows()
    sidebar(rows)
    appbar(rows)
    page_header(title, subtitle, domain, rows)
    return rows


def finish() -> None:
    """For pages that inject their own CSS after begin(): re-assert the shared tokens last so shell elements stay consistent."""
    inject_css()
