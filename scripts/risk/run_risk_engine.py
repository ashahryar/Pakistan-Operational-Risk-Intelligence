"""Task 23 -- run the operational risk engine against the REAL local Gold datasets.

Reads data/analytics/gold/datasets/*.jsonl (run scripts/gold/run_gold.py first). The only
database access is a single READ-ONLY lookup of geo.admin_unit (name/level/parent) for labelling;
without a database the rows are still produced, with null names. Nothing is written to PostgreSQL.

Writes (data/analytics/risk/):
  gold_operational_risk.jsonl        full rows (gitignored -- regenerable)
  risk_explanations.jsonl            per-row machine-readable explanations (gitignored)
  unresolved_signals.jsonl           observations whose geography is NOT resolved, preserved unmapped
  reservoir_context.json             reservoir signals kept separate (not attributable to an admin unit)
  risk_coverage_matrix.json, risk_run_summary.json   (tracked)

Usage: python scripts/risk/run_risk_engine.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.risk.config import load_config  # noqa: E402
from pipeline.risk.engine import run_engine  # noqa: E402

GOLD = PROJECT_ROOT / "data" / "analytics" / "gold" / "datasets"
OUT = PROJECT_ROOT / "data" / "analytics" / "risk"
FILES = {"rainfall": "gold_rainfall_daily", "weather": "gold_weather_daily", "gauge": "gold_gauge_daily",
         "air_quality": "gold_air_quality", "hazard_alert": "gold_hazard_alerts",
         "disaster_event": "gold_disaster_events", "reservoir": "gold_reservoir_status"}
ML_VERSION_DIR = PROJECT_ROOT / "data" / "models" / "gauge_discharge_forecast" / "2026-10-01-task22-daily"


def _read(name: str) -> list[dict]:
    path = GOLD / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def _unit_info() -> dict[int, dict]:
    try:
        from sqlalchemy import text

        from config.database import engine
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, level, name, parent_id FROM geo.admin_unit")).fetchall()
    except Exception:
        return {}
    by_id = {r[0]: r for r in rows}
    info = {}
    for uid, level, name, parent in rows:
        province = name if level == 1 else (by_id[parent][2] if parent in by_id and by_id[parent][1] == 1 else None)
        info[uid] = {"name": name, "level": level, "province": province}
    return info


def _caveated(info: dict[int, dict]) -> set[int]:
    from scripts.geo.canonical_data import DISTRICTS
    names = {d["name"] for d in DISTRICTS if d.get("caveat")}
    return {uid for uid, i in info.items() if i["level"] == 2 and i["name"] in names}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main() -> dict:
    cfg = load_config()
    gold = {k: _read(v) for k, v in FILES.items()}
    info = _unit_info()
    predictions, qualifying = [], set()
    if (ML_VERSION_DIR / "predictions.json").exists():
        predictions = json.loads((ML_VERSION_DIR / "predictions.json").read_text(encoding="utf-8"))
        qualifying = set(json.loads((ML_VERSION_DIR / "metadata.json").read_text(encoding="utf-8")).get("qualifying_stations", []))
    result = run_engine(gold, cfg, info, _caveated(info), predictions, qualifying)

    OUT.mkdir(parents=True, exist_ok=True)
    _write_jsonl(OUT / "gold_operational_risk.jsonl", result["rows"])
    _write_jsonl(OUT / "risk_explanations.jsonl", result["explanations"])
    _write_jsonl(OUT / "unresolved_signals.jsonl", result["unresolved"])
    (OUT / "reservoir_context.json").write_text(json.dumps(result["reservoir_context"], indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "risk_coverage_matrix.json").write_text(json.dumps(result["coverage"], indent=2, sort_keys=True), encoding="utf-8")

    rows = result["rows"]
    dates = sorted({r["date"] for r in rows})
    summary = {
        "calculation_version": result["calculation_version"], "threshold_status": cfg["threshold_status"],
        "risk_rows": len(rows), "distinct_admin_units": len({r["admin_unit_id"] for r in rows}),
        "date_min": dates[0] if dates else None, "date_max": dates[-1] if dates else None,
        "risk_status_distribution": dict(sorted(Counter(r["risk_status"] for r in rows).items())),
        "risk_basis_distribution": dict(sorted(Counter(r["risk_basis"] for r in rows).items())),
        "risk_confidence_distribution": dict(sorted(Counter(r["risk_confidence"] for r in rows).items())),
        "rows_with_risk_score": sum(1 for r in rows if r["risk_score"] is not None),
        "rows_with_ml_forecast": sum(1 for r in rows if r["ml_forecast_available"]),
        "ml_unavailable_reasons": dict(Counter(r["ml_unavailable_reason"] for r in rows)),
        "signal_state_counts": {d: dict(Counter(r["signal_states"][d] for r in rows)) for d in
                                sorted({d for r in rows for d in r["signal_states"]})},
        "unresolved_signal_records": len(result["unresolved"]),
        "unresolved_by_domain": dict(Counter(u["domain"] for u in result["unresolved"])),
        "admin_unit_labels_from_db": bool(info),
    }
    (OUT / "risk_run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
