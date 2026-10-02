"""Per-domain coverage matrix computed from the Gold datasets (no assumptions)."""

from __future__ import annotations

from typing import Any

# domain -> (gold dataset key, date field, geography-resolved test)
_DOMAIN_DATE = {"rainfall": "date", "weather": "date", "gauge": "date", "air_quality": "date",
                "hazard_alert": "issued_at", "disaster_event": "event_date"}


def coverage_matrix(gold: dict[str, list[dict]]) -> dict[str, Any]:
    out = {}
    for domain, date_field in _DOMAIN_DATE.items():
        rows = gold.get(domain, [])
        resolved = [r for r in rows if r.get("resolution_status") == "resolved" and r.get("admin_unit_id")]
        dates = {str(r[date_field])[:10] for r in rows if r.get(date_field)}
        out[domain] = {
            "total_source_observations": len(rows), "resolved_observations": len(resolved),
            "unresolved_observations": len(rows) - len(resolved),
            "distinct_geographies_resolved": len({r["admin_unit_id"] for r in resolved}),
            "distinct_dates": len(dates), "date_min": min(dates) if dates else None,
            "date_max": max(dates) if dates else None,
            "resolved_pct": round(100 * len(resolved) / len(rows), 2) if rows else None,
        }
    res = gold.get("reservoir", [])
    out["reservoir"] = {"total_source_observations": len(res), "resolved_observations": 0,
                        "unresolved_observations": len(res), "note": "not geographically attributable to an admin unit"}
    return out
