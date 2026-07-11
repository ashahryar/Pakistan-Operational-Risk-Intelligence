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

BASE = Path("data/parsed/pdma")


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
        return 0

    inserted = 0
    with engine.begin() as conn:
        for year_dir in sorted(folder.iterdir()):
            if not year_dir.is_dir():
                continue
            year = to_int(year_dir.name)
            for json_file in sorted(year_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    report_date = parse_date(data.get("report_date"))
                    conn.execute(
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
                    inserted += 1
                except Exception as e:
                    logger.error("daily %s: %s", json_file.name, e)

    logger.info("Daily reports inserted/skipped: %d", inserted)
    return inserted


# ----------------------------------------------------------
# LOAD RAINFALL READINGS
# ----------------------------------------------------------

def load_rainfall_readings():
    folder = BASE / "rainfall"
    if not folder.exists():
        logger.warning("rainfall folder not found: %s", folder)
        return 0

    inserted = 0
    with engine.begin() as conn:
        for year_dir in sorted(folder.iterdir()):
            if not year_dir.is_dir():
                continue
            year = to_int(year_dir.name)
            for json_file in sorted(year_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    report_date = parse_date(data.get("report_date"))
                    for station in data.get("stations", []):
                        conn.execute(
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
                        inserted += 1
                except Exception as e:
                    logger.error("rainfall %s: %s", json_file.name, e)

    logger.info("Rainfall readings inserted/skipped: %d", inserted)
    return inserted


# ----------------------------------------------------------
# LOAD GAUGE READINGS
# ----------------------------------------------------------

def load_gauge_readings():
    folder = BASE / "gauge"
    if not folder.exists():
        logger.warning("gauge folder not found: %s", folder)
        return 0

    inserted = 0
    with engine.begin() as conn:
        for year_dir in sorted(folder.iterdir()):
            if not year_dir.is_dir():
                continue
            year = to_int(year_dir.name)
            for json_file in sorted(year_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    report_dt = data.get("report_datetime")
                    for gauge in data.get("gauges", []):
                        conn.execute(
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
                        inserted += 1
                except Exception as e:
                    logger.error("gauge %s: %s", json_file.name, e)

    logger.info("Gauge readings inserted/skipped: %d", inserted)
    return inserted


# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------

def main():
    print("=" * 60)
    print("LOADING PDMA DATASETS")
    print("=" * 60)
    load_daily_reports()
    load_rainfall_readings()
    load_gauge_readings()
    print("=" * 60)
    print("PDMA DATA LOADED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
