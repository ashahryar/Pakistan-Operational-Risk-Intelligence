import sys
import json
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine

BASE = Path("data/parsed/pmd")
daily_file = BASE / "daily_forecast" / "latest.json"

if daily_file.exists():

    rows = json.loads(daily_file.read_text(encoding="utf-8"))

    with engine.begin() as conn:

        for row in rows:

            conn.execute(

                text("""

                INSERT INTO pmd_daily_forecast(

                    city,
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
                    :province,
                    :temperature,
                    :humidity,
                    :day1,
                    :day2,
                    :day3,
                    :category,
                    :scraped_at

                )

                """),

                {

                    "city": row["city"],
                    "province": row["province"],
                    "temperature": row["temperature"],
                    "humidity": row["humidity"],
                    "day1": row["forecast_day_1"],
                    "day2": row["forecast_day_2"],
                    "day3": row["forecast_day_3"],
                    "category": row["category"],
                    "scraped_at": row["scraped_at"]

                }

            )

print("✓ Daily Forecast Loaded")
weekly_file = BASE / "weekly_outlook" / "latest.json"

if weekly_file.exists():

    rows = json.loads(weekly_file.read_text(encoding="utf-8"))

    with engine.begin() as conn:

        for row in rows:

            conn.execute(

                text("""

                INSERT INTO pmd_weekly_outlook(

                    report_date,
                    weekday,
                    weather_summary,
                    regions,
                    scraped_at

                )

                VALUES(

                    :date,
                    :weekday,
                    :summary,
                    :regions,
                    :scraped

                )

                """),

                {

                    "date": row["date"],
                    "weekday": row["weekday"],
                    "summary": row["weather_summary"],
                    "regions": json.dumps(row["regions"]),
                    "scraped": row["scraped_at"]

                }

            )

print("✓ Weekly Outlook Loaded")
alert_file = BASE / "weather_alerts" / "latest.json"

if alert_file.exists():

    row = json.loads(alert_file.read_text(encoding="utf-8"))

    with engine.begin() as conn:

        conn.execute(

            text("""

            INSERT INTO pmd_weather_alerts(

                alert_type,
                severity,
                duration,
                regions,
                forecast,
                scraped_at

            )

            VALUES(

                :type,
                :severity,
                :duration,
                :regions,
                :forecast,
                :scraped

            )

            """),

            {

                "type": row["alert_type"],
                "severity": row["severity"],
                "duration": row["duration"],
                "regions": json.dumps(row["regions"]),
                "forecast": row["forecast"],
                "scraped": row["scraped_at"]

            }

        )

print("✓ Weather Alerts Loaded")
print("="*60)
print("PMD DATA LOADED SUCCESSFULLY")
print("="*60)