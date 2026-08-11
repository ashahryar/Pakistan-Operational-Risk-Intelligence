from datetime import datetime

import streamlit as st


def render_header(last_update) -> None:
    """
    Renders the hero row: title + subtitle + live badge on the left,
    Platform Health card on the right.
    """

    left, right = st.columns([5, 2])

    with left:

        st.markdown(
            f"""
<div class='main-title'>Executive Command Dashboard</div>
<div class='subtitle'>
Operational Intelligence Ecosystem
<span class="live-badge">
<span class="dot"></span>
LIVE &nbsp;•&nbsp; {datetime.now().strftime("%d %b %Y %I:%M %p")}
</span>
</div>
""",
            unsafe_allow_html=True,
        )

    with right:

        st.markdown(
            """
<div class='status-card'>
<div class="status-card-title">🟢 Platform Health</div>
<div class="status-card-row"><span class="dot dot-green"></span>Pipeline Running</div>
<div class="status-card-row"><span class="dot dot-green"></span>Database Connected</div>
<div class="status-card-row"><span class="dot dot-green"></span>Dashboard Live</div>
</div>
""",
            unsafe_allow_html=True,
        )

    st.divider()