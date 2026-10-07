"""
dashboard/pages/6_Risk_Map.py

Task 27 -- national operational-risk map. Streamlit -> FastAPI (/api/v1/...) -> serving layer. This page talks only to
dashboard/api_client.py: it does not import the risk engine, pipeline code, Airflow, or the database.

Risk statuses are the Task 23 engine's, shown as served. `risk_score` is null by design in engine v1.0.0 and is displayed
as unavailable, never as a number. Areas with risk but no boundary are listed, not dropped.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.styles.theme import load_css
from dashboard.utils.risk_map_helpers import (
    NO_DATA,
    STATUS_COLORS,
    STATUS_ORDER,
    dates_from_rows,
    filter_rows,
    map_frame,
    mapped_geojson,
    merge_risk_into_features,
    risk_score_text,
    signal_summary,
    summarize,
    unmapped_risk_frame,
)

st.set_page_config(page_title="Operational Risk Map", page_icon="🗺️", layout="wide")
load_css()

LATEST = "Latest available"
ALL = "All"


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


# Cached API reads (5 min). A failed result is not kept: the cache is cleared so the next run retries.
@st.cache_data(ttl=300, show_spinner=False)
def _provinces(base_url: str):
    return _client().admin_units(level=1)


@st.cache_data(ttl=300, show_spinner=False)
def _all_risk_rows(base_url: str):
    return _client().risk(limit=2000)


@st.cache_data(ttl=300, show_spinner="Loading map from the API…")
def _risk_map(base_url: str, level, province, status):
    return _client().risk_map(level=level, province=province, risk_status=status)


@st.cache_data(ttl=300, show_spinner=False)
def _risk_on_date(base_url: str, date, province):
    return _client().risk(date=date, province=province, limit=2000)


@st.cache_data(ttl=300, show_spinner=False)
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

st.title("🗺️ National Operational Risk Map")
st.caption("Served by the PORI API. Statuses are provisional engine outputs (thresholds are not authoritative); "
           "no numeric risk score exists in this version.")

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
f1, f2, f3, f4 = st.columns(4)
level_label = f1.selectbox("Administrative level", ["District", "Province"])
level = 2 if level_label == "District" else 1
province = f2.selectbox("Province", [ALL] + province_names)
status = f3.selectbox("Risk status", [ALL] + STATUS_ORDER[:5])
date_choice = f4.selectbox("Risk date", [LATEST] + all_dates)

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

# ---------------------------------------------------------------- summary cards
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
st.caption("A status with no score is an ABSTAINED score, not a low risk: a numeric score needs at least two independent eligible signal groups with "
           "evidence-based weights, which do not exist yet. INSUFFICIENT_DATA means no usable signal was observed. Missing evidence is never shown as low risk.")
st.caption(f"Scope: {level_label.lower()}s · {province} · status {status} · date "
           f"{date_choice if date_p else 'latest available per area'}")

# ---------------------------------------------------------------- map
frame = map_frame(fc)
if frame.empty:
    st.info("No areas with mapped geometry match these filters.")
else:
    frame["risk_score_text"] = [risk_score_text(None if pd.isna(s) else s) for s in frame["risk_score"]]
    order = [s for s in STATUS_ORDER + [NO_DATA] if s in set(frame["status"])]
    fig = px.choropleth_map(
        frame, geojson=mapped_geojson(fc), locations="admin_unit_id", featureidkey="properties.admin_unit_id",
        color="status", color_discrete_map=STATUS_COLORS, category_orders={"status": order},
        hover_name="admin_unit_name",
        hover_data={"admin_unit_id": False, "status": True, "province": True, "risk_date": True, "risk_confidence": True,
                    "risk_score_text": True},
        map_style="carto-positron", zoom=4.3, center={"lat": 30.4, "lon": 69.5}, opacity=0.75, height=620)
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, legend_title_text="Risk status")
    st.plotly_chart(fig, width="stretch")
    st.caption(f"{NO_DATA} = boundary exists but no risk row in this scope. Boundaries: COD-AB v01 (2022-09-09, CC BY-IGO), "
               "a third-party dataset that is not government-certified.")

# ---------------------------------------------------------------- area detail
st.subheader("Area detail")
options = {}
for r in frame.itertuples():
    options[f"{r.admin_unit_name} ({r.province or '—'})"] = int(r.admin_unit_id)
unm = unmapped_risk_frame(fc, risk_rows)
for r in unm.itertuples():
    options.setdefault(f"{r.admin_unit_name} ({r.province or '—'}) — no boundary", int(r.admin_unit_id))
if options:
    label = st.selectbox("Select an area", sorted(options))
    detail_res = _area_detail(base, options[label], date_p)
    if not detail_res.ok:
        st.warning(f"Detail unavailable: {detail_res.message}")
    elif not detail_res.data:
        st.info("No risk record for this area in the selected scope.")
    else:
        d = detail_res.data[0]
        left, right = st.columns(2)
        left.markdown(
            f"**{d['admin_unit_name']}** · {d['province'] or '—'}  \n"
            f"Risk date: `{d['risk_date']}`  \nStatus: **{d['risk_status']}**  \nBasis: `{d['risk_basis']}`  \n"
            f"Confidence: `{d['risk_confidence']}`  \nData coverage: {d['data_coverage_pct']}%  \n"
            f"Top risk domain: {d['top_risk_domain'] or 'none identified'}  \nCalculation version: `{d['calculation_version']}` "
            f"({d['threshold_status']})  \nRisk score: {risk_score_text(d['risk_score'])}")
        right.dataframe(signal_summary(d["signals"]), hide_index=True, width="stretch")
else:
    st.info("Nothing to inspect for these filters.")

# ---------------------------------------------------------------- missing geography
st.subheader("Risk records without mapped boundary")
if unm.empty:
    st.success("Every risk record in this scope has a mapped boundary.")
else:
    st.caption("These areas have risk data but no matched boundary geometry (e.g. units absent from the boundary dataset, or "
               "caveated seed units). They are listed here, not dropped from the analysis.")
    cols = [c_ for c_ in ("admin_unit_name", "province", "admin_level", "risk_status", "risk_date", "risk_confidence") if c_ in unm]
    st.dataframe(unm[cols], hide_index=True, width="stretch")
