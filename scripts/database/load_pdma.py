"""
PDMA PostgreSQL Loader

Loads parsed PDMA JSON files into PostgreSQL:
  - pdma_daily_reports
  - pdma_rainfall_readings
  - pdma_gauge_readings

Idempotent: uses ON CONFLICT DO NOTHING.
"""

import json
import sys
import logging
from pathlib import Path
from datetime import datetime

from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config.database import engine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE = PROJECT_ROOT / "data" / "parsed" / "pdma"

# ==========================================================
# DATA QUALITY (Phase 1 / Task 6, ADR-0001)
# ==========================================================

from pipeline.utils.quarantine import write_quarantine
from config.data_quality import REJECTION_THRESHOLD

PARSER_VERSION = "1.0.0"


# ----------------------------------------------------------
# HELPERS
# ----------------------------------------------------------

def parse_date(value):
    if not value:
        return None
    for fmt in ("%d %B %Y", "%d.%m.%Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except Exception:
            continue
    return None


def to_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return None


# ----------------------------------------------------------
# LOAD DAILY REPORTS
# ----------------------------------------------------------

def load_daily_reports():
    folder = BASE / "daily"
    if not folder.exists():
        logger.warning("daily folder not found: %s", folder)
        return 0, 0, 0, 0

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for year_dir in sorted(folder.iterdir()):
        if not year_dir.is_dir():
            continue
        year = to_int(year_dir.name)
        for json_file in sorted(year_dir.glob("*.json")):
            processed += 1
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                report_date = parse_date(data.get("report_date"))
                with engine.begin() as conn:
                    result = conn.execute(
                        text("""
                            INSERT INTO pdma_daily_reports
                                (source_file, report_date, report_year, raw_data)
                            VALUES
                                (:source_file, :report_date, :report_year, CAST(:raw_data AS jsonb))
                            ON CONFLICT (source_file) DO NOTHING
                        """),
                        {
                            "source_file": json_file.name,
                            "report_date": report_date,
                            "report_year": year,
                            "raw_data": json.dumps(data),
                        },
                    )
                    if result.rowcount:
                        inserted += 1
                    else:
                        skipped += 1
            except Exception as e:
                rejected += 1
                logger.error("daily %s: %s", json_file.name, e)
                write_quarantine(
                    source="pdma",
                    domain="daily",
                    source_document=str(json_file),
                    reason_code="load_exception",
                    message=str(e),
                    parser_version=PARSER_VERSION,
                )

    logger.info(
        "Daily reports processed=%d inserted=%d skipped=%d rejected=%d",
        processed, inserted, skipped, rejected,
    )
    return processed, inserted, skipped, rejected


# ----------------------------------------------------------
# LOAD RAINFALL READINGS
# ----------------------------------------------------------

def load_rainfall_readings():
    folder = BASE / "rainfall"
    if not folder.exists():
        logger.warning("rainfall folder not found: %s", folder)
        return 0, 0, 0, 0

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for year_dir in sorted(folder.iterdir()):
        if not year_dir.is_dir():
            continue
        year = to_int(year_dir.name)
        for json_file in sorted(year_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                report_date = parse_date(data.get("report_date"))
            except Exception as e:
                processed += 1
                rejected += 1
                logger.error("rainfall %s: %s", json_file.name, e)
                write_quarantine(
                    source="pdma",
                    domain="rainfall",
                    source_document=str(json_file),
                    reason_code="load_exception",
                    message=str(e),
                    parser_version=PARSER_VERSION,
                )
                continue

            for station in data.get("stations", []):
                processed += 1
                try:
                    with engine.begin() as conn:
                        result = conn.execute(
                            text("""
                                INSERT INTO pdma_rainfall_readings
                                    (source_file, report_date, report_year, station, rainfall_mm)
                                VALUES
                                    (:source_file, :report_date, :report_year, :station, :rainfall_mm)
                                ON CONFLICT (source_file, station) DO NOTHING
                            """),
                            {
                                "source_file": json_file.name,
                                "report_date": report_date,
                                "report_year": year,
                                "station": station.get("station"),
                                "rainfall_mm": station.get("rainfall_mm"),
                            },
                        )
                        if result.rowcount:
                            inserted += 1
                        else:
                            skipped += 1
                except Exception as e:
                    rejected += 1
                    logger.error("rainfall %s: %s", json_file.name, e)
                    write_quarantine(
                        source="pdma",
                        domain="rainfall",
                        source_document=str(json_file),
                        reason_code="load_exception",
                        message=str(e),
                        parser_version=PARSER_VERSION,
                        raw_payload=station,
                    )

    logger.info(
        "Rainfall readings processed=%d inserted=%d skipped=%d rejected=%d",
        processed, inserted, skipped, rejected,
    )
    return processed, inserted, skipped, rejected


# ----------------------------------------------------------
# LOAD GAUGE READINGS
# ----------------------------------------------------------

def load_gauge_readings():
    folder = BASE / "gauge"
    if not folder.exists():
        logger.warning("gauge folder not found: %s", folder)
        return 0, 0, 0, 0

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for year_dir in sorted(folder.iterdir()):
        if not year_dir.is_dir():
            continue
        year = to_int(year_dir.name)
        for json_file in sorted(year_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                report_dt = data.get("report_datetime")
            except Exception as e:
                processed += 1
                rejected += 1
                logger.error("gauge %s: %s", json_file.name, e)
                write_quarantine(
                    source="pdma",
                    domain="gauge",
                    source_document=str(json_file),
                    reason_code="load_exception",
                    message=str(e),
                    parser_version=PARSER_VERSION,
                )
                continue

            for gauge in data.get("gauges", []):
                processed += 1
                try:
                    with engine.begin() as conn:
                        result = conn.execute(
                            text("""
                                INSERT INTO pdma_gauge_readings
                                    (source_file, report_datetime, report_year,
                                     station, river, current_level_ft,
                                     danger_level_ft, discharge_cusecs, flow_status)
                                VALUES
                                    (:source_file, :report_datetime, :report_year,
                                     :station, :river, :current_level_ft,
                                     :danger_level_ft, :discharge_cusecs, :flow_status)
                                ON CONFLICT (source_file, station) DO NOTHING
                            """),
                            {
                                "source_file": json_file.name,
                                "report_datetime": report_dt,
                                "report_year": year,
                                "station": gauge.get("station"),
                                "river": gauge.get("river"),
                                "current_level_ft": gauge.get("current_level_ft"),
                                "danger_level_ft": gauge.get("danger_level_ft"),
                                "discharge_cusecs": gauge.get("discharge_cusecs"),
                                "flow_status": gauge.get("flow_status"),
                            },
                        )
                        if result.rowcount:
                            inserted += 1
                        else:
                            skipped += 1
                except Exception as e:
                    rejected += 1
                    logger.error("gauge %s: %s", json_file.name, e)
                    write_quarantine(
                        source="pdma",
                        domain="gauge",
                        source_document=str(json_file),
                        reason_code="load_exception",
                        message=str(e),
                        parser_version=PARSER_VERSION,
                        raw_payload=gauge,
                    )

    logger.info(
        "Gauge readings processed=%d inserted=%d skipped=%d rejected=%d",
        processed, inserted, skipped, rejected,
    )
    return processed, inserted, skipped, rejected


# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------

def main():
    print("=" * 60)
    print("LOADING PDMA DATASETS")
    print("=" * 60)
    print(BASE)
    print(BASE.exists())

    daily_p, daily_i, daily_s, daily_r = load_daily_reports()
    rain_p, rain_i, rain_s, rain_r = load_rainfall_readings()
    gauge_p, gauge_i, gauge_s, gauge_r = load_gauge_readings()

    grand_processed = daily_p + rain_p + gauge_p
    grand_inserted = daily_i + rain_i + gauge_i
    grand_skipped = daily_s + rain_s + gauge_s
    grand_rejected = daily_r + rain_r + gauge_r

    print("=" * 60)
    print("PDMA DATA LOADED SUCCESSFULLY")
    print(f"Processed : {grand_processed}")
    print(f"Inserted  : {grand_inserted}")
    print(f"Skipped   : {grand_skipped}")
    print(f"Rejected  : {grand_rejected}")
    print("=" * 60)

    # ------------------------------------------------------
    # DATA QUALITY GATE (Phase 1 / Task 6, ADR-0001, CLAUDE.md rule 5)
    # ------------------------------------------------------

    if grand_processed == 0:
        return

    rejection_ratio = grand_rejected / grand_processed

    print(f"Rejection Ratio      : {round(rejection_ratio * 100, 2)}%")
    print(f"Rejection Threshold  : {round(REJECTION_THRESHOLD * 100, 2)}%")

    if rejection_ratio > REJECTION_THRESHOLD:

        print("=" * 60)
        print("DATA QUALITY GATE FAILED")
        print(f"{grand_rejected}/{grand_processed} rows rejected — exceeds threshold")
        print("=" * 60)

        sys.exit(1)


if __name__ == "__main__":
    main()
