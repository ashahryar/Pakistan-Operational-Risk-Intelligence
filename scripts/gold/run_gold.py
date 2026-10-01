"""Task 21 -- run the Gold transformations against the REAL canonical JSONL output already on
disk (produced by scripts/parsing/run_task17_canonical.py and scripts/parsing/tier1/run_tier1.py
-- run those first if data/parsed/canonical/ is empty).

Reads data/parsed/canonical/<domain>/*.jsonl (read-only). Writes:
  data/analytics/gold/datasets/<dataset>.jsonl        (full Gold rows, gitignored -- large)
  data/analytics/gold/gold_validation_summary.json     (per-dataset counts, tracked)
  data/analytics/gold/gold_quality_report.json         (geography/null/timestamp findings, tracked)
  data/analytics/gold/gold_coverage_summary.json        (operational-risk-input coverage, tracked)

No pyspark required -- pure Python throughout (pipeline/gold/transforms.py).

Usage: python scripts/gold/run_gold.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.canonical.output import write_jsonl  # noqa: E402
from pipeline.gold import transforms as gt  # noqa: E402
from pipeline.gold.domain_registry import GOLD_REGISTRY  # noqa: E402

CANONICAL_ROOT = PROJECT_ROOT / "data" / "parsed" / "canonical"
GOLD_ROOT = PROJECT_ROOT / "data" / "analytics" / "gold"


def _read_domain(domain: str) -> list[dict]:
    domain_dir = CANONICAL_ROOT / domain
    if not domain_dir.exists():
        return []
    records = []
    for f in sorted(domain_dir.glob("*.jsonl")):
        if f.name.startswith("_"):
            continue
        records.extend(json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
    return records


def _quality(dataset: str, input_count: int, output: list[dict], geo_field: str | None) -> dict:
    missing_important = Counter()
    required = GOLD_REGISTRY[dataset].required_fields
    for row in output:
        for field in required:
            if row.get(field) in (None, ""):
                missing_important[field] += 1
    geo_counts = Counter(row.get("resolution_status") for row in output) if geo_field else {}
    keys = [tuple(row.get(k) for k in GOLD_REGISTRY[dataset].business_key) for row in output]
    duplicate_keys = len(keys) - len(set(keys))
    return {"input_records": input_count, "output_records": len(output),
           "duplicate_business_keys": duplicate_keys,
           "missing_required_fields": dict(missing_important),
           "geography": dict(sorted(geo_counts.items())) if geo_field else "not_applicable"}


def run():
    silver = {d: _read_domain(d) for d in ("weather_observation", "rainfall_observation", "gauge_observation",
                                           "air_quality_observation", "disaster_event", "hazard_alert",
                                           "reservoir_observation", "document")}

    datasets = {
        "gold_weather_daily": gt.build_gold_weather_daily(silver["weather_observation"]),
        "gold_rainfall_daily": gt.build_gold_rainfall_daily(silver["rainfall_observation"]),
        "gold_gauge_daily": gt.build_gold_gauge_daily(silver["gauge_observation"]),
        "gold_air_quality": gt.build_gold_air_quality(silver["air_quality_observation"]),
        "gold_disaster_events": gt.build_gold_disaster_events(silver["disaster_event"]),
        "gold_hazard_alerts": gt.build_gold_hazard_alerts(silver["hazard_alert"]),
        "gold_reservoir_status": gt.build_gold_reservoir_status(silver["reservoir_observation"]),
        "gold_documents": gt.build_gold_documents(silver["document"]),
    }
    datasets["gold_operational_risk_inputs"] = gt.build_gold_operational_risk_inputs(
        rainfall=silver["rainfall_observation"], gauge=silver["gauge_observation"],
        aqi=silver["air_quality_observation"], weather=silver["weather_observation"],
        hazard_alerts=silver["hazard_alert"], disaster_events=silver["disaster_event"],
    )

    input_counts = {
        "gold_weather_daily": len(silver["weather_observation"]), "gold_rainfall_daily": len(silver["rainfall_observation"]),
        "gold_gauge_daily": len(silver["gauge_observation"]), "gold_air_quality": len(silver["air_quality_observation"]),
        "gold_disaster_events": len(silver["disaster_event"]), "gold_hazard_alerts": len(silver["hazard_alert"]),
        "gold_reservoir_status": len(silver["reservoir_observation"]), "gold_documents": len(silver["document"]),
        "gold_operational_risk_inputs": sum(len(silver[d]) for d in
            ("rainfall_observation", "gauge_observation", "air_quality_observation", "weather_observation",
             "hazard_alert", "disaster_event")),
    }

    geo_applicable = {"gold_weather_daily": True, "gold_rainfall_daily": True, "gold_gauge_daily": True,
                      "gold_air_quality": True, "gold_disaster_events": True, "gold_hazard_alerts": True,
                      "gold_reservoir_status": False, "gold_documents": False, "gold_operational_risk_inputs": False}

    validation_summary, quality_report = {}, {}
    for name, rows in datasets.items():
        validation_summary[name] = {"input_records": input_counts[name], "output_records": len(rows),
                                    "business_key": list(GOLD_REGISTRY[name].business_key)}
        quality_report[name] = _quality(name, input_counts[name], rows, geo_applicable[name])

    coverage_cells = datasets["gold_operational_risk_inputs"]
    coverage_summary = {
        "total_geography_date_cells": len(coverage_cells),
        "cells_with_any_signal": sum(1 for c in coverage_cells if c["coverage"]),
        "signal_coverage_counts": {signal: sum(1 for c in coverage_cells if c["coverage"].get(signal))
                                   for signal in ("rainfall_observation", "gauge_observation",
                                                 "air_quality_observation", "weather_observation",
                                                 "hazard_alert", "disaster_event")},
        "note": "coverage counts how many (admin_unit_id, date) cells have a value for each signal; "
               "a cell/signal absent from this count is NULL in gold_operational_risk_inputs, never zero",
        "no_risk_score_computed": True,
    }

    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    datasets_dir = GOLD_ROOT / "datasets"
    for name, rows in datasets.items():
        write_jsonl(rows, datasets_dir / f"{name}.jsonl")
    for filename, payload in (("gold_validation_summary.json", validation_summary),
                              ("gold_quality_report.json", quality_report),
                              ("gold_coverage_summary.json", coverage_summary)):
        (GOLD_ROOT / filename).write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    return validation_summary, quality_report, coverage_summary


if __name__ == "__main__":
    v, q, c = run()
    print(json.dumps({"validation": v, "coverage": c}, indent=2, sort_keys=True))
