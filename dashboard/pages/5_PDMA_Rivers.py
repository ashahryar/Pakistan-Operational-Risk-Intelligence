"""PDMA river gauge network and geography evidence (Task 40).

The legacy `pdma_gauge_readings` columns named *current level* and *danger level* are not water levels for most rows (the PDF parser stored flood-limit / design
columns there, and the real inflow can sit in another column), so this page does not draw level, danger or flood-risk indicators from them. It shows what is
reliable: the station inventory, observation coverage, and which stations are tied to a district by official evidence."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.styles.theme import load_css

st.set_page_config(page_title="PDMA River Gauges", page_icon="🌊", layout="wide")
load_css()

STATE_LABEL = {"ELIGIBLE": "Mapped (official evidence)", "CONFLICTING_GEOGRAPHY": "Conflicting evidence", "SECONDARY_ONLY": "Secondary reference only",
               "CAVEATED": "Caveated", "UNRESOLVED": "Unresolved"}
STATE_ORDER = list(STATE_LABEL)


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


@st.cache_data(ttl=300, show_spinner=False)
def _evidence(base_url: str):
    return _client()._get("/api/v1/evidence/gauge-stations")


@st.cache_data(ttl=300, show_spinner=False)
def _unit_history(base_url: str, admin_unit_id: int):
    return _client().risk(admin_unit_id=admin_unit_id, limit=500)


base = _client().base_url
st.title("🌊 PDMA River Gauge Network")
st.caption("PDMA Punjab gauge sitreps (data source stated as FFD and DEOCs). A snapshot of published bulletins, not a live feed. Decision support only.")

res = _evidence(base)
if not res.ok:
    st.error(f"Could not load gauge evidence: {res.message}")
    st.caption("This page reads from the PORI API. Start it with: docker compose up -d --build api (or set PORI_API_URL).")
    st.stop()

data = res.data
summary, stations = data["summary"], pd.DataFrame(data["stations"])
stations["river"] = stations["river"].str.replace(r"\s+DATA SOURCE.*$", "", regex=True)      # a PDF footer fragment that leaked into one river name
counts = summary["state_counts"]

st.warning("**Reading note.** The legacy gauge table's *level* and *danger level* columns are not water levels for most rows, so no level, danger or flood-risk "
           "indicator is shown here. A station is attributed to a district only when official evidence supports it; every other station is shown as unattributed.")

c = st.columns(5)
c[0].metric("Gauge stations", summary["stations"])
c[1].metric("Rivers / nullah groups", int(stations["river"].nunique()))
c[2].metric("Gauge observations", f"{summary['observations']:,}")
c[3].metric("Mapped to a district", counts.get("ELIGIBLE", 0))
c[4].metric("Observations attributable", f"{summary['observations_with_eligible_mapping']:,}")
dmin, dmax = stations["date_min"].min(), stations["date_max"].max()
st.caption(f"Observation dates {dmin} to {dmax}. Unattributed stations still have observations: they are kept, not dropped, and not assigned to any district. "
           f"Mapping version {summary['mapping_version']}.")

st.subheader("Geography evidence coverage")
left, right = st.columns([2, 3])
by_state = pd.DataFrame({"state": [STATE_LABEL[s] for s in STATE_ORDER], "stations": [counts.get(s, 0) for s in STATE_ORDER]})
fig = px.bar(by_state, x="stations", y="state", orientation="h", title="Stations by geography evidence state", text="stations")
fig.update_layout(yaxis={"autorange": "reversed"}, height=300, margin={"l": 0, "r": 10, "t": 40, "b": 0})
left.plotly_chart(fig, use_container_width=True)
right.markdown(
    "- **Mapped** - an official owner states the district (WAPDA) or official coordinates stay inside one boundary district over their stated offset.\n"
    "- **Conflicting** - sources disagree (for example Tarbela: WAPDA states Swabi, which is not in the canonical geography; other references name Haripur). Nothing is selected.\n"
    "- **Secondary reference only** - non-official sources exist; never used for risk.\n"
    "- **Caveated** - the only candidate unit is not a real district (Mangla).\n"
    "- **Unresolved** - no usable evidence; most hill-torrent and nullah sites.")

st.subheader("Stations")
f1, f2 = st.columns(2)
state_pick = f1.multiselect("Evidence state", STATE_ORDER, default=STATE_ORDER, format_func=STATE_LABEL.get)
rivers = sorted(stations["river"].dropna().unique())
river_pick = f2.multiselect("River", rivers, default=rivers)
view = stations[stations["evidence_state"].isin(state_pick) & stations["river"].isin(river_pick)].copy()
view["Geography"] = view["evidence_state"].map(STATE_LABEL)
view["District (evidence-backed)"] = view["admin_unit_name"].fillna("not attributed")
view["Candidates (NOT applied)"] = view["candidate_districts"].apply(lambda x: ", ".join(x) if x else "")
view["Dates"] = view["date_min"].astype(str) + " to " + view["date_max"].astype(str)
table = view[["station_name", "river", "observations", "Dates", "Geography", "District (evidence-backed)", "Candidates (NOT applied)", "ineligibility_reason"]]
table = table.rename(columns={"station_name": "Station", "river": "River", "observations": "Observations", "ineligibility_reason": "Why not attributed"})
st.dataframe(table, hide_index=True, width="stretch")
st.download_button("Download stations (CSV)", table.to_csv(index=False).encode("utf-8"), "pdma_gauge_stations_evidence.csv", "text/csv")

mapped = stations[stations["evidence_state"] == "ELIGIBLE"]
if not mapped.empty:
    st.subheader("Risk-engine gauge signal for mapped stations")
    st.caption("The engine's normalised gauge signal (discharge relative to its own history) and provisional status for the districts that have an evidence-backed station. "
               "This is a status, not a score: no numeric score is produced.")
    for _, m in mapped.iterrows():
        if pd.isna(m.get("admin_unit_id")):
            st.info(f"{m['station_name']}: the API did not return an administrative unit id (API older than this page?). Rebuild it: docker compose up -d --build api")
            continue
        h = _unit_history(base, int(m["admin_unit_id"]))
        if not h.ok:
            st.info(f"{m['station_name']} → {m['admin_unit_name']}: risk history unavailable ({h.message}).")
            continue
        df = pd.DataFrame([{"date": r["risk_date"], "gauge signal": r["signals"]["gauge"], "status": r["risk_status"]} for r in h.data]).sort_values("date")
        df = df[df["gauge signal"].notna()]
        st.markdown(f"**{m['station_name']}** → **{m['admin_unit_name']}** ({m['geography_derivation'].replace('_', ' ')})")
        if df.empty:
            st.caption("No gauge signal rows for this district yet.")
            continue
        fig2 = px.line(df, x="date", y="gauge signal", markers=True, title=f"{m['admin_unit_name']}: normalised gauge signal (not a risk score)")
        fig2.update_layout(height=280, margin={"l": 0, "r": 10, "t": 40, "b": 0}, yaxis_range=[0, 1])
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("Status counts: " + ", ".join(f"{k} {v}" for k, v in df["status"].value_counts().items()))
