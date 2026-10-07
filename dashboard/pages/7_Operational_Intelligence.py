"""Operational Intelligence (Task 40): one place for the platform's evidence-grounded question answering.

Three capabilities stay separate in the backend (RAG retrieval, the risk-intelligence assembler, the read-only agent) and are presented as one experience here.
The hierarchy never changes: authoritative structured data > validated evidence > retrieved official documents > derived analysis > agent synthesis.
Nothing on this page can override geography, risk abstention, evidence status or provenance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.sections import oi_agent, oi_analyze_risk, oi_ask_reports
from dashboard.ui import shell

st.set_page_config(page_title="Intelligence Workspace · PORI", page_icon="🧭", layout="wide")

MODES = {
    "Agent": ("What should I look at?", "Ask a question in plain words. The agent identifies the area, looks up the risk status and evidence, retrieves official reports and states "
              "the limits. Read-only: no SQL, no writes; it cannot override geography, abstention or provenance.", oi_agent),
    "Analyze Risk": ("Explain the operational situation", "The risk engine's provisional status and signals for one area, kept separate from documentary evidence and from forecasts.",
                     oi_analyze_risk),
    "Ask Reports": ("Find evidence in official reports", "Answers only from retrieved NDMA / PDMA / PMD passages, with citations. A summary of reports, not a risk assessment.",
                    oi_ask_reports),
}

shell.begin("Intelligence Workspace", "Evidence-grounded answers about operational risk. Every answer separates structured data, document evidence, derived analysis and "
            "what is unavailable. A missing risk score means no defensible numeric score exists, not low risk. Decision support only; not an official warning.")

mode = st.radio("What do you want to do?", list(MODES), horizontal=True, key="oi_mode",
                format_func=lambda m: f"{m} · {MODES[m][0]}")
st.caption(MODES[mode][1])
st.divider()
MODES[mode][2].render()
shell.finish()
