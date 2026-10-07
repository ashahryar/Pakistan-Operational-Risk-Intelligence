"""Task 26 -- read-only queries over the risk serving layer (risk.operational_risk, risk.latest_operational_risk,
geo.operational_risk_map). No risk is calculated here; values are served exactly as the Task 23 engine produced them."""

from __future__ import annotations

from datetime import date
from typing import Optional

from api.app.db import fetch_all
from pipeline.risk.scoring_v2 import SERVING_CONFIG, abstain_from_stored_row

_COLS = """admin_unit_id, admin_unit_name, admin_level, province, risk_date, risk_status, risk_basis, risk_score,
           risk_confidence, rainfall_signal, weather_signal, gauge_signal, air_quality_signal, hazard_alert_signal,
           disaster_event_signal, active_signal_count, observed_signal_count, missing_signal_count, top_risk_domain,
           top_risk_contribution, data_coverage_pct, source_count, source_record_count, calculation_version, threshold_status"""

_FILTER = """
    WHERE (CAST(:admin_unit_id AS int) IS NULL OR admin_unit_id = :admin_unit_id)
      AND (CAST(:province AS text) IS NULL OR lower(province) = lower(:province))
      AND (CAST(:risk_status AS text) IS NULL OR risk_status = :risk_status)
"""


def _num(v):
    return None if v is None else float(v)


def _shape(r: dict) -> dict:
    row = {
        "admin_unit_id": r["admin_unit_id"], "admin_unit_name": r["admin_unit_name"], "admin_level": r["admin_level"],
        "province": r["province"], "risk_date": r["risk_date"].isoformat(), "risk_status": r["risk_status"],
        "risk_basis": r["risk_basis"], "risk_score": _num(r["risk_score"]), "risk_confidence": r["risk_confidence"],
        "signals": {"rainfall": r["rainfall_signal"], "weather": r["weather_signal"], "gauge": r["gauge_signal"],
                    "air_quality": r["air_quality_signal"], "hazard_alert": r["hazard_alert_signal"],
                    "disaster_event": r["disaster_event_signal"]},
        "active_signal_count": r["active_signal_count"], "observed_signal_count": r["observed_signal_count"],
        "missing_signal_count": r["missing_signal_count"], "top_risk_domain": r["top_risk_domain"],
        "top_risk_contribution": r["top_risk_contribution"], "data_coverage_pct": _num(r["data_coverage_pct"]),
        "source_count": r["source_count"], "source_record_count": r["source_record_count"],
        "calculation_version": r["calculation_version"], "threshold_status": r["threshold_status"],
    }
    row["score_v2"] = abstain_from_stored_row({"risk_score": row["risk_score"], "signals": row["signals"]}, SERVING_CONFIG)
    return row


def list_risk(risk_date: Optional[date], province: Optional[str], admin_unit_id: Optional[int], risk_status: Optional[str],
              limit: int, offset: int) -> list[dict]:
    query = f"""SELECT {_COLS} FROM risk.operational_risk
        {_FILTER} AND is_current AND (CAST(:risk_date AS date) IS NULL OR risk_date = :risk_date)
        ORDER BY risk_date DESC, admin_unit_id LIMIT :limit OFFSET :offset"""
    rows = fetch_all(query, {"risk_date": risk_date, "province": province, "admin_unit_id": admin_unit_id,
                             "risk_status": risk_status, "limit": limit, "offset": offset})
    return [_shape(r) for r in rows]


def list_latest_risk(province: Optional[str], admin_unit_id: Optional[int], risk_status: Optional[str], limit: int) -> list[dict]:
    query = f"""SELECT {_COLS} FROM risk.latest_operational_risk {_FILTER} ORDER BY admin_unit_id LIMIT :limit"""
    rows = fetch_all(query, {"province": province, "admin_unit_id": admin_unit_id, "risk_status": risk_status, "limit": limit})
    return [_shape(r) for r in rows]


def risk_map_rows(level: Optional[int], province: Optional[str], risk_status: Optional[str], only_with_risk: bool,
                  include_geometry: bool) -> list[dict]:
    geom = "geometry" if include_geometry else "NULL::jsonb AS geometry"
    query = f"""SELECT admin_unit_id, admin_unit_name, admin_level, province, {geom}, risk_date, risk_status, risk_score,
                       risk_confidence, risk_basis, top_risk_domain, data_coverage_pct, calculation_version
        FROM geo.operational_risk_map
        WHERE (CAST(:level AS int) IS NULL OR admin_level = :level)
          AND (CAST(:province AS text) IS NULL OR lower(province) = lower(:province))
          AND (CAST(:risk_status AS text) IS NULL OR risk_status = :risk_status)
          AND (NOT :only_with_risk OR risk_status IS NOT NULL)
          AND (risk_status IS NOT NULL OR geometry IS NOT NULL)
        ORDER BY admin_level, admin_unit_id"""
    return fetch_all(query, {"level": level, "province": province, "risk_status": risk_status, "only_with_risk": only_with_risk})


def to_feature_collection(rows: list[dict]) -> dict:
    """Standard GeoJSON FeatureCollection. NULL geometry stays null; NULL risk_score stays null."""
    feats = []
    for r in rows:
        feats.append({
            "type": "Feature", "id": r["admin_unit_id"], "geometry": r["geometry"],
            "properties": {
                "admin_unit_id": r["admin_unit_id"], "admin_unit_name": r["admin_unit_name"], "admin_level": r["admin_level"],
                "province": r["province"], "risk_status": r["risk_status"], "risk_score": _num(r["risk_score"]),
                "risk_confidence": r["risk_confidence"], "risk_basis": r["risk_basis"],
                "risk_date": r["risk_date"].isoformat() if r["risk_date"] else None, "top_risk_domain": r["top_risk_domain"],
                "data_coverage_pct": _num(r["data_coverage_pct"]), "calculation_version": r["calculation_version"],
            }})
    return {"type": "FeatureCollection", "features": feats}
