"""Operational Intelligence (Task 40): one place for the platform's evidence-grounded question answering.

Three capabilities stay separate in the backend (RAG retrieval, the risk-intelligence assembler, the read-only agent) and are presented as one experience here.
The hierarchy never changes: authoritative structured data > validated evidence > retrieved official documents > derived analysis > agent synthesis.
Nothing on this page can override geography, risk abstention, evidence status or provenance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.sections import oi_agent, oi_analyze_risk, oi_ask_reports
from dashboard.styles.theme import load_css

st.set_page_config(page_title="Operational Intelligence", page_icon="🧭", layout="wide")
load_css()

MODES = {
    "Agent": ("Multi-step questions", "Identifies the area, looks up risk status and evidence, retrieves official reports and states the limits. "
              "Read-only, no SQL, no writes; it cannot override geography, abstention or provenance.", oi_agent),
    "Analyze Risk": ("Structured risk analysis", "The risk engine's provisional status and signals for one area, kept separate from documentary evidence and from ML forecasts.",
                     oi_analyze_risk),
    "Ask Reports": ("Questions about official reports", "Answers only from retrieved NDMA / PDMA / PMD passages, with citations. A summary of reports, not a risk assessment.",
                    oi_ask_reports),
}

st.title("🧭 Operational Intelligence")
st.caption("Decision support only; not an official warning. Every answer separates structured data, document evidence, derived analysis and what is unavailable. "
           "A missing risk score means no defensible numeric score exists, not low risk.")

mode = st.radio("What do you want to do?", list(MODES), horizontal=True, key="oi_mode",
                format_func=lambda m: f"{m} · {MODES[m][0]}")
st.caption(MODES[mode][1])
st.divider()
MODES[mode][2].render()
