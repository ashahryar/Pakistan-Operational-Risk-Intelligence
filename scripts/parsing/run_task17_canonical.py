"""Task 20 -- run the existing Task 17 canonical adapters over the REAL parsed NDMA/PDMA/PMD
output already on disk under data/parsed/{ndma,pdma,pmd}/, and write canonical JSONL next to the
Tier-1 output at data/parsed/canonical/<domain>/task17_<source>.jsonl.

This did not previously exist: Task 17's own tests only ever exercised the adapters against
small in-memory literal dicts, never against the real parsed files. Running it here is what
Task 20 Step 8 ("use the actual Task 17 + Task 19 canonical outputs") requires, and is what
surfaced a real field-name mismatch in adapt_pmd_daily() (fixed in pipeline/canonical/adapters.py
in this same task: real scripts/parsing/pmd/daily_parser.py output uses "temperature", not
"max_temperature").

Nothing under data/parsed/{ndma,pdma,pmd}/ (Task 5-11 output) is written -- read-only. Output is
deterministic: ingestion_timestamp for the PMD batches is derived from the records' own latest
`scraped_at` (not wall-clock), so re-running produces byte-identical JSONL.

Usage: python scripts/parsing/run_task17_canonical.py [--no-db]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.canonical.adapters import (  # noqa: E402
    adapt_ndma, adapt_pdma_gauge, adapt_pdma_rainfall, adapt_pmd_alerts, adapt_pmd_daily, adapt_pmd_weekly,
)
from pipeline.canonical.normalization import normalize_timestamp  # noqa: E402
from pipeline.canonical.output import write_jsonl  # noqa: E402

CANONICAL_ROOT = PROJECT_ROOT / "data" / "parsed" / "canonical"
QUARANTINE_PATH = PROJECT_ROOT / "data" / "parsed" / "canonical" / "_task17_quarantine.jsonl"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _batch_ingestion_timestamp(records: list[dict]) -> str:
    """Deterministic: the latest `scraped_at` among the batch's own records, not wall-clock."""
    stamps = sorted((normalize_timestamp(r.get("scraped_at")) for r in records if r.get("scraped_at")), reverse=True)
    return stamps[0] if stamps else "unknown"


def run(parsed_root: Path, admin_unit_lookup=None):
    quarantine_rows: list[dict] = []

    def sink(**kwargs):
        quarantine_rows.append({k: kwargs.get(k) for k in
                                ("source", "domain", "source_document", "reason_code", "message", "parser_version")})
        return True

    results = {}

    # ---- NDMA sitreps -> disaster_event
    ndma_files = sorted((parsed_root / "ndma" / "sitreps").glob("*.json"))
    ndma_canon = []
    for f in ndma_files:
        ndma_canon.extend(adapt_ndma(_load(f), quarantine=sink, admin_unit_lookup=admin_unit_lookup))
    results["ndma_sitreps"] = {"raw_files": len(ndma_files), "canonical_records": len(ndma_canon), "domain": "disaster_event"}

    # ---- PDMA rainfall -> rainfall_observation
    rain_files = sorted((parsed_root / "pdma" / "rainfall").glob("*/*.json"))
    rain_canon = []
    for f in rain_files:
        rain_canon.extend(adapt_pdma_rainfall(_load(f), quarantine=sink, admin_unit_lookup=admin_unit_lookup))
    results["pdma_rainfall"] = {"raw_files": len(rain_files), "canonical_records": len(rain_canon), "domain": "rainfall_observation"}

    # ---- PDMA gauge -> gauge_observation
    gauge_files = sorted((parsed_root / "pdma" / "gauge").glob("*/*.json"))
    gauge_canon = []
    for f in gauge_files:
        gauge_canon.extend(adapt_pdma_gauge(_load(f), quarantine=sink, admin_unit_lookup=admin_unit_lookup))
    results["pdma_gauge"] = {"raw_files": len(gauge_files), "canonical_records": len(gauge_canon), "domain": "gauge_observation"}

    # ---- PMD daily forecast -> weather_observation
    daily_path = parsed_root / "pmd" / "daily_forecast" / "latest.json"
    daily_records = _load(daily_path) if daily_path.exists() else []
    daily_canon = adapt_pmd_daily(daily_records, ingestion_timestamp=_batch_ingestion_timestamp(daily_records),
                                  quarantine=sink, admin_unit_lookup=admin_unit_lookup) if daily_records else []
    results["pmd_daily_forecast"] = {"raw_files": 1 if daily_path.exists() else 0, "canonical_records": len(daily_canon),
                                     "domain": "weather_observation"}

    # ---- PMD weekly outlook -> hazard_alert
    weekly_path = parsed_root / "pmd" / "weekly_outlook" / "latest.json"
    weekly_records = _load(weekly_path) if weekly_path.exists() else []
    weekly_canon = adapt_pmd_weekly(weekly_records, ingestion_timestamp=_batch_ingestion_timestamp(weekly_records),
                                    quarantine=sink, admin_unit_lookup=admin_unit_lookup) if weekly_records else []
    results["pmd_weekly_outlook"] = {"raw_files": 1 if weekly_path.exists() else 0, "canonical_records": len(weekly_canon),
                                     "domain": "hazard_alert"}

    # ---- PMD weather alerts -> hazard_alert
    alerts_path = parsed_root / "pmd" / "weather_alerts" / "latest.json"
    alerts_record = _load(alerts_path) if alerts_path.exists() else None
    alerts_canon = adapt_pmd_alerts(alerts_record, ingestion_timestamp=_batch_ingestion_timestamp([alerts_record]) if alerts_record else "unknown",
                                    quarantine=sink, admin_unit_lookup=admin_unit_lookup) if alerts_record else []
    results["pmd_weather_alerts"] = {"raw_files": 1 if alerts_path.exists() else 0, "canonical_records": len(alerts_canon),
                                     "domain": "hazard_alert"}

    canonical = {
        "disaster_event/task17_ndma.jsonl": ndma_canon,
        "rainfall_observation/task17_pdma.jsonl": rain_canon,
        "gauge_observation/task17_pdma.jsonl": gauge_canon,
        "weather_observation/task17_pmd.jsonl": daily_canon,
        "hazard_alert/task17_pmd_weekly.jsonl": weekly_canon,
        "hazard_alert/task17_pmd_alerts.jsonl": alerts_canon,
    }
    return results, canonical, quarantine_rows


def write_outputs(results, canonical, quarantine_rows, canonical_root: Path = CANONICAL_ROOT):
    for rel_path, records in sorted(canonical.items()):
        write_jsonl(records, canonical_root / rel_path)
    QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE_PATH.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
                                       for r in sorted(quarantine_rows, key=lambda r: (r["source"], r["reason_code"]))),
                               encoding="utf-8")
    return {"datasets": results, "records_quarantined_total": len(quarantine_rows)}


def _try_db_lookup():
    try:
        from sqlalchemy import text

        from config.database import engine
        from pipeline.canonical.geography import build_db_admin_unit_lookup
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return build_db_admin_unit_lookup(engine)
    except Exception:
        return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    lookup = None if "--no-db" in argv else _try_db_lookup()
    results, canonical, quarantine_rows = run(PROJECT_ROOT / "data" / "parsed", admin_unit_lookup=lookup)
    report = write_outputs(results, canonical, quarantine_rows)
    print(json.dumps({"admin_unit_lookup": "postgres(read-only)" if lookup else "none", **report}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
