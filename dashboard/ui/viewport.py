"""dashboard/ui/viewport.py -- phone detection for the few things CSS cannot do (Task 43).

CSS media queries handle layout. Plotly figures, however, have their pixel height fixed in Python before the browser sees them, so a chart built at a desktop height would
fill a whole phone screen. The request's User-Agent (st.context.headers) tells us when the viewer is on a phone so those heights and the map's initial fit can be reduced.
Tablets and desktops (including a narrow desktop window) keep the desktop sizes; CSS adapts their layout. Outside a running Streamlit session (tests) nothing is detected.
"""

from __future__ import annotations

import re

import streamlit as st

_PHONE = re.compile(r"iPhone|iPod|Windows Phone|Android.*Mobile|Mobile.*Android|\bMobi\b", re.I)
_TABLET = re.compile(r"iPad|Tablet", re.I)

PHONE_MAX_CHART = 360          # px: the tallest ordinary chart on a phone
PHONE_MAP_HEIGHT = 420         # px
PHONE_MAP_WIDTH = 380          # px, used to fit the map's initial view


def user_agent() -> str:
    try:
        return st.context.headers.get("User-Agent", "") or ""
    except Exception:           # no script run context (tests, bare mode)
        return ""


def is_phone(ua: str | None = None) -> bool:
    ua = user_agent() if ua is None else ua
    return bool(_PHONE.search(ua)) and not _TABLET.search(ua)


def chart_height(height: int, ua: str | None = None) -> int:
    """Ordinary chart height: unchanged on tablet/desktop, capped on a phone (never below 240)."""
    return max(240, min(height, PHONE_MAX_CHART)) if is_phone(ua) else height


def map_size(height: int, width: int, ua: str | None = None) -> tuple[int, int]:
    """(height, width hint) for a map: smaller on a phone so it does not fill the screen and the initial fit uses the real phone width."""
    return (min(height, PHONE_MAP_HEIGHT), min(width, PHONE_MAP_WIDTH)) if is_phone(ua) else (height, width)
