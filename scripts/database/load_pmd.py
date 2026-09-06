"""
Load PMD Data

Loads

1. Daily Forecast
2. Weekly Outlook
3. Weather Alerts

from parsed JSON into PostgreSQL.
"""

import json
import sys

from pathlib import Path
from datetime import datetime

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(PROJECT_ROOT))

from config.database import engine

# ==========================================================
# DATA QUALITY (Phase 1 / Task 6, ADR-0001)
# ==========================================================

from pipeline.utils.quarantine import write_quarantine
from config.data_quality import REJECTION_THRESHOLD

PARSER_VERSION = "1.0.0"


# ==========================================================
# CONFIGURATION
# ==========================================================

BASE = Path("data/parsed/pmd")

DAILY_FILE = BASE / "daily_forecast" / "latest.json"

WEEKLY_FILE = BASE / "weekly_outlook" / "latest.json"

ALERT_FILE = BASE / "weather_alerts" / "latest.json"


# ==========================================================
# HELPERS
# ==========================================================

def load_json(path: Path):

    if not path.exists():

        raise FileNotFoundError(f"{path} not found")

    with open(path, "r", encoding="utf-8") as file:

        return json.load(file)


def parse_timestamp(value):

    if not value:

        return None

    try:

        return datetime.fromisoformat(value)

    except Exception:

        return None
# ==========================================================
# LOAD DAILY FORECAST
# ==========================================================

def load_daily():

    rows = load_json(DAILY_FILE)

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for row in rows:

        processed += 1

        try:

            scraped_at = parse_timestamp(row.get("scraped_at"))

            with engine.begin() as conn:

                # The normal unique constraint handles this on a fresh schema.
                # This guard also keeps legacy databases idempotent.
                if conn.execute(
                    text("""
                        SELECT 1 FROM pmd_daily_forecast
                        WHERE city IS NOT DISTINCT FROM :city
                          AND scraped_at IS NOT DISTINCT FROM :scraped
                        LIMIT 1
                    """),
                    {"city": row.get("city"), "scraped": scraped_at},
                ).fetchone():
                    skipped += 1
                    continue

                result = conn.execute(

                    text("""

                    INSERT INTO pmd_daily_forecast(

                        city,
                        district,
                        province,
                        temperature,
                        humidity,
                        forecast_day_1,
                        forecast_day_2,
                        forecast_day_3,
                        category,
                        scraped_at

                    )

                    VALUES(

                        :city,
                        :district,
                        :province,
                        :temperature,
                        :humidity,
                        :day1,
                        :day2,
                        :day3,
                        :category,
                        :scraped

                    )

                    ON CONFLICT DO NOTHING

                    """),

                    {

                        "city": row.get("city"),

                        "district": row.get("district"),

                        "province": row.get("province"),

                        "temperature": row.get("temperature"),

                        "humidity": row.get("humidity"),

                        "day1": row.get("forecast_day_1"),

                        "day2": row.get("forecast_day_2"),

                        "day3": row.get("forecast_day_3"),

                        "category": row.get("category"),

                        "scraped": scraped_at,

                    }

                )

                if result.rowcount:
                    inserted += 1
                else:
                    skipped += 1

        except Exception as e:

            rejected += 1

            print(f"[DAILY FORECAST REJECTED] {row.get('city')} | {e}")

            write_quarantine(
                source="pmd",
                domain="daily_forecast",
                source_document=str(DAILY_FILE),
                reason_code="load_exception",
                message=str(e),
                parser_version=PARSER_VERSION,
                raw_payload=row,
            )

    print("=" * 60)
    print(f"Daily Forecast Loaded : {inserted} | Skipped : {skipped} | Rejected : {rejected}")
    print("=" * 60)

    return processed, inserted, skipped, rejected

# ==========================================================
# LOAD WEEKLY OUTLOOK
# ==========================================================

