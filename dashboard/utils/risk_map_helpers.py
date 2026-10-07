"""dashboard/utils/risk_map_helpers.py

Task 27 -- pure transformation helpers for the geographic risk map (no Streamlit, no database, no HTTP). They reshape
what the FastAPI serving layer returns; they never calculate a risk score, never reinterpret a status and never invent
geometry. Directly unit-tested in tests/dashboard/test_risk_map_helpers.py.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import pandas as pd

# Status values come from the Task 23 engine (unchanged). NO_DATA is a display category for areas that have a boundary
# but no risk row in the selected scope -- it is not a risk status.
from dashboard.ui import tokens  # noqa: E402

STATUS_ORDER = ["CRITICAL", "HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA", "NO_SIGNAL"]
NO_DATA = "NO_RISK_DATA"
STATUS_COLORS = {k: tokens.status_fill(k) for k in STATUS_ORDER + [NO_DATA]}      # one status palette for the whole dashboard (dashboard/ui/tokens.py)
SCORE_UNAVAILABLE = "Unavailable (null — the engine computes no numeric score in v1.0.0)"
_PROP_KEYS = ["admin_unit_id", "admin_unit_name", "admin_level", "province", "risk_status", "risk_score", "risk_confidence",
              "risk_basis", "risk_date", "top_risk_domain", "data_coverage_pct", "calculation_version"]


def is_feature_collection(fc: Any) -> bool:
    return isinstance(fc, dict) and fc.get("type") == "FeatureCollection" and isinstance(fc.get("features"), list)


def feature_rows(fc: Any) -> pd.DataFrame:
    """One row per feature with its properties and a has_geometry flag. Missing properties become None (never defaulted)."""
    if not is_feature_collection(fc):
        return pd.DataFrame(columns=_PROP_KEYS + ["has_geometry"])
    rows = []
    for f in fc["features"]:
        props = f.get("properties") or {}
        r = {k: props.get(k) for k in _PROP_KEYS}
        if r["admin_unit_id"] is None:
            r["admin_unit_id"] = f.get("id")
        r["has_geometry"] = bool(f.get("geometry"))
        rows.append(r)
    return pd.DataFrame(rows, columns=_PROP_KEYS + ["has_geometry"])


def merge_risk_into_features(fc: dict, risk_rows: Iterable[dict]) -> dict:
    """Replace the risk properties of each feature with the rows of a chosen date (matched by admin_unit_id).
    A feature without a row on that date gets risk_status None (shown as NO_RISK_DATA); geometry is untouched."""
    by_id = {r["admin_unit_id"]: r for r in risk_rows}
    feats = []
    for f in fc.get("features", []):
        props = dict(f.get("properties") or {})
        uid = props.get("admin_unit_id", f.get("id"))
        r = by_id.get(uid)
        for k in ("risk_status", "risk_score", "risk_confidence", "risk_basis", "risk_date", "top_risk_domain",
                  "data_coverage_pct", "calculation_version"):
            props[k] = r.get(k) if r else None
        feats.append({**f, "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def mapped_geojson(fc: dict) -> dict:
    """Only features that actually have geometry (null-geometry features are kept elsewhere, never drawn)."""
    return {"type": "FeatureCollection", "features": [f for f in fc.get("features", []) if f.get("geometry")]}


def map_frame(fc: dict) -> pd.DataFrame:
    """Rows to draw: has geometry; status column is the risk status or NO_RISK_DATA."""
    df = feature_rows(mapped_geojson(fc))
    df["status"] = df["risk_status"].where(df["risk_status"].notna(), NO_DATA)
    return df


def unmapped_risk_frame(fc: dict, risk_rows: Optional[Iterable[dict]] = None) -> pd.DataFrame:
    """Risk records with NO mapped boundary geometry -- shown, never silently dropped. If risk_rows (a chosen date) is given,
    those rows are used and any whose unit has no drawn geometry is listed."""
    drawn = {f.get("properties", {}).get("admin_unit_id", f.get("id")) for f in fc.get("features", []) if f.get("geometry")}
    if risk_rows is None:
        df = feature_rows(fc)
        df = df[(~df["has_geometry"]) & df["risk_status"].notna()]
        return df.drop(columns=["has_geometry"]).reset_index(drop=True)
    rows = [{k: r.get(k) for k in _PROP_KEYS if k in r or k in ("risk_status",)} for r in risk_rows if r["admin_unit_id"] not in drawn]
    return pd.DataFrame(rows)


def summarize(fc: dict, risk_rows: Optional[Iterable[dict]] = None) -> dict:
    """Counts for the selected scope. Uses the API's actual statuses; calculates nothing new."""
    df = feature_rows(fc)
    risk_rows = list(risk_rows) if risk_rows is not None else None
    if risk_rows is not None:
        df = feature_rows(merge_risk_into_features(fc, risk_rows))
    with_risk = df["risk_status"].notna()
    counts = df.loc[with_risk, "risk_status"].value_counts().to_dict()
    unmapped = len(unmapped_risk_frame(fc, risk_rows))
    return {
        "total_areas": int(len(df)), "areas_with_risk": int(with_risk.sum()),
        "areas_without_geometry": int((~df["has_geometry"]).sum()),
        "risk_records_without_boundary": unmapped,
        "high": int(counts.get("HIGH", 0)), "critical": int(counts.get("CRITICAL", 0)),
        "insufficient_data": int(counts.get("INSUFFICIENT_DATA", 0)),
        "by_status": {s: int(counts.get(s, 0)) for s in STATUS_ORDER if counts.get(s, 0)},
        **score_coverage(df),
    }


def score_coverage(df: pd.DataFrame) -> dict:
    """Task 39: scored vs abstained areas. An area with a status but a null score is ABSTAINED (no defensible numeric aggregate),
    which is a different state from a low risk and from 'no data'."""
    has_status = df["risk_status"].notna()
    scored = int((has_status & df["risk_score"].notna()).sum()) if "risk_score" in df else 0
    return {"areas_scored": scored, "areas_score_abstained": int(has_status.sum()) - scored}


def risk_score_text(score: Optional[float]) -> str:
    """null stays unavailable; a numeric value (never produced by engine v1.0.0) is shown as-is."""
    return SCORE_UNAVAILABLE if score is None else f"{float(score):g}"


def signal_summary(signals: Optional[dict]) -> pd.DataFrame:
    """Signal name -> normalized value (None stays 'not observed', never 0)."""
    sig = signals or {}
    return pd.DataFrame([{"signal": k.replace("_", " "), "value": v if v is not None else "not observed"} for k, v in sig.items()],
                        columns=["signal", "value"])


def dates_from_rows(rows: Iterable[dict]) -> list[str]:
    return sorted({r["risk_date"] for r in rows if r.get("risk_date")}, reverse=True)


def filter_rows(rows: Iterable[dict], level: Optional[int] = None) -> list[dict]:
    return [r for r in rows if level is None or r.get("admin_level") == level]
