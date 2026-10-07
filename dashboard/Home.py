"""dashboard/Home.py -- Executive overview (Task 42).

Hierarchy: purpose -> national snapshot -> major operational signals -> geographic overview -> source freshness -> recent ingestion -> evidence and limits.
Only real values: a missing value is n/a, NULL risk_score is "not computed" (never 0, never low risk), and nothing is called live.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Executive Overview · PORI", page_icon="🇵🇰", layout="wide", initial_sidebar_state="expanded")

from dashboard.api_client import RiskApiClient  # noqa: E402
from dashboard.components.executive_landing import latest, risk_availability  # noqa: E402
from dashboard.db import get_casualties, get_dashboard_summary, get_geo_summary, get_ndma_summary  # noqa: E402
from dashboard.sections.geo_intelligence import render_geo_intelligence_section  # noqa: E402
from dashboard.ui import components as C  # noqa: E402
from dashboard.ui import shell, tokens  # noqa: E402
from dashboard.ui.maps import ATTRIBUTION, risk_choropleth  # noqa: E402
from dashboard.utils.api_cache import cached_api  # noqa: E402
from dashboard.utils.freshness import describe  # noqa: E402


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


@cached_api(ttl=120)
def _risk_latest(base_url: str):
    return _client().risk_latest(limit=500)


@cached_api(ttl=120)
def _gauge_evidence(base_url: str):
    return _client()._get("/api/v1/evidence/gauge-stations")


@cached_api(ttl=300)
def _risk_map(base_url: str):
    return _client().risk_map(level=2)


base = _client().base_url
rows = shell.begin("Executive Overview", "What is happening across Pakistan, where data exists, what has changed and what is currently unavailable.")

casualties = get_casualties()
ndma = get_ndma_summary()
risk_res = _risk_latest(base)
risk_rows = risk_res.data if risk_res.ok and risk_res.data else []
risk = risk_availability(risk_rows) if risk_rows else None
evidence_res = _gauge_evidence(base)
evidence = evidence_res.data if evidence_res.ok else None

# ---------------------------------------------------------------- 1. national snapshot
C.section("National snapshot", "Disaster impact from NDMA situation reports (province level).")
s = ndma.iloc[0] if ndma is not None and len(ndma) else {}
nd = describe(rows.get("ndma"))
first = latest(casualties.sort_values("report_date").head(1), "report_date") if casualties is not None and not casualties.empty else None
C.kpis([("Deaths", s.get("total_deaths") if len(s) else None, "peak reported per province, summed"),
        ("Injured", s.get("total_injured") if len(s) else None, "peak reported per province, summed"),
        ("Houses damaged", s.get("total_houses_damaged") if len(s) else None, "cumulative; blank is not reported"),
        ("Persons rescued", s.get("total_persons_rescued") if len(s) else None, "cumulative"),
        ("Provinces reporting", s.get("provinces_affected") if len(s) else None, "of 7 provinces and territories")])
st.caption(f"NDMA reports are cumulative: each figure is the peak reported value per province, summed — never the sum of every report "
           f"(reports {first or 'n/a'} to {C._fmt_date(nd['latest']) or 'n/a'}).")

# ---------------------------------------------------------------- 2. major operational signals
C.section("Operational signals", "Risk status availability and the latest official weather advisory.")
left, right = st.columns([3, 2])
with left:
    if risk is None:
        C.empty_state("Risk status unavailable", "The risk API did not return any record, so no area status can be shown.")
    else:
        C.kpis([("Areas with a risk record", risk["areas"]), ("With a usable signal", risk["with_usable_signal"]),
                ("Numeric scores", risk["scored"], "score is not computed where evidence is insufficient"),
                ("Score abstained", risk["abstained"])])
        statuses = [s_ for s_ in ("CRITICAL", "HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA", "NO_SIGNAL") if risk["by_status"].get(s_)]
        st.markdown(" ".join(C.status_badge_html(s_, str(risk["by_status"][s_])) for s_ in statuses), unsafe_allow_html=True)
        st.caption(f"Latest risk date {C._fmt_date(risk['latest_date'])}. Status compares observed signals with provisional thresholds. "
                   "INSUFFICIENT_DATA means no usable signal, which is not low risk.")
with right:
    alert = (get_dashboard_summary() or {}).get("latest_alert")
    pmd = describe(rows.get("pmd_weather"))
    st.markdown("**Latest PMD advisory**")
    if alert is None:
        C.empty_state("No advisory stored", "No PMD advisory is in the data. This is not confirmation that none is active.")
    else:
        issued = C._fmt_date(alert.get("scraped_at"))
        st.markdown(f"{alert.get('alert_type', 'Weather advisory')} · severity {str(alert.get('severity', 'not stated')).lower()} · captured {issued}")
        text = str(alert.get("forecast") or "")
        st.caption((text[:360] + ("…" if len(text) > 360 else "")) or "No advisory text stored.")
    if pmd["state"] == "source_unavailable":
        C.notice("unavail", "PMD source unavailable", f"Latest successful snapshot: {C._fmt_date(pmd['latest'])}. This is not a current advisory.")

# ---------------------------------------------------------------- 3. geographic overview
C.section("Geographic overview", "Latest operational status by district. Open the Risk Map for filters, dates and area detail.")
map_res = _risk_map(base)
if not map_res.ok:
    C.api_error(map_res.message, "The overview map reads from the PORI API.")
else:
    fig = risk_choropleth(map_res.data, height=460)
    if fig is None:
        C.empty_state("No boundaries available", "The API returned no area with a mapped boundary.")
    else:
        st.plotly_chart(fig, width="stretch", key="home_map")
        C.legend(["CRITICAL", "HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA", "NO_RISK_DATA"])
        st.caption(ATTRIBUTION)
try:
    st.page_link("pages/6_Risk_Map.py", label="Open the Risk Map →")
except Exception:
    pass

# ---------------------------------------------------------------- 4. source freshness
C.section("Source freshness", "The newest date in each source's own data, and the state of its ingestion.")
fresh_rows = []
for key in ("ndma", "pdma_rainfall", "pdma_gauge", "pmd_weather", "pdma_daily", "risk"):
    r = rows.get(key)
    d = describe(r)
    glyph = tokens.FRESHNESS[d["state"] if d["state"] in tokens.FRESHNESS else "unknown"][1]
    fresh_rows.append({"Source": (r or {}).get("label", key), "Date kind": (r or {}).get("date_kind", "n/a").replace("_", " "),
                       "Latest available": C._fmt_date(d["latest"]) or "n/a", "Last successful ingestion": C._fmt_date(d["last_ingestion"]) or "n/a",
                       "State": f"{glyph} {C.freshness_text(d)}"})
st.dataframe(pd.DataFrame(fresh_rows), hide_index=True, width="stretch")

# ---------------------------------------------------------------- 5. recent changes
C.section("Recent ingestion", "What most recently arrived, newest first. Taken from the ingestion timestamps, not estimated.")
recent = sorted((r for r in rows.values() if r.get("last_ingestion_at")), key=lambda r: r["last_ingestion_at"], reverse=True)
if not recent:
    C.empty_state("No ingestion recorded", "No domain reports a last ingestion time.")
else:
    st.markdown("\n".join(f"- **{r['label']}** — last successful ingestion {C._fmt_date(r['last_ingestion_at'])}"
                          + (f"; latest data {C._fmt_date(r['latest_data_date'])}" if r.get("latest_data_date") else "") for r in recent))

# ---------------------------------------------------------------- 6. evidence and limitations
C.section("Evidence and limitations")
gs = (evidence or {}).get("summary", {})
states = gs.get("state_counts", {})
notes = [
    "No numeric risk score exists: score_v2 abstains until at least two independent eligible signal groups with evidence-based weights are available. A status is not a probability.",
    f"River gauges: {states.get('ELIGIBLE', 0)} of {gs.get('stations', 0)} stations are tied to a district by official evidence; the rest are shown as unresolved, conflicting or secondary-only and are never attributed."
    if gs else "River-gauge geography evidence is unavailable (the API did not answer).",
    "Statuses use provisional thresholds that are not authoritative. This platform is decision support, not an official warning.",
]
notes += [f"{r['label']}: {r['note']}" for r in rows.values() if r.get("note") and r["domain"] in ("pdma_rainfall", "pmd_weather")]
st.markdown("\n".join(f"- {n}" for n in notes))
with st.expander("Geographic resolution coverage"):
    render_geo_intelligence_section(get_geo_summary())

C.provenance(sources="NDMA, PDMA Punjab, PMD", geography="COD-AB v01", api=base)
shell.finish()
