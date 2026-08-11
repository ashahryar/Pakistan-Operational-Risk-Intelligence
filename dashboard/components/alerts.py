import streamlit as st


def render_platform_health(summary) -> None:
    """Render the Overall Platform Health progress bar + status banner."""
    st.markdown("## ❤️ Overall Platform Health")

    health = 100

    if summary.get("last_update") is None:
        health = 60

    st.progress(health/100)

    left,right = st.columns([4,1])

    with left:

        if health>=95:

            st.success("🟢 All core services are operational and receiving live government data.")

        elif health>=80:

            st.warning("🟡 Platform operational with minor issues.")

        else:

            st.error("🔴 Platform health degraded.")

    with right:

        st.metric(
            "Health",
            f"{health}%"
        )

    st.divider()


def render_national_alert_center(summary) -> None:
    """Render the National Alert Center: the primary, detailed advisory card."""
    st.markdown("## 🚨 National Alert Center")

    alert = summary.get("latest_alert")

    if alert is None:

        st.success("""
### ✅ No Active National Alert

No emergency advisory is currently active.
""")

    else:

        severity = str(
            alert.get("severity","")
        ).lower()

        title = alert.get(
            "alert_type",
            "Weather Advisory"
        )

        forecast = str(
            alert.get("forecast","") or ""
        )

        issued = alert.get("scraped_at")

        if hasattr(issued, "strftime"):
            issued_str = issued.strftime("%d %b %Y, %I:%M %p")
        elif issued is not None:
            issued_str = str(issued)
        else:
            issued_str = "N/A"

        if severity=="high":

            card_class="alert-card-high"
            chip_class="status-chip-high"
            icon="🔴"
            text="HIGH"

        elif severity=="medium":

            card_class="alert-card-medium"
            chip_class="status-chip-medium"
            icon="🟡"
            text="MEDIUM"

        else:

            card_class="alert-card-low"
            chip_class="status-chip-low"
            icon="🟢"
            text="LOW"

        # Short summary shown on the card itself -- capped at 280 characters,
        # the complete text is always available below in "Read Full Advisory".
        summary_limit = 280

        short_summary = forecast[:summary_limit].rstrip()

        if len(forecast) > summary_limit:
            short_summary += "…"

        st.markdown(f"""
<div class="alert-card {card_class}">

<span class="status-chip {chip_class}">{icon} {text} PRIORITY</span>

<div class="alert-card-title">{title}</div>

<div class="alert-card-meta">Issued: {issued_str}</div>

<div class="alert-card-summary">{short_summary}</div>

</div>
""", unsafe_allow_html=True)

        # Affected districts / provinces, if the alert record provides them --
        # shown as chips instead of buried inside a paragraph.
        affected_areas = alert.get("districts") if hasattr(alert, "get") else None

        if not affected_areas:
            affected_areas = alert.get("affected_areas") if hasattr(alert, "get") else None

        if affected_areas:

            if isinstance(affected_areas, str):
                area_list = [a.strip() for a in affected_areas.split(",") if a.strip()]
            else:
                area_list = list(affected_areas)

            st.caption("Affected Districts / Provinces")

            chips_html = "".join(
                f'<span class="status-chip">{area}</span>' for area in area_list
            )

            st.markdown(chips_html, unsafe_allow_html=True)

        if forecast:

            with st.expander("Read Full Advisory"):

                st.write(forecast)

    st.divider()


def render_platform_health_compact(summary) -> None:
    """Render the compact Overall Platform Health subheader + status line."""
    st.subheader("🏥 Overall Platform Health")

    health_score = 100

    if summary.get("last_update") is None:

        health_score = 60

    st.progress(health_score / 100)

    if health_score >= 95:

        st.success("🟢 Overall Platform Status : Excellent")

    elif health_score >= 80:

        st.warning("🟡 Overall Platform Status : Good")

    else:

        st.error("🔴 Overall Platform Status : Needs Attention")

    st.divider()


def render_executive_alert_center(summary) -> None:
    """Render the compact Executive Alert Center: an at-a-glance status strip.

    Deliberately distinct from render_national_alert_center() above -- this
    is a quick-glance summary (severity + type only) for an executive
    scanning the page, not a repeat of the full advisory text.
    """
    st.subheader("🚨 Executive Alert Center")

    alert = summary.get("latest_alert")

    if alert is not None:

        severity = str(alert.get("severity", "")).lower()

        if severity == "high":
            chip_class, icon, label = "status-chip-high", "🔴", "HIGH RISK"

        elif severity == "medium":
            chip_class, icon, label = "status-chip-medium", "🟡", "MEDIUM RISK"

        else:
            chip_class, icon, label = "status-chip-low", "🟢", "NORMAL"

        alert_type = alert.get("alert_type", "N/A")

        st.markdown(
            f"""
<div class="exec-alert-strip">

<span class="status-chip {chip_class}">{icon} {label}</span>

<div>

<div class="exec-alert-label">Active Advisory Type</div>

<div class="exec-alert-title">{alert_type}</div>

</div>

</div>
""",
            unsafe_allow_html=True,
        )

    else:

        st.success("✅ No active alerts reported.")

    st.divider()


def render_live_system_status() -> None:
    """Render the Live Dashboard Status metric strip."""
    st.subheader("📡 Live Dashboard Status")

    s1, s2, s3, s4 = st.columns(4)

    with s1:

        st.metric(
            "Government Sources",
            "3",
        )

    with s2:

        st.metric(
            "Database",
            "Online",
        )

    with s3:

        st.metric(
            "Auto Refresh",
            "60 sec",
        )

    with s4:

        st.metric(
            "Dashboard",
            "LIVE",
        )

    st.divider()

def render_alerts(summary):
    """
    Render complete alerts section.
    """

    render_national_alert_center(summary)

    render_platform_health(summary)

    render_live_system_status()