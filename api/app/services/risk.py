from __future__ import annotations

from api.app.db import fetch_all


def list_risk_records(limit: int = 200) -> list[dict]:
    """
    Returns rows from operational_risk. Real query against the real
    table -- not fabricated -- but that table is currently unpopulated
    (its only writer, scripts/risk_engine/risk_engine.py, is confirmed
    broken against this schema; docs/architecture/CODEBASE_AUDIT.md),
    so this is expected to return an empty list today. Fixing the
    loader is a separate, future task -- this endpoint's job is only
    to serve whatever is genuinely in the table, honestly.
    """
    query = """
        SELECT district, province, latitude, longitude,
               weather_risk, disaster_risk, overall_risk, risk_level, recommendation
        FROM operational_risk
        ORDER BY overall_risk DESC NULLS LAST
        LIMIT :limit
    """
    return fetch_all(query, {"limit": limit})
