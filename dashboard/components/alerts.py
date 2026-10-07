import streamlit as st


def render_national_alert_center(summary) -> None:
    """Render the National Alert Center: the primary, detailed advisory card."""
    st.markdown("## 🚨 National Alert Center")

    alert = summary.get("latest_alert")

    if alert is None:

        st.info("""
### No advisory in the data

No PMD advisory is stored. This is not confirmation that no advisory is active.
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