def load_weekly():

    rows = load_json(WEEKLY_FILE)

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for row in rows:

        processed += 1

        try:

            scraped_at = parse_timestamp(row.get("scraped_at"))

            with engine.begin() as conn:

                if conn.execute(
                    text("""
                        SELECT 1 FROM pmd_weekly_outlook
                        WHERE report_date IS NOT DISTINCT FROM :report_date
                          AND scraped_at IS NOT DISTINCT FROM :scraped
                        LIMIT 1
                    """),
                    {"report_date": row.get("date"), "scraped": scraped_at},
                ).fetchone():
                    skipped += 1
                    continue

                result = conn.execute(

                    text("""

                    INSERT INTO pmd_weekly_outlook(

                        report_date,
                        weekday,
                        weather_summary,
                        regions,
                        category,
                        scraped_at

                    )

                    VALUES(

                        :date,
                        :weekday,
                        :summary,
                        :regions,
                        :category,
                        :scraped

                    )

                    ON CONFLICT DO NOTHING

                    """),

                    {

                        "date": row.get("date"),

                        "weekday": row.get("weekday"),

                        "summary": row.get("weather_summary"),

                        "regions": json.dumps(
                            row.get("regions", [])
                        ),

                        "category": row.get("category"),

                        "scraped": scraped_at,

                    }

                )

                if result.rowcount:
                    inserted += 1
                else:
                    skipped += 1

        except Exception as e:

            rejected += 1

            print(f"[WEEKLY OUTLOOK REJECTED] {row.get('date')} | {e}")

            write_quarantine(
                source="pmd",
                domain="weekly_outlook",
                source_document=str(WEEKLY_FILE),
                reason_code="load_exception",
                message=str(e),
                parser_version=PARSER_VERSION,
                raw_payload=row,
            )

    print("=" * 60)
    print(f"Weekly Outlook Loaded : {inserted} | Skipped : {skipped} | Rejected : {rejected}")
    print("=" * 60)

    return processed, inserted, skipped, rejected


# ==========================================================
# LOAD WEATHER ALERT
# ==========================================================

def load_alerts():

    row = load_json(ALERT_FILE)

    processed = 1
    inserted = 0
    skipped = 0
    rejected = 0

    try:

        scraped_at = parse_timestamp(row.get("scraped_at"))

        with engine.begin() as conn:

            if conn.execute(
                text("""
                    SELECT 1 FROM pmd_weather_alerts
                    WHERE alert_type IS NOT DISTINCT FROM :alert_type
                      AND scraped_at IS NOT DISTINCT FROM :scraped
                    LIMIT 1
                """),
                {"alert_type": row.get("alert_type"), "scraped": scraped_at},
            ).fetchone():
                skipped += 1

            else:

                result = conn.execute(

                    text("""

                    INSERT INTO pmd_weather_alerts(

                        alert_type,
                        severity,
                        duration,
                        regions,
                        forecast,
                        category,
                        scraped_at

                    )

                    VALUES(

                        :type,
                        :severity,
                        :duration,
                        :regions,
                        :forecast,
                        :category,
                        :scraped

                    )

                    ON CONFLICT DO NOTHING

                    """),

                    {

                        "type": row.get("alert_type"),

                        "severity": row.get("severity"),

                        "duration": row.get("duration"),

                        "regions": json.dumps(
                            row.get("regions", [])
                        ),

                        "forecast": row.get("forecast"),

                        "category": row.get("category"),

                        "scraped": scraped_at,

                    }

                )

                if result.rowcount:
                    inserted += 1
                else:
                    skipped += 1

    except Exception as e:

        rejected += 1

        print(f"[WEATHER ALERT REJECTED] {e}")

        write_quarantine(
            source="pmd",
            domain="weather_alerts",
            source_document=str(ALERT_FILE),
            reason_code="load_exception",
            message=str(e),
            parser_version=PARSER_VERSION,
            raw_payload=row,
        )

    print("=" * 60)
    print(f"Weather Alerts Loaded : {inserted} | Skipped : {skipped} | Rejected : {rejected}")
    print("=" * 60)

    return processed, inserted, skipped, rejected

# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 60)
    print("LOADING PMD DATASETS")
    print("=" * 60)

    daily_p, daily_i, daily_s, daily_r = load_daily()

    weekly_p, weekly_i, weekly_s, weekly_r = load_weekly()

    alerts_p, alerts_i, alerts_s, alerts_r = load_alerts()

    grand_processed = daily_p + weekly_p + alerts_p
    grand_inserted = daily_i + weekly_i + alerts_i
    grand_skipped = daily_s + weekly_s + alerts_s
    grand_rejected = daily_r + weekly_r + alerts_r

    print()

    print("=" * 60)
    print("PMD DATA LOADED SUCCESSFULLY")
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


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    main()
