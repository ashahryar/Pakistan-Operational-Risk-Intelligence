import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.components.alerts import render_national_alert_center
from dashboard.components.executive_landing import (
    render_coverage,
    render_intro,
    render_navigation,
    render_ndma_kpis,
    render_risk_availability,
    risk_availability,
)
from dashboard.db import (
    get_casualties,
    get_dashboard_summary,
    get_geo_summary,
    get_ndma_summary,
    get_pmd_weather,
    get_rainfall,
)
from dashboard.sections.disaster import render_disaster_section
from dashboard.sections.geo_intelligence import render_geo_intelligence_section
from dashboard.styles.theme import load_css

st.set_page_config(page_title="Pakistan Operational Risk Intelligence", page_icon="🇵🇰", layout="wide", initial_sidebar_state="expanded")
load_css()


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


@st.cache_data(ttl=120, show_spinner=False)
def _risk_latest(base_url: str):
    return _client().risk_latest(limit=500)


@st.cache_data(ttl=300, show_spinner=False)
def _gauge_evidence(base_url: str):
    return _client()._get("/api/v1/evidence/gauge-stations")


base = _client().base_url
casualties = get_casualties()
weather = get_pmd_weather()
rainfall = get_rainfall()
ndma = get_ndma_summary()

risk_res = _risk_latest(base)
risk_rows = risk_res.data if risk_res.ok and risk_res.data else []
risk = risk_availability(risk_rows) if risk_rows else None
risk_date = max((r["risk_date"] for r in risk_rows), default=None)
evidence_res = _gauge_evidence(base)
evidence = evidence_res.data if evidence_res.ok else None

render_intro()
render_ndma_kpis(ndma, casualties)
st.divider()
render_coverage(rainfall, weather, casualties, evidence, risk)
st.divider()
render_risk_availability(risk, risk_date)
st.divider()
render_national_alert_center(get_dashboard_summary())
st.divider()
render_disaster_section(casualties)
st.divider()
render_geo_intelligence_section(get_geo_summary())
st.divider()
render_navigation()
