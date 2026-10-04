"""Task 26 -- load data/analytics/risk/gold_operational_risk.jsonl into risk.operational_risk (serving copy).

No risk calculation happens here. One transaction: rows previously served but absent from this load are flagged
is_current = FALSE (never deleted), then every row of the file is upserted with is_current = TRUE, so reruns are idempotent.
A row whose admin_unit_id is not in geo.admin_unit makes the load fail loudly (nothing is dropped or guessed).

Usage: python scripts/risk/load_risk_serving.py [--database NAME]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

SOURCE = PROJECT_ROOT / "data" / "analytics" / "risk" / "gold_operational_risk.jsonl"
SCALARS = ["admin_unit_name", "admin_level", "province", "risk_status", "risk_basis", "risk_score", "risk_confidence",
           "rainfall_signal", "weather_signal", "gauge_signal", "air_quality_signal", "hazard_alert_signal",
           "disaster_event_signal", "active_signal_count", "observed_signal_count", "missing_signal_count", "top_risk_domain",
           "top_risk_contribution", "data_coverage_pct", "source_count", "source_record_count", "ml_forecast_available",
           "ml_reference_model", "ml_unavailable_reason", "calculation_version", "engine_version", "threshold_status"]


def read_rows(path: Path = SOURCE) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def to_params(r: dict) -> dict:
    p = {k: r.get(k) for k in SCALARS}
    p.update(admin_unit_id=r["admin_unit_id"], risk_date=r["date"],
             signal_states=json.dumps(r.get("signal_states"), sort_keys=True),
             business_signals=json.dumps(r.get("business_signals"), sort_keys=True))
    return p


def load(rows: list[dict], database: Optional[str] = None) -> dict:
    from scripts.database.apply_serving_migration import engine_for
    cols = ["admin_unit_id", "risk_date"] + SCALARS + ["signal_states", "business_signals"]
    marks = ", ".join(f"CAST(:{c} AS jsonb)" if c in ("signal_states", "business_signals") else f":{c}" for c in cols)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("admin_unit_id", "risk_date"))
    sql = text(f"INSERT INTO risk.operational_risk ({', '.join(cols)}, is_current) VALUES ({marks}, TRUE) "
               f"ON CONFLICT (admin_unit_id, risk_date) DO UPDATE SET {updates}, is_current = TRUE, loaded_at = now()")
    eng = engine_for(database)
    with eng.begin() as conn:
        flagged = conn.execute(text("UPDATE risk.operational_risk SET is_current = FALSE WHERE is_current")).rowcount
        params = [to_params(r) for r in rows]
        for i in range(0, len(params), 500):
            conn.execute(sql, params[i:i + 500])
        total = conn.execute(text("SELECT count(*) FROM risk.operational_risk WHERE is_current")).scalar_one()
    return {"rows_in_file": len(rows), "current_rows_after_load": total, "previously_current_flagged_before_upsert": flagged}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    print(json.dumps(load(read_rows(), a.database), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
