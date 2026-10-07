"""dashboard/ui/components.py

Task 42 -- the shared building blocks of every page. All values are HTML-escaped. Components never invent a value: a missing value is rendered as
"n/a"/"Unavailable", never 0, and a status is always glyph + label (never colour alone).

Pure helpers (`*_html`, `freshness_text`) return strings so they are unit-testable without Streamlit.
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from typing import Optional, Sequence

import streamlit as st

from dashboard.ui import tokens

NA = "n/a"


def _fmt_date(v) -> Optional[str]:
    if v in (None, ""):
        return None
    if isinstance(v, (date, datetime)):
        return v.strftime("%d %b %Y")
    try:
        return datetime.fromisoformat(str(v).replace("Z", "")).strftime("%d %b %Y")
    except ValueError:
        return str(v)


def freshness_text(d: dict) -> str:
    """Words for a describe() result (dashboard.utils.freshness). Always shows the actual date when one exists; never relies on colour."""
    latest = _fmt_date(d.get("latest"))
    state = d.get("state")
    if state == "current":
        return f"Latest available · {latest}"
    if state == "stale":
        return f"Stale · latest successful snapshot {latest} ({d.get('age_days')} days old)"
    if state == "source_unavailable":
        return f"Source unavailable — latest successful snapshot: {latest}" if latest else "Source unavailable"
    if state == "no_data":
        return "No observations available"
    return "Freshness unavailable"


def freshness_chip_html(d: dict, label: Optional[str] = None) -> str:
    state = d.get("state") if d.get("state") in tokens.FRESHNESS else "unknown"
    _, glyph, colour = tokens.FRESHNESS[state]
    prefix = f"{escape(label)}: " if label else ""
    return (f'<span class="pori-chip" title="{escape(freshness_text(d))}"><span class="g" style="color:{colour}" aria-hidden="true">{glyph}</span>'
            f'<span>{prefix}{escape(freshness_text(d))}</span></span>')


def status_badge_html(status: Optional[str], extra: Optional[str] = None) -> str:
    label, glyph, fill, text, meaning = tokens.STATUS.get(status or "NO_RISK_DATA", tokens.STATUS["NO_RISK_DATA"])
    more = f" · {escape(extra)}" if extra else ""
    return (f'<span class="pori-badge" style="border-color:{fill}; color:{text}; background:{fill}33" title="{escape(meaning)}">'
            f'<span class="g" aria-hidden="true">{glyph}</span><span>{escape(label)}{more}</span></span>')


def kpi_values(items: Sequence[tuple]) -> list[tuple]:
    """(label, shown value, sub). None/"" is n/a; zero is a real value and shown as 0. Pure."""
    out = []
    for item in items:
        label, value = item[0], item[1]
        missing = value is None or value == ""
        if not missing and isinstance(value, float) and value == value and value.is_integer():
            value = int(value)                                      # 199.0 -> 199 (NumPy/pandas floats included below)
        elif not missing and hasattr(value, "item") and not isinstance(value, (int, float, str)):
            py = value.item()
            value = int(py) if isinstance(py, float) and py == py and float(py).is_integer() else py
        shown = NA if missing else (f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else (f"{value:,.1f}" if isinstance(value, float) else str(value)))
        out.append((str(label), shown, item[2] if len(item) > 2 else None))
    return out


_NOTICE = {"info": "ⓘ", "warn": "▲", "error": "✕", "unavail": "○", "ok": "●"}


def notice_html(kind: str, title: str, body: str = "") -> str:
    return (f'<div class="pori-notice {kind}" role="status"><span class="g" aria-hidden="true">{_NOTICE.get(kind, "ⓘ")}</span>'
            f'<div class="b"><b>{escape(title)}</b>{(" — " + escape(body)) if body else ""}</div></div>')


def legend_html(statuses: Sequence[str]) -> str:
    items = "".join(f'<span><i style="background:{tokens.status_fill(s)}"></i><span aria-hidden="true">{tokens.status_glyph(s)}</span> {escape(tokens.status_label(s))}</span>'
                    for s in statuses)
    return f'<div class="pori-legend" role="list" aria-label="Legend">{items}</div>'


def provenance_html(**fields) -> str:
    parts = [f"<b>{escape(k.replace('_', ' ').capitalize())}</b> {escape(str(v))}" for k, v in fields.items() if v not in (None, "")]
    return f'<div class="pori-prov">{" · ".join(parts)}</div>'


# ---- Streamlit renderers
def section(title: str, caption: Optional[str] = None) -> None:
    st.subheader(title)
    if caption:
        st.caption(caption)


def kpis(items: Sequence[tuple]) -> None:
    """The one KPI primitive: a row of st.metric (accessible, testable), styled flat by the design system. items: (label, value, sub)."""
    vals = kpi_values(items)
    for col, (label, shown, sub) in zip(st.columns(len(vals)), vals):
        col.metric(label, shown)
        if sub:
            col.caption(sub)


def notice(kind: str, title: str, body: str = "") -> None:
    st.markdown(notice_html(kind, title, body), unsafe_allow_html=True)


def status_badge(status: Optional[str], extra: Optional[str] = None) -> None:
    st.markdown(status_badge_html(status, extra), unsafe_allow_html=True)


def legend(statuses: Sequence[str]) -> None:
    st.markdown(legend_html(statuses), unsafe_allow_html=True)


def provenance(**fields) -> None:
    st.markdown(provenance_html(**fields), unsafe_allow_html=True)


def empty_state(title: str, body: str = "", kind: str = "unavail") -> None:
    """A professional empty panel: says what is missing and why. Never a blank area, never a zero."""
    notice(kind, title, body)


def api_error(message: Optional[str], hint: Optional[str] = None) -> None:
    notice("error", "This view could not load", (message or "The API did not answer.") + (f" {hint}" if hint else ""))


def stale_session_error() -> None:
    notice("warn", "This view needs a fresh dashboard session",
           "The running dashboard process holds older code than this page. Restart it (stop `streamlit run` and start it again, or `docker compose up -d --build dashboard`).")
