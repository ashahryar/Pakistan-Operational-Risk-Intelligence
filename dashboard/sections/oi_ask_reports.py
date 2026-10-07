"""Operational Intelligence section (Task 40): the former 7_RAG_Ask.py page as a render() function. Logic unchanged."""



import pandas as pd
import streamlit as st

from dashboard.api_client import RiskApiClient
from dashboard.utils.api_cache import cached_api
from dashboard.utils.rag_helpers import FALLBACK_PROVINCES, MODES, SOURCES, citation_rows, evidence_caption, relevance_notice, status_banner



ALL = "All"


@st.cache_resource
def _client() -> RiskApiClient:
    return RiskApiClient()


@cached_api(ttl=300)
def _admin_units(base_url: str, level: int):
    return _client().admin_units(level=level)


def _province_names(base_url: str):
    res = _admin_units(base_url, 1)
    names = sorted(p["name"] for p in res.data) if res.ok and res.data else []
    return names or FALLBACK_PROVINCES



def render() -> None:
    st.subheader("💬 Ask the Reports")
    st.caption("Answers are generated only from retrieved NDMA / PDMA / PMD report passages and cite them. "
               "A summary of source reports — not an official warning and not a risk assessment.")

    base = _client().base_url
    with st.form("ask"):
        question = st.text_input("Your question", placeholder="e.g. How many people died in the floods reported by NDMA?")
        c1, c2, c3, c4 = st.columns(4)
        mode = c1.selectbox("Retrieval", list(MODES), format_func=MODES.get)
        province = c2.selectbox("Province", [ALL] + _province_names(base))
        source = c3.selectbox("Source", [ALL] + SOURCES)
        top_k = c4.slider("Evidence passages", 1, 10, 5)
        submitted = st.form_submit_button("Ask")

    if submitted:
        if len((question or "").strip()) < 2:
            st.warning("Please type a question (at least 2 characters).")
            st.stop()
        with st.spinner("Searching the reports…"):
            res = _client().ask(question.strip(), mode=mode, source=None if source == ALL else source,
                                province=None if province == ALL else province, top_k=top_k)
        body = res.data if isinstance(res.data, dict) and "answer_status" in res.data else None
        if body is None:                                    # transport failure, validation error, or retrieval unavailable
            st.error(f"Could not get an answer: {res.message}")
            if res.error_kind == "connection":
                st.caption("The question service is not reachable. Start the API with: docker compose up -d --build api "
                           "(or: uvicorn api.app.main:app --port 8000). Override the address with PORI_API_URL.")
            st.stop()

        status = body["answer_status"]
        level, message = status_banner(status)
        getattr(st, level)(f"**{status}** — {message}")
        if body.get("answer"):
            st.subheader("Answer")
            st.markdown(body["answer"])
        model = body.get("model") or {}
        r = body.get("retrieval") or {}
        st.caption(f"Retrieval: {r.get('mode')} ({r.get('method')}) · {r.get('evidence_count')} passages · "
                   f"Model: {model.get('provider') or 'not configured'}{' / ' + model['model'] if model.get('model') else ''}")
        notice = relevance_notice(r)
        if notice:
            getattr(st, notice[0])(notice[1])
        g = body.get("groundedness") or {}
        for w in g.get("warnings") or []:
            st.warning(f"Number {w.get('number')} does not appear in the cited text: “{w.get('sentence')}”")
        if status == "INVALID_ANSWER":
            with st.expander("Why the answer was withheld"):
                st.json(g.get("problems") or [])

        st.subheader("Citations")
        if body.get("citations"):
            st.dataframe(pd.DataFrame(citation_rows(body["citations"])), hide_index=True, use_container_width=True)
        else:
            st.caption("No cited passages (no answer was accepted).")

        st.subheader("Retrieved evidence")
        cited = {c["chunk_id"] for c in body.get("citations") or []}
        if not body.get("evidence"):
            st.caption("Nothing was retrieved.")
        for e in body.get("evidence") or []:
            label = f"{'✅ ' if e['chunk_id'] in cited else ''}{e.get('title') or '(untitled)'} — {e['chunk_id']}"
            with st.expander(label):
                st.caption(evidence_caption(e))
                st.text(e.get("snippet") or "")
        st.caption(body.get("disclaimer") or "")
