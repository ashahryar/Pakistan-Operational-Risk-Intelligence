"""
Create PDMA Tables

Creates all PostgreSQL tables required for
Daily Reports
Rainfall Reports
Gauge Reports

Safe to execute multiple times.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import text
from config.database import engine


TABLES = [

    # ==========================================================
    # DAILY REPORTS
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pdma_daily_reports(

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

    # ==========================================================
    # RAINFALL
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pdma_rainfall_readings(

        id SERIAL PRIMARY KEY,

        source_file TEXT,

        report_date DATE,

        report_year INTEGER,

        station TEXT,

        rainfall_mm REAL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(source_file,station)

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

    # ==========================================================
    # GAUGE
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pdma_gauge_readings(

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

        UNIQUE(source_file,station)

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


def create_pdma_tables():

    with engine.begin() as conn:

        for sql in TABLES:

            conn.execute(text(sql))

    print("=" * 60)
    print("PDMA TABLES CREATED SUCCESSFULLY")
    print("=" * 60)
    print("✓ pdma_daily_reports")
    print("✓ pdma_rainfall_readings")
    print("✓ pdma_gauge_readings")
    print("=" * 60)


def main():

    create_pdma_tables()


if __name__ == "__main__":

    main()