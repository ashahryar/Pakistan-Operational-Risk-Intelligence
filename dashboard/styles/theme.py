"""
dashboard/styles/theme.py

Loads the dashboard's design-system stylesheet (styles/style.css) into
the Streamlit app, plus the Inter typeface used by the typography
system. Public API (`load_css()`) is unchanged so Home.py does not
need to be modified to pick up the new design system.
"""

from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).resolve().parent / "style.css"

_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@400;500;600;700;800&display=swap" '
    'rel="stylesheet">'
)


def load_css() -> None:
    """
    Inject the Inter typeface and styles/style.css into the page,
    exactly as the original inline <style> block in Home.py did —
    now sourced from an external, versioned stylesheet.
    """
    st.markdown(_FONT_LINK, unsafe_allow_html=True)

    css = _CSS_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)
