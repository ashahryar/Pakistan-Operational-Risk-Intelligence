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

    inserted = 0

    with engine.begin() as conn:

        for row in rows:

            conn.execute(

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

                    "scraped": parse_timestamp(
                        row.get("scraped_at")
                    ),

                }

            )

            inserted += 1

    print("=" * 60)
    print(f"Daily Forecast Loaded : {inserted}")
    print("=" * 60)

# ==========================================================
# LOAD WEEKLY OUTLOOK
# ==========================================================

def load_weekly():

    rows = load_json(WEEKLY_FILE)

    inserted = 0

    with engine.begin() as conn:

        for row in rows:

            conn.execute(

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

                    "scraped": parse_timestamp(
                        row.get("scraped_at")
                    ),

                }

            )

            inserted += 1

    print("=" * 60)
    print(f"Weekly Outlook Loaded : {inserted}")
    print("=" * 60)


# ==========================================================
# LOAD WEATHER ALERT
# ==========================================================

def load_alerts():

    row = load_json(ALERT_FILE)

    inserted = 0

    with engine.begin() as conn:

        conn.execute(

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

                "scraped": parse_timestamp(
                    row.get("scraped_at")
                ),

            }

        )

        inserted += 1

    print("=" * 60)
    print(f"Weather Alerts Loaded : {inserted}")
    print("=" * 60)

# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 60)
    print("LOADING PMD DATASETS")
    print("=" * 60)

    load_daily()

    load_weekly()

    load_alerts()

    print()

    print("=" * 60)
    print("PMD DATA LOADED SUCCESSFULLY")
    print("=" * 60)


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    main()