"""Operational Intelligence section (Task 40): the former 8_Intelligence.py page as a render() function. Logic unchanged."""



from datetime import date

import pandas as pd
import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.utils.api_cache import cached_api
from dashboard.utils.intelligence_helpers import area_options, ml_caption, ml_table, risk_metrics, score_caption, signal_summary, status_banner
from dashboard.utils.rag_helpers import MODES, evidence_caption, evidence_rows, relevance_notice




@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


@cached_api(ttl=300)
def _admin_units(base_url: str, level: int):
    return _client().admin_units(level=level)


def _units(base_url: str):
    rows = []
    for level in (1, 2):
        res = _admin_units(base_url, level)
        if res.ok and res.data:
            rows += [{"id": u["id"], "name": u["name"], "level": u["level"], "province": u.get("province")} for u in res.data]
    return rows



def render() -> None:
    st.subheader("Operational Intelligence")
    st.caption("Computed risk-engine context and documentary evidence from official reports, kept separate. "
               "Decision support only - not an official warning.")

    base = _client().base_url
    options = area_options(_units(base))
    with st.form("intel"):
        question = st.text_input("Your question", placeholder="e.g. Why is Sialkot classified as MODERATE?")
        c1, c2, c3 = st.columns(3)
        area = c1.selectbox("Area", list(options))
        mode = c2.selectbox("Evidence retrieval", list(MODES), format_func=MODES.get)
        top_k = c3.slider("Evidence passages", 1, 10, 5)
        use_date = st.checkbox("Look up the risk on a specific date (otherwise the latest available)")
        risk_date = st.date_input("Risk date", value=date.today()) if use_date else None
        submitted = st.form_submit_button("Ask")

    if submitted:
        if len((question or "").strip()) < 2:
            st.warning("Please type a question (at least 2 characters).")
            st.stop()
        with st.spinner("Collecting risk context and evidence..."):
            res = _client().intelligence(question.strip(), mode=mode, admin_unit_id=options[area],
                                         date=risk_date.isoformat() if risk_date else None, top_k=top_k)
        body = res.data if isinstance(res.data, dict) and "risk_context" in res.data else None
        if body is None:
            st.error(f"Could not get an answer: {res.message}")
            if res.error_kind == "connection":
                st.caption("The service is not reachable. Start the API with: docker compose up -d --build api "
                           "(or: uvicorn api.app.main:app --port 8000). Override the address with PORI_API_URL.")
            st.stop()

        status = body["status"]
        level, message = status_banner(status)
        getattr(st, level)(f"**{status}** - {message}")
        qc = body.get("question_context") or {}
        unit = qc.get("admin_unit")
        st.caption("Area: " + (f"{unit['name']} ({qc.get('target_basis')})" if unit else f"not determined ({qc.get('geography_status')})"))

        # ---------------------------------------------------------------- computed context
        st.subheader("Operational Risk Context")
        rcx = body["risk_context"]
        st.caption("Provenance: RISK_ENGINE (computed). Documents below are not inputs to this classification.")
        if rcx["status"] == "AVAILABLE":
            rec = rcx["record"]
            cols = st.columns(5)
            for col, (label, value) in zip(cols, risk_metrics(rec).items()):
                col.metric(label, value)
            st.caption(f"{rec['admin_unit_name']} | risk date {rec['risk_date']} ({rcx['lookup'].get('basis')}) | basis {rec.get('risk_basis')} | "
                       f"engine {rec['calculation_version']} | thresholds {rec.get('threshold_status')}")
            st.caption(score_caption(rec))
            sig = signal_summary(rec.get("signals"))
            sig["value"] = sig["value"].astype(str)                    # mixed numbers / "not observed" must not break Arrow conversion
            st.dataframe(sig, hide_index=True, use_container_width=True)
        else:
            st.info(f"NO_RISK_CONTEXT - {rcx.get('reason')}")

        # ---------------------------------------------------------------- ML forecast (a separate provenance; never a current risk status)
        st.subheader("ML Forecast (not a current risk status)")
        ml = body.get("ml_prediction")
        if ml:
            st.caption("Provenance: ML_MODEL. A forecast of an observed quantity at a future date; it does not change the risk classification above.")
            st.dataframe(ml_table(ml["predictions"]), hide_index=True, use_container_width=True)
            st.caption(ml_caption(ml) + " No calibrated probability or confidence interval is available.")
        else:
            reason = None
            if unit:
                res_ml = _client().ml_predictions(admin_unit_id=unit["id"])
                if res_ml.ok and res_ml.data and res_ml.data.get("predictions"):
                    reason = res_ml.data["predictions"][0].get("reason")
            st.info("INSUFFICIENT_DATA - no valid ML forecast exists for this area." + (f" {reason}" if reason else ""))

        # ---------------------------------------------------------------- documents
        st.subheader("Documentary Evidence")
        r = body.get("retrieval") or {}
        st.caption(f"Retrieval: {r.get('mode')} ({r.get('method')}) | filters applied {r.get('filters_applied')}"
                   + (f" | relaxed: {', '.join(r['filters_relaxed'])}" if r.get("filters_relaxed") else ""))
        cited = {c["chunk_id"] for c in body.get("citations") or [] if c.get("kind") == "documentary"}
        notice = relevance_notice(r)
        if notice:
            getattr(st, notice[0])(notice[1])
        if not body.get("documentary_evidence"):
            st.caption("No documentary evidence was retrieved.")
        if body.get("documentary_evidence"):
            st.dataframe(pd.DataFrame(evidence_rows(body.get("documentary_evidence"), cited)), hide_index=True, width="stretch")
            st.caption("Evidence that passed the relevance check. Passages that matched only loosely are withheld by the API and are never shown as evidence.")
        for e in body.get("documentary_evidence") or []:
            with st.expander(f"{'Cited · ' if e['chunk_id'] in cited else ''}{e.get('title') or '(untitled)'} - {e['chunk_id']}"):
                st.caption(evidence_caption(e))
                st.text(e.get("snippet") or "")

        # ---------------------------------------------------------------- explanation (only if a real model produced one)
        if status == "ANSWERED" and body.get("answer"):
            st.subheader("AI Explanation")
            st.markdown(body["answer"])
            m = body.get("model") or {}
            st.caption(f"Generated by {m.get('provider')} / {m.get('model')}. Statements marked [risk_engine] restate the computed context; "
                       "statements citing [chunk:...] are from the documents above.")
        g = body.get("groundedness") or {}
        for w in g.get("warnings") or []:
            st.warning(f"Number {w.get('number')} not found in the cited source: {w.get('sentence')}")
        if status == "INVALID_ANSWER":
            with st.expander("Why the explanation was withheld"):
                st.json(g.get("problems") or [])
        st.caption(body.get("disclaimer") or "")
