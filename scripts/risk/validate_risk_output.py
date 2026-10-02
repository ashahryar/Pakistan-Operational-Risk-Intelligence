"""Task 23 -- validate data/analytics/risk/gold_operational_risk.jsonl structurally and semantically.
Exit code 1 on any failure. Usage: python scripts/risk/validate_risk_output.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.risk.config import load_config  # noqa: E402
from pipeline.risk.contracts import RISK_BASES, RISK_STATES  # noqa: E402

OUT = PROJECT_ROOT / "data" / "analytics" / "risk"
REQUIRED = ("admin_unit_id", "date", "risk_status", "risk_basis", "risk_score", "risk_confidence", "signal_states",
            "active_signal_count", "observed_signal_count", "missing_signal_count", "data_coverage_pct",
            "calculation_version", "engine_version", "ml_forecast_available", "ml_reference_model")


def _read(name: str) -> list[dict]:
    path = OUT / name
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def validate() -> dict:
    cfg = load_config()
    rows, expl, unresolved = _read("gold_operational_risk.jsonl"), _read("risk_explanations.jsonl"), _read("unresolved_signals.jsonl")
    failures: list[str] = []
    if not rows:
        failures.append("no risk rows found")
    keys = [(r["admin_unit_id"], r["date"]) for r in rows]
    if len(keys) != len(set(keys)):
        failures.append("duplicate (admin_unit_id, date) keys")
    for r in rows:
        miss = [f for f in REQUIRED if f not in r]
        if miss:
            failures.append(f"{r.get('admin_unit_id')}/{r.get('date')}: missing fields {miss}")
            continue
        if r["risk_status"] not in RISK_STATES or r["risk_basis"] not in RISK_BASES:
            failures.append(f"invalid status/basis on {r['admin_unit_id']}/{r['date']}")
        if r["calculation_version"] != cfg["calculation_version"]:
            failures.append("calculation_version does not match config")
        if r["risk_score"] is not None and not cfg["score"]["enabled"]:
            failures.append("risk_score populated while score.enabled is false")
        if r["risk_status"] in ("NO_SIGNAL", "INSUFFICIENT_DATA") and (r["risk_score"] is not None or r["top_risk_domain"]):
            failures.append(f"insufficient cell reports a score/top driver: {r['admin_unit_id']}/{r['date']}")
        if r["ml_forecast_available"] and r["ml_reference_model"] != "persistence":
            failures.append("persistence must remain the ML reference model")
    by_key = {(e["admin_unit_id"], e["date"]): e for e in expl}
    for r in rows:
        e = by_key.get((r["admin_unit_id"], r["date"]))
        if e is None:
            failures.append(f"missing explanation for {r['admin_unit_id']}/{r['date']}")
        elif e["risk_status"] != r["risk_status"] or {d["domain"] for d in e["drivers"]} != \
                {d for d, s in r["signal_states"].items() if s != "MISSING"}:
            failures.append(f"explanation does not match row {r['admin_unit_id']}/{r['date']}")
    if any(u.get("admin_unit_id") for u in unresolved):
        failures.append("an unresolved signal record carries an admin_unit_id")
    report = {"rows_checked": len(rows), "explanations_checked": len(expl), "unresolved_records": len(unresolved),
              "failures": failures, "passed": not failures}
    (OUT / "risk_validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = validate()
    print(json.dumps({k: v for k, v in result.items() if k != "failures"} | {"failure_count": len(result["failures"]),
                                                                              "first_failures": result["failures"][:5]}, indent=2))
    sys.exit(0 if result["passed"] else 1)
