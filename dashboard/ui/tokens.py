"""dashboard/ui/tokens.py

Task 42 -- the single source of design tokens and status semantics.

Chosen with the UI/UX Pro Max skill (`--design-system`, dense dashboard, subtle motion): style "Minimalism & Swiss" (grid-based, high contrast,
functional), typography pairing "Dashboard Data" (Fira Sans for text, Fira Code for figures), blue primary with an amber accent. The skill's default
surface is light; PORI keeps a dark operations-console surface (the skill lists dark as supported) because every legacy page and chart is dark, so the
tokens below are the skill's blue/amber family re-derived for a dark surface and checked for WCAG contrast in tests/dashboard/test_design_system.py.

Status semantics live here ONCE: every badge, map fill, chart colour, table cell and filter takes its colour, label and glyph from STATUS / FRESHNESS.
A status is never colour alone: each one has a text label and a distinct glyph.
"""

from __future__ import annotations

PALETTE = {
    "bg": "#0B1220", "surface": "#111A2B", "elevated": "#17233A", "border": "#2A3A55",
    "text": "#E6EDF3", "text_2": "#B7C3D3", "muted": "#93A1B5",
    "primary": "#60A5FA", "accent": "#F59E0B", "info": "#7DD3FC",
    "success": "#4ADE80", "warning": "#FBBF24", "danger": "#F87171", "critical": "#FCA5A5",
    "unavailable": "#A3AEC0", "insufficient": "#A3AEC0",
}

FONT_TEXT = "'Fira Sans', 'Segoe UI', system-ui, sans-serif"
FONT_DATA = "'Fira Code', 'Cascadia Mono', Consolas, monospace"
FONT_URL = ("https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@400;500;600;700&display=swap")

SPACE = {"1": 4, "2": 8, "3": 12, "4": 16, "5": 24, "6": 32}       # px, 4-pt scale
RADIUS = 6                                                          # one radius for every card, input and badge
TYPE_SCALE = {"title": 28, "page": 22, "section": 16, "kpi": 28, "body": 14, "label": 12, "meta": 12}

# risk status -> (label, glyph, map/chart fill, badge text colour, meaning)
STATUS = {
    "CRITICAL": ("Critical", "◆", "#B91C1C", "#FECACA", "Observed signals exceed the provisional critical threshold"),
    "HIGH": ("High", "▲", "#EF4444", "#FECACA", "Observed signals exceed the provisional high threshold"),
    "MODERATE": ("Moderate", "◐", "#F59E0B", "#FDE68A", "Observed signals are between the provisional thresholds"),
    "LOW": ("Low", "●", "#22C55E", "#BBF7D0", "Observed signals are below the provisional thresholds"),
    "INSUFFICIENT_DATA": ("Insufficient data", "○", "#64748B", "#CBD5E1", "No usable signal was observed; this is not low risk"),
    "NO_SIGNAL": ("No signal", "–", "#475569", "#CBD5E1", "The engine found no signal"),
    "NO_RISK_DATA": ("No risk record", "·", "#1E293B", "#B7C3D3", "A boundary exists but there is no risk record in this scope"),
}

# data freshness state -> (label, glyph, colour)
FRESHNESS = {
    "current": ("Latest available", "●", "#4ADE80"),
    "stale": ("Stale", "◐", "#FBBF24"),
    "source_unavailable": ("Source unavailable", "✕", "#F87171"),
    "no_data": ("No observations available", "○", "#A3AEC0"),
    "unknown": ("Freshness unavailable", "?", "#A3AEC0"),
}

# geography evidence state -> (label, glyph)
EVIDENCE = {
    "ELIGIBLE": ("Mapped (official evidence)", "●"), "CONFLICTING_GEOGRAPHY": ("Conflicting evidence", "◆"), "SECONDARY_ONLY": ("Secondary reference only", "◐"),
    "CAVEATED": ("Caveated", "▲"), "UNRESOLVED": ("Unresolved", "○"),
}


def status_fill(status: str | None) -> str:
    return STATUS.get(status or "NO_RISK_DATA", STATUS["NO_RISK_DATA"])[2]


def status_label(status: str | None) -> str:
    return STATUS.get(status or "NO_RISK_DATA", STATUS["NO_RISK_DATA"])[0]


def status_glyph(status: str | None) -> str:
    return STATUS.get(status or "NO_RISK_DATA", STATUS["NO_RISK_DATA"])[1]


def status_text(status: str | None) -> str:
    """Plain-text form for tables and filters: glyph + label (never colour alone)."""
    return f"{status_glyph(status)} {status_label(status)}"
