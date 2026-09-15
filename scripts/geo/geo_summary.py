"""
scripts/geo/geo_summary.py

Phase 1 / Task 11 (ADR-0001) -- read-only export: queries the
`geo.resolved_observation_counts` view (created by
scripts/database/create_geo_views.py -- run that first) and writes a
flat, analytics-ready JSON summary to
data/analytics/geo/geo_summary.json, matching the existing house
style (array-of-flat-objects, 4-space indent, snake_case) used by
data/analytics/ndma/*.json and data/analytics/pdma/gauge_forecast.json
(Task 9).

This is the first consumable data product built on top of Task 10's
canonical geography: "how many real observations do we have, broken
out by canonical province/district" -- something no query in this
repository could answer before Task 10/11.

Read-only against Postgres (a single SELECT against a view -- no
existing table is written to, no schema change). The only write is the
JSON file, overwritten fresh each run (same full-overwrite convention
already used by every other data/analytics/*.json output).

Run manually, after create_geo_views.py:
    python scripts/geo/geo_summary.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from config.database import engine  # noqa: E402
from config.path import ANALYTICS_DATA  # noqa: E402
from scripts.geo.summary_format import build_summary_records  # noqa: E402

OUTPUT_PATH = ANALYTICS_DATA / "geo" / "geo_summary.json"


def main():
    print("=" * 60)
    print("GEO SUMMARY EXPORT")
    print("=" * 60)

    generated_at = datetime.now(timezone.utc).isoformat()

    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM geo.resolved_observation_counts"))
        rows = result.fetchall()

    records = build_summary_records(rows, generated_at)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4)

    total_observations = sum(r["observation_count"] for r in records)
    print(f"Admin units with resolved observations: {len({r['admin_unit_id'] for r in records})}")
    print(f"(source, domain) groups: {len(records)}")
    print(f"Total resolved observations counted: {total_observations}")
    print(f"Written to: {OUTPUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
