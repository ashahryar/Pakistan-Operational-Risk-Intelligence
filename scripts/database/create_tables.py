import sys
from pathlib import Path

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine

# ==========================================================
# SQL TABLES
# ==========================================================

TABLES = [  

    # ==========================================================
    # NDMA CASUALTIES
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS ndma_casualties (

        id SERIAL PRIMARY KEY,

        report_number TEXT NOT NULL,
        report_date DATE NOT NULL,
        province TEXT NOT NULL,

        deaths INTEGER,
        injured INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province)

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_casualties_date
    ON ndma_casualties(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_casualties_province
    ON ndma_casualties(province);
    """,

    # ==========================================================
    # NDMA DAMAGE
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS ndma_damage (

        id SERIAL PRIMARY KEY,

        report_number TEXT NOT NULL,
        report_date DATE NOT NULL,
        province TEXT NOT NULL,

        roads_km REAL,
        bridges INTEGER,
        houses_total INTEGER,
        livestock INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province)

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_damage_date
    ON ndma_damage(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_damage_province
    ON ndma_damage(province);
    """,

    # ==========================================================
    # NDMA RELIEF
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS ndma_relief (

        id SERIAL PRIMARY KEY,

        report_number TEXT NOT NULL,
        report_date DATE NOT NULL,
        province TEXT NOT NULL,

        item TEXT NOT NULL,
        quantity INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province, item)

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_relief_date
    ON ndma_relief(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_relief_province
    ON ndma_relief(province);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_relief_item
    ON ndma_relief(item);
    """,

    # ==========================================================
    # NDMA RESCUE
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS ndma_rescue (

        id SERIAL PRIMARY KEY,

        report_number TEXT NOT NULL,
        report_date DATE NOT NULL,
        province TEXT NOT NULL,

        rescue_operations INTEGER,
        persons_rescued INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province)

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_rescue_date
    ON ndma_rescue(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_ndma_rescue_province
    ON ndma_rescue(province);
    """,

    # ==========================================================
    # PMD TABLES START HERE
    # (Continue in Part 2)
    # ==========================================================
    # ==========================================================
    # PMD TABLES
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pmd_daily_forecast (
        id SERIAL PRIMARY KEY,

        city TEXT,
        province TEXT,

        temperature REAL,
        humidity REAL,

        forecast_day_1 TEXT,
        forecast_day_2 TEXT,
        forecast_day_3 TEXT,

        category TEXT,

        scraped_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_daily_city
    ON pmd_daily_forecast(city);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_daily_province
    ON pmd_daily_forecast(province);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_daily_scraped
    ON pmd_daily_forecast(scraped_at);
    """,

    """
    CREATE TABLE IF NOT EXISTS pmd_weekly_outlook (
        id SERIAL PRIMARY KEY,

        report_date TEXT,
        weekday TEXT,
        weather_summary TEXT,
        regions JSONB,

        scraped_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_weekly_date
    ON pmd_weekly_outlook(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pmd_weekly_scraped
    ON pmd_weekly_outlook(scraped_at);
    """,

    """
    CREATE TABLE IF NOT EXISTS pmd_weather_alerts (
        id SERIAL PRIMARY KEY,

        alert_type TEXT,
        severity TEXT,
        duration TEXT,
        regions JSONB,
        forecast TEXT,

        scraped_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    # ==========================================================
    # PDMA TABLES
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pdma_daily_reports (
        id SERIAL PRIMARY KEY,

        source_file TEXT UNIQUE,
        report_date DATE,
        report_year INTEGER,

        raw_data JSONB,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pdma_daily_date
    ON pdma_daily_reports(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pdma_daily_year
    ON pdma_daily_reports(report_year);
    """,

    """
    CREATE TABLE IF NOT EXISTS pdma_rainfall_readings (
        id SERIAL PRIMARY KEY,

        source_file TEXT,
        report_date DATE,
        report_year INTEGER,

        station TEXT,
        rainfall_mm REAL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(source_file, station)
    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pdma_rainfall_date
    ON pdma_rainfall_readings(report_date);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pdma_rainfall_station
    ON pdma_rainfall_readings(station);
    """,

    """
    CREATE TABLE IF NOT EXISTS pdma_gauge_readings (
        id SERIAL PRIMARY KEY,

        source_file TEXT,
        report_datetime TIMESTAMP,
        report_year INTEGER,

        station TEXT,
        river TEXT,

        current_level_ft REAL,
        danger_level_ft REAL,
        discharge_cusecs REAL,

        flow_status TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(source_file, station)
    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pdma_gauge_datetime
    ON pdma_gauge_readings(report_datetime);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pdma_gauge_station
    ON pdma_gauge_readings(station);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_pdma_gauge_river
    ON pdma_gauge_readings(river);
    """
]


def create_all_tables():

    with engine.begin() as conn:
        for sql in TABLES:
            conn.execute(text(sql))

    print("=" * 60)
    print("DATABASE TABLES CREATED SUCCESSFULLY")
    print("=" * 60)

    print("NDMA")
    print("  ✓ ndma_casualties")
    print("  ✓ ndma_damage")
    print("  ✓ ndma_relief")
    print("  ✓ ndma_rescue")

    print()
    print("PMD")
    print("  ✓ pmd_daily_forecast")
    print("  ✓ pmd_weekly_outlook")
    print("  ✓ pmd_weather_alerts")

    print()
    print("PDMA")
    print("  ✓ pdma_daily_reports")
    print("  ✓ pdma_rainfall_readings")
    print("  ✓ pdma_gauge_readings")

    print("=" * 60)


def main():
    create_all_tables()


if __name__ == "__main__":
    main()