import json
import sys
from pathlib import Path
from datetime import datetime

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.database import engine


# ==========================================================
# CONFIGURATION
# ==========================================================

PMD_FOLDER = Path("data/raw/pmd")

BASE = Path("data/raw/pmd/reports")

REPORT_FILE = BASE / "daily_forecast" / "all" / "latest.json"
ALERT_FILE = BASE / "weather_alerts" / "all" / "latest.json"
OUTLOOK_FILE = BASE / "weekly_outlook" / "all" / "latest.json"


# ==========================================================
# HELPERS
# ==========================================================

def load_json(path: Path):

    with open(path, "r", encoding="utf8") as f:
        return json.load(f)


def parse_timestamp(value):

    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


# ==========================================================
# LOAD REPORT
# ==========================================================

def insert_report(conn, report):

    conn.execute(

        text("""

        INSERT INTO pmd_reports(

            category,
            source,
            url,
            forecast,
            scraped_at

        )

        VALUES(

            :category,
            :source,
            :url,
            :forecast,
            :scraped_at

        )

        """),

        {

            "category": report["category"],
            "source": report["source"],
            "url": report["url"],
            "forecast": report["forecast"],
            "scraped_at": parse_timestamp(
                report["scraped_at"]
            )

        }

    )


# ==========================================================
# LOAD DAILY WEATHER
# ==========================================================

def load_daily_weather(conn):

    report = load_json(REPORT_FILE)

    insert_report(conn, report)

    total = 0

    for table in report["tables"]:

        for row in table["rows"]:

            if len(row) < 6:
                continue

            thursday = row[0]
            wednesday = row[1]
            tuesday = row[2]
            max_temp = row[3]
            humidity = row[4]
            city = row[5]

            conn.execute(

                text("""

                INSERT INTO pmd_weather(

                    category,
                    city,
                    humidity,
                    max_temperature,
                    day1_forecast,
                    day2_forecast,
                    day3_forecast,
                    scraped_at

                )

                VALUES(

                    :category,
                    :city,
                    :humidity,
                    :max_temperature,
                    :day1,
                    :day2,
                    :day3,
                    :scraped_at

                )

                """),

                {

                    "category": report["category"],
                    "city": city,
                    "humidity": humidity,
                    "max_temperature": max_temp,
                    "day1": tuesday,
                    "day2": wednesday,
                    "day3": thursday,
                    "scraped_at": parse_timestamp(
                        report["scraped_at"]
                    )

                }

            )

            total += 1

    print(f"Loaded {total} weather records")

# ==========================================================
# LOAD WEEKLY OUTLOOK
# ==========================================================

def load_weekly_outlook(conn):

    report = load_json(OUTLOOK_FILE)

    insert_report(conn, report)

    total = 0

    for table in report.get("tables", []):

        for row in table.get("rows", []):

            if len(row) < 2:
                continue

            conn.execute(

                text("""

                INSERT INTO pmd_weekly_outlook(

                    forecast_date,
                    weather_description,
                    scraped_at

                )

                VALUES(

                    :forecast_date,
                    :weather_description,
                    :scraped_at

                )

                """),

                {

                    "forecast_date": row[1],
                    "weather_description": row[0],
                    "scraped_at": parse_timestamp(
                        report["scraped_at"]
                    )

                }

            )

            total += 1

    print(f"Loaded {total} weekly outlook records")


# ==========================================================
# LOAD WEATHER ALERTS
# ==========================================================

def load_weather_alerts(conn):

    report = load_json(ALERT_FILE)

    insert_report(conn, report)

    print("Loaded weather alerts report")


# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 60)
    print("LOADING PMD DATASETS")
    print("=" * 60)

    with engine.begin() as conn:

        load_daily_weather(conn)

        load_weekly_outlook(conn)

        load_weather_alerts(conn)

    print()
    print("=" * 60)
    print("PMD DATA LOADED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()