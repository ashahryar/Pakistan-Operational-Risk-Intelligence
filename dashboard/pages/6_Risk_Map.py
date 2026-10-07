"""
dashboard/pages/6_Risk_Map.py

Task 27/42 -- national operational-risk map. Streamlit -> FastAPI (/api/v1/...) -> serving layer. This page talks only to
dashboard/api_client.py: it does not import the risk engine, pipeline code, Airflow, or the database.

Risk statuses are the Task 23 engine's, shown as served. `risk_score` is null by design in engine v1.0.0 and is displayed
as unavailable, never as a number. Areas with risk but no boundary are listed, not dropped.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.ui import components as C
from dashboard.ui import shell, tokens
from dashboard.ui.maps import ATTRIBUTION, risk_choropleth
from dashboard.utils.api_cache import cached_api
from dashboard.utils.risk_map_helpers import (
    NO_DATA,
    STATUS_ORDER,
    dates_from_rows,
    filter_rows,
    map_frame,
    merge_risk_into_features,
    risk_score_text,
    signal_summary,
    summarize,
    unmapped_risk_frame,
)

st.set_page_config(page_title="Risk Map · PORI", page_icon="🗺️", layout="wide")

LATEST = "Latest available"
ALL = "All"
LEGEND = ["CRITICAL", "HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA", "NO_RISK_DATA"]
AVAIL_ALL, AVAIL_WITH, AVAIL_WITHOUT = "All areas", "Areas with a risk record", "Areas without a risk record"


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


# Cached API reads (5 min, plain dicts via cached_api). A failed result is never kept, so the next run retries.
@cached_api(ttl=300)
def _provinces(base_url: str):
    return _client().admin_units(level=1)


@cached_api(ttl=300)
def _all_risk_rows(base_url: str):
    return _client().risk(limit=2000)


@cached_api(ttl=300)
def _risk_map(base_url: str, level, province, status):
    return _client().risk_map(level=level, province=province, risk_status=status)


@cached_api(ttl=300)
def _risk_on_date(base_url: str, date, province):
    return _client().risk(date=date, province=province, limit=2000)


@cached_api(ttl=300)
def _area_detail(base_url: str, admin_unit_id: int, date):
    c = _client()
    return c.risk_latest(admin_unit_id=admin_unit_id) if date is None else c.risk(date=date, admin_unit_id=admin_unit_id, limit=1)


def _fail(result, fn=None):
    """Show a friendly message (never a traceback) and stop the page."""
    if fn is not None:
        fn.clear()
    st.error(f"Could not load data: {result.message}")
    st.caption("The map reads from the PORI API. Start it with: docker compose up -d --build api "
               "(or: uvicorn api.app.main:app --port 8000). Override the address with PORI_API_URL.")
    st.stop()


base = _client().base_url
shell.begin("Risk Map", "Provisional operational status per administrative area on COD-AB boundaries. A status summarises observed signals against "
            "provisional thresholds; it is not a validated probability, and there is no numeric risk score.", domain="risk")

provinces_res = _provinces(base)
if not provinces_res.ok:
    _fail(provinces_res, _provinces)
province_names = sorted(p["name"] for p in provinces_res.data)

rows_res = _all_risk_rows(base)
if not rows_res.ok:
    _fail(rows_res, _all_risk_rows)
all_dates = dates_from_rows(rows_res.data)
if len(rows_res.data) >= 2000:
    st.warning("The risk history exceeds the API page size; the date list may be incomplete.")

# ---------------------------------------------------------------- filters
f1, f2, f3, f4, f5 = st.columns(5)
level_label = f1.selectbox("Administrative level", ["District", "Province"])
level = 2 if level_label == "District" else 1
province = f2.selectbox("Province", [ALL] + province_names)
status = f3.selectbox("Risk status", [ALL] + STATUS_ORDER[:5])
date_choice = f4.selectbox("Risk date", [LATEST] + all_dates)
availability = f5.selectbox("Data availability", [AVAIL_ALL, AVAIL_WITH, AVAIL_WITHOUT])

province_p = None if province == ALL else province
status_p = None if status == ALL else status
date_p = None if date_choice == LATEST else date_choice

# ---------------------------------------------------------------- data (API filters applied before geometry is downloaded)
map_res = _risk_map(base, level, province_p, status_p if date_p is None else None)
if not map_res.ok:
    _fail(map_res, _risk_map)
fc = map_res.data

risk_rows = None
if date_p is not None:
    day_res = _risk_on_date(base, date_p, province_p)
    if not day_res.ok:
        _fail(day_res, _risk_on_date)
    risk_rows = filter_rows(day_res.data, level)
    if status_p:
        risk_rows = [r for r in risk_rows if r["risk_status"] == status_p]
    fc = merge_risk_into_features(fc, risk_rows)
    if status_p:   # keep only areas matching the chosen status on that date
        fc = {"type": "FeatureCollection", "features": [f for f in fc["features"] if f["properties"]["risk_status"] == status_p]}

summary = summarize(fc, risk_rows)
_REQUIRED = ("total_areas", "areas_with_risk", "areas_without_geometry", "high", "critical", "insufficient_data", "areas_scored", "areas_score_abstained")
if not all(k in summary for k in _REQUIRED):      # self-contained on purpose: a stale process has an older helper module (and no newer helper functions)
    st.error("This view needs a fresh dashboard session. The dashboard process is running older code than this page (its summary is missing fields). Restart the dashboard "
             "(stop `streamlit run` and start it again, or `docker compose up -d --build dashboard`).")
    st.stop()

# the data-availability filter applies to what is drawn and listed (the API already applied the other filters)
if availability != AVAIL_ALL:
    want = availability == AVAIL_WITH
    fc = {"type": "FeatureCollection", "features": [f for f in fc["features"] if bool(f["properties"].get("risk_status")) == want]}

# ---------------------------------------------------------------- summary
c = st.columns(6)
c[0].metric("Areas returned", summary["total_areas"])
c[1].metric("Areas with risk", summary["areas_with_risk"])
c[2].metric("Areas without geometry", summary["areas_without_geometry"])
c[3].metric("HIGH", summary["high"])
c[4].metric("CRITICAL", summary["critical"])
c[5].metric("INSUFFICIENT_DATA", summary["insufficient_data"])
s1, s2, s3 = st.columns(3)
s1.metric("Areas with a numeric score", summary["areas_scored"])
s2.metric("Areas where the score is abstained", summary["areas_score_abstained"])
s3.metric("Latest risk date", max(all_dates) if all_dates else "n/a")
st.caption("Operational status is not a numeric score. A status with no score is an ABSTAINED score, not a low risk: a numeric score needs at least two independent "
           "eligible signal groups with evidence-based weights, which do not exist yet. INSUFFICIENT_DATA means no usable signal was observed. "
           "Missing evidence is never shown as low risk.")
st.caption(f"Scope: {level_label.lower()}s · {province} · status {status} · date {date_choice if date_p else 'latest available per area'} · {availability.lower()}")

# ---------------------------------------------------------------- map + selected area
frame = map_frame(fc)
unm = unmapped_risk_frame(fc, risk_rows)
options = {}
for r in frame.itertuples():
    options[f"{r.admin_unit_name} ({r.province or '—'})"] = int(r.admin_unit_id)
for r in unm.itertuples():
    options.setdefault(f"{r.admin_unit_name} ({r.province or '—'}) — no boundary", int(r.admin_unit_id))
labels = sorted(options)

map_col, side_col = st.columns([2, 1])
picked_id = st.session_state.get("risk_map_pick")
with side_col:
    st.subheader("Area detail")
    index = next((i for i, lb in enumerate(labels) if options[lb] == picked_id), 0)
    label = st.selectbox("Select an area", labels, index=index) if labels else None
    selected_id = options[label] if label else None
    if label is None:
        C.empty_state("Nothing to inspect", "No area matches these filters.")
    else:
        detail_res = _area_detail(base, selected_id, date_p)
        if not detail_res.ok:
            C.notice("warn", "Detail unavailable", detail_res.message or "")
        elif not detail_res.data:
            st.info("No risk record for this area in the selected scope.")
            C.status_badge(None)
        else:
            d = detail_res.data[0]
            st.markdown(f"**{d['admin_unit_name']}** · {d['province'] or '—'}")
            C.status_badge(d["risk_status"])
            st.markdown(f"Operational status: **{tokens.status_label(d['risk_status'])}** · Risk date: `{d['risk_date']}`")
            st.markdown(f"Risk score: {risk_score_text(d['risk_score'])}")
            st.caption(f"Basis `{d['risk_basis']}` · confidence `{d['risk_confidence']}` · data coverage {d['data_coverage_pct']}% · "
                       f"top risk domain {d['top_risk_domain'] or 'none identified'} · {d['calculation_version']} ({d['threshold_status']})")
            st.markdown("**Contributing signals**")
            st.dataframe(signal_summary(d["signals"]), hide_index=True, width="stretch")
            observed, missing = d.get("observed_signal_count"), d.get("missing_signal_count")
            if observed is not None and missing is not None:
                st.caption(f"Evidence status: {observed} signal(s) observed, {missing} missing. Last observation = the risk date above.")
            if d["risk_status"] == "INSUFFICIENT_DATA":
                C.notice("info", "Insufficient evidence", "No usable signal was observed for this area. That is not the same as low risk.")

with map_col:
    fig = risk_choropleth(fc, selected_id=selected_id, height=620)
    if fig is None:
        C.empty_state("No areas with mapped boundaries match these filters", "Change a filter, or see the list of risk records without a boundary below.")
    else:
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="risk_map_chart")
        pts = (getattr(event, "selection", None) or {}).get("points") if event is not None else None
        if pts and pts[0].get("location") is not None and int(pts[0]["location"]) != picked_id:
            st.session_state["risk_map_pick"] = int(pts[0]["location"])
            st.rerun()
        C.legend(LEGEND)
        st.caption(f"{tokens.status_label(NO_DATA)} = a boundary exists but no risk row in this scope. {ATTRIBUTION}")

# ---------------------------------------------------------------- missing geography
st.subheader("Risk records without mapped boundary")
if unm.empty:
    st.success("Every risk record in this scope has a mapped boundary.")
else:
    st.caption("These areas have risk data but no matched boundary geometry (e.g. units absent from the boundary dataset, or "
               "caveated seed units). They are listed here, not dropped from the analysis.")
    cols = [c_ for c_ in ("admin_unit_name", "province", "admin_level", "risk_status", "risk_date", "risk_confidence") if c_ in unm]
    st.dataframe(unm[cols], hide_index=True, width="stretch")

C.provenance(source="PORI API /api/v1/risk", engine="risk-engine-1.0.0 (provisional thresholds)", boundaries="COD-AB v01")
