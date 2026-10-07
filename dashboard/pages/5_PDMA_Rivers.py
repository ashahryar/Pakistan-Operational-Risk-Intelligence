"""PDMA river gauge network and geography evidence (Task 40, redesigned in Task 42 as a hydrology monitoring network view).

The legacy `pdma_gauge_readings` columns named *current level* and *danger level* are not water levels for most rows (the PDF parser stored flood-limit / design
columns there, and the real inflow can sit in another column), so this page does not draw level, danger or flood-risk indicators from them. It shows what is
reliable: the station inventory (metadata), observation coverage (what was actually reported, and when), and which stations are tied to a district by official evidence."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.ui import components as C
from dashboard.ui import shell, tokens
from dashboard.ui.charts import coverage_timeline, ranked_bar, style_fig
from dashboard.utils.api_cache import cached_api

st.set_page_config(page_title="River & Gauge Network · PORI", page_icon="🌊", layout="wide")

STATE_ORDER = list(tokens.EVIDENCE)


def state_label(s: str) -> str:
    label, glyph = tokens.EVIDENCE[s]
    return f"{glyph} {label}"


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


@cached_api(ttl=120)
def _evidence(base_url: str):
    return _client()._get("/api/v1/evidence/gauge-stations")


@cached_api(ttl=300)
def _unit_history(base_url: str, admin_unit_id: int):
    return _client().risk(admin_unit_id=admin_unit_id, limit=500)


base = _client().base_url
shell.begin("River & Gauge Network", "PDMA Punjab gauge bulletins (data source stated as FFD and DEOCs): the station network, what each station actually reported, "
            "and which stations are tied to a district by official evidence. A snapshot of published bulletins, not a live feed.", domain="pdma_gauge")

res = _evidence(base)
if not res.ok:
    C.api_error(res.message, "This page reads from the PORI API. Start it with: docker compose up -d --build api (or set PORI_API_URL).")
    st.stop()

data = res.data
summary, stations = data["summary"], pd.DataFrame(data["stations"])
stations["river"] = stations["river"].str.replace(r"\s+DATA SOURCE.*$", "", regex=True)      # a PDF footer fragment that leaked into one river name
counts = summary["state_counts"]
unresolved = counts.get("UNRESOLVED", 0)

C.notice("info", "Reading note", "Station metadata (name, river, geography evidence) is shown separately from observations (how many report dates a station has, and when). "
         "The legacy table's level and danger-level columns are not water levels for most rows, so no level, danger or flood-risk indicator is shown here. "
         "A station is attributed to a district only when official evidence supports it.")

C.kpis([("Gauge stations", summary["stations"]), ("Mapped to a district", counts.get("ELIGIBLE", 0), "official evidence"),
        ("Unresolved", unresolved, "no usable evidence"), ("Observation days", summary["observations"], "one per station and report date"),
        ("Latest observation", C._fmt_date(summary.get("latest_observation")))])
if summary.get("observations_source") != "database":
    C.notice("warn", "Observation counts are from a frozen snapshot", "The database could not be read, so counts and dates come from the committed evidence snapshot, not current data.")
st.caption(f"Observation dates {stations['date_min'].min()} to {stations['date_max'].max()} (read from the database). Unattributed stations still have observations: they are kept, "
           f"not dropped, and not assigned to any district. Mapping version {summary['mapping_version']}.")

C.section("Geography evidence coverage", "How many stations can be placed in a district, and why the rest cannot.")
left, right = st.columns([2, 3])
by_state = pd.DataFrame({"state": [state_label(s) for s in STATE_ORDER], "stations": [counts.get(s, 0) for s in STATE_ORDER]})
fig = px.bar(by_state, x="stations", y="state", orientation="h", text="stations")
fig.update_traces(marker_color=tokens.PALETTE["primary"], textposition="outside", hovertemplate="%{y}: %{x} stations<extra></extra>")
fig.update_layout(yaxis={"autorange": "reversed"}, margin={"l": 0, "r": 24, "t": 36, "b": 0})
left.plotly_chart(style_fig(fig, "Stations by geography evidence state", 300, xtitle="Stations", ytitle=""), width="stretch")
right.markdown(
    "- **Mapped** - an official owner states the district (WAPDA) or official coordinates stay inside one boundary district over their stated offset.\n"
    "- **Conflicting** - sources disagree (for example Tarbela: WAPDA states Swabi, which is not in the canonical geography; other references name Haripur). Nothing is selected.\n"
    "- **Secondary reference only** - non-official sources exist; never used for risk.\n"
    "- **Caveated** - the only candidate unit is not a real district (Mangla).\n"
    "- **Unresolved** - no usable evidence; most hill-torrent and nullah sites.")
C.empty_state("Station map not available", "The sources publish no coordinates for most stations, and a station is never placed on a district without evidence, so a point map would "
              "invent precision. Mapped stations are shown by district on the Risk Map.")

C.section("Stations", "Station metadata and observation coverage.")
f1, f2 = st.columns(2)
state_pick = f1.multiselect("Evidence state", STATE_ORDER, default=STATE_ORDER, format_func=state_label)
rivers = sorted(stations["river"].dropna().unique())
river_pick = f2.multiselect("River", rivers, default=rivers)
view = stations[stations["evidence_state"].isin(state_pick) & stations["river"].isin(river_pick)].copy()
if view.empty:
    C.empty_state("No stations match these filters", "Widen the evidence-state or river selection.")
else:
    view["Geography"] = view["evidence_state"].map(state_label)
    view["District (evidence-backed)"] = view["admin_unit_name"].fillna("not attributed")
    view["Candidates (NOT applied)"] = view["candidate_districts"].apply(lambda x: ", ".join(x) if x else "")
    table = view[["station_name", "river", "Geography", "District (evidence-backed)", "Candidates (NOT applied)", "observations", "date_min", "date_max", "ineligibility_reason"]]
    table = table.rename(columns={"station_name": "Station", "river": "River", "observations": "Observation days", "date_min": "First observation",
                                  "date_max": "Latest observation", "ineligibility_reason": "Why not attributed"})
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("Download stations (CSV)", table.to_csv(index=False).encode("utf-8"), "pdma_gauge_stations_evidence.csv", "text/csv")

C.section("Observation coverage", "What each station actually reported, and over which dates. Metadata is separate from observations: a station can exist in the network with few reports.")
if view.empty:
    C.empty_state("No stations in the current filter", "Widen the filters above to see observation coverage.")
else:
    c1, c2 = st.columns([3, 2])
    with c1:
        fig_cov = coverage_timeline(view, name="station_name", start="date_min", end="date_max", group="river", title="Reporting period per station",
                                    source="PDMA Punjab gauge bulletins")
        if fig_cov is not None:
            st.plotly_chart(fig_cov, width="stretch", key="gauge_cov")
    with c2:
        fig_days = ranked_bar(view, "station_name", "observations", title="Observation days per station", unit="report dates", source="PDMA Punjab gauge bulletins",
                              n=12, as_of=C._fmt_date(summary.get("latest_observation")))
        if fig_days is not None:
            st.plotly_chart(fig_days, width="stretch", key="gauge_days")
    pick = st.selectbox("Inspect a station", sorted(view["station_name"]), key="gauge_pick")
    row = view[view["station_name"] == pick].iloc[0]
    st.markdown(f"**{row['station_name']}** · {row['river']}")
    st.markdown(f"Geography: {state_label(row['evidence_state'])} · District: {row['admin_unit_name'] if pd.notna(row['admin_unit_name']) else 'not attributed'}")
    st.caption(f"Observation days {row['observations']:,} · first {C._fmt_date(row['date_min'])} · latest {C._fmt_date(row['date_max'])} · "
               + (f"candidate districts (not applied): {', '.join(row['candidate_districts'])}" if len(row["candidate_districts"]) else "no candidate districts")
               + (f" · why not attributed: {row['ineligibility_reason']}" if pd.notna(row["ineligibility_reason"]) else ""))

mapped = stations[stations["evidence_state"] == "ELIGIBLE"]
if not mapped.empty:
    C.section("Risk-engine gauge signal for mapped stations", "The engine's normalised gauge signal (discharge relative to its own history) and provisional status for the districts that "
              "have an evidence-backed station. This is a status, not a score: no numeric score is produced.")
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
            C.empty_state("No gauge signal rows for this district yet", "")
            continue
        fig2 = px.line(df, x="date", y="gauge signal", markers=True)
        fig2.update_traces(hovertemplate="%{x}<br>gauge signal %{y:.2f}<extra></extra>")
        fig2.update_layout(yaxis_range=[0, 1])
        st.plotly_chart(style_fig(fig2, f"{m['admin_unit_name']}: normalised gauge signal (not a risk score)", 280, xtitle="Risk date", ytitle="Signal (0-1)"), width="stretch")
        st.caption("Status counts: " + ", ".join(f"{tokens.status_label(k)} {v}" for k, v in df["status"].value_counts().items()))

C.provenance(source="PDMA Punjab gauge bulletins", geography=f"gauge-geo {summary['mapping_version']}", observations=summary.get("observations_source"))
