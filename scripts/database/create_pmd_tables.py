"""
Create PMD Tables

Creates all PostgreSQL tables required for

1. Daily Forecast
2. Weekly Outlook
3. Weather Alerts

Safe to execute multiple times.
"""

import sys
from pathlib import Path

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


# ==========================================================
# TABLES
# ==========================================================

TABLES = [

    # ==========================================================
    # DAILY FORECAST
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pmd_daily_forecast(

        id SERIAL PRIMARY KEY,

        city TEXT NOT NULL,

        district TEXT,

        province TEXT NOT NULL,

        temperature REAL,

        humidity REAL,

        forecast_day_1 TEXT,

        forecast_day_2 TEXT,

        forecast_day_3 TEXT,

        category TEXT NOT NULL,

        scraped_at TIMESTAMP NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(city, scraped_at)

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_daily_city
    ON pmd_daily_forecast(city);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_daily_district
    ON pmd_daily_forecast(district);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_daily_province
    ON pmd_daily_forecast(province);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_daily_scraped
    ON pmd_daily_forecast(scraped_at);
    """,
    # ==========================================================
    # WEEKLY OUTLOOK
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pmd_weekly_outlook(

        id SERIAL PRIMARY KEY,

        report_date TEXT NOT NULL,

        weekday TEXT NOT NULL,

        weather_summary TEXT NOT NULL,

        regions JSONB,

        category TEXT NOT NULL,

        scraped_at TIMESTAMP NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_date, scraped_at)

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_weekly_date
    ON pmd_weekly_outlook(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_weekly_weekday
    ON pmd_weekly_outlook(weekday);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_weekly_scraped
    ON pmd_weekly_outlook(scraped_at);
    """,

    # ==========================================================
    # WEATHER ALERTS
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pmd_weather_alerts(

        id SERIAL PRIMARY KEY,

        alert_type TEXT NOT NULL,

        severity TEXT NOT NULL,

        duration TEXT,

        regions JSONB,

        forecast TEXT NOT NULL,

        category TEXT NOT NULL,

        scraped_at TIMESTAMP NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(alert_type, scraped_at)

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_alert_type
    ON pmd_weather_alerts(alert_type);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_alert_severity
    ON pmd_weather_alerts(severity);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_alert_scraped
    ON pmd_weather_alerts(scraped_at);
    """,

]
# ==========================================================
# CREATE TABLES
# ==========================================================

def create_pmd_tables():

    with engine.begin() as conn:

        for sql in TABLES:

            conn.execute(text(sql))

    print("=" * 60)
    print("PMD TABLES CREATED SUCCESSFULLY")
    print("=" * 60)
    print("✓ pmd_daily_forecast")
    print("✓ pmd_weekly_outlook")
    print("✓ pmd_weather_alerts")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():

    create_pmd_tables()


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    main()