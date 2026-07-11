"""
aws/redshift/create_tables.py

Creates all Redshift tables for the Pakistan Operational Risk platform.
Mirrors the PostgreSQL schema with Redshift-optimised DISTKEY / SORTKEY.

Prerequisites:
  - .env must contain REDSHIFT_HOST, REDSHIFT_PORT, REDSHIFT_DB,
    REDSHIFT_USER, REDSHIFT_PASSWORD
  - pip install redshift-connector

Run:
    python aws/redshift/create_tables.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import os
from dotenv import load_dotenv
import redshift_connector

load_dotenv()

REDSHIFT_HOST     = os.getenv("REDSHIFT_HOST")
REDSHIFT_PORT     = int(os.getenv("REDSHIFT_PORT", 5439))
REDSHIFT_DB       = os.getenv("REDSHIFT_DB", "pakistan_operational_risk")
REDSHIFT_USER     = os.getenv("REDSHIFT_USER")
REDSHIFT_PASSWORD = os.getenv("REDSHIFT_PASSWORD")

# ----------------------------------------------------------
# DDL
# ----------------------------------------------------------

TABLES = [

    # ======================================================
    # NDMA
    # ======================================================

    """
    CREATE TABLE IF NOT EXISTS ndma_casualties (
        id            INTEGER IDENTITY(1,1),
        report_number VARCHAR(50),
        report_date   DATE,
        province      VARCHAR(100),
        deaths        INTEGER,
        injured       INTEGER,
        created_at    TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(province)
    SORTKEY(report_date);
    """,

    """
    CREATE TABLE IF NOT EXISTS ndma_damage (
        id            INTEGER IDENTITY(1,1),
        report_number VARCHAR(50),
        report_date   DATE,
        province      VARCHAR(100),
        roads_km      FLOAT,
        bridges       INTEGER,
        houses_total  INTEGER,
        livestock     INTEGER,
        created_at    TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(province)
    SORTKEY(report_date);
    """,

    """
    CREATE TABLE IF NOT EXISTS ndma_relief (
        id            INTEGER IDENTITY(1,1),
        report_number VARCHAR(50),
        report_date   DATE,
        province      VARCHAR(100),
        item          VARCHAR(255),
        quantity      INTEGER,
        created_at    TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(province)
    SORTKEY(report_date);
    """,

    """
    CREATE TABLE IF NOT EXISTS ndma_rescue (
        id                 INTEGER IDENTITY(1,1),
        report_number      VARCHAR(50),
        report_date        DATE,
        province           VARCHAR(100),
        rescue_operations  INTEGER,
        persons_rescued    INTEGER,
        created_at         TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(province)
    SORTKEY(report_date);
    """,

    # ======================================================
    # PMD
    # ======================================================

    """
    CREATE TABLE IF NOT EXISTS pmd_reports (
        id          INTEGER IDENTITY(1,1),
        category    VARCHAR(100),
        source      VARCHAR(50),
        url         VARCHAR(500),
        forecast    VARCHAR(MAX),
        scraped_at  TIMESTAMP,
        created_at  TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTSTYLE ALL
    SORTKEY(scraped_at);
    """,

    """
    CREATE TABLE IF NOT EXISTS pmd_weather (
        id               INTEGER IDENTITY(1,1),
        category         VARCHAR(100),
        city             VARCHAR(100),
        humidity         VARCHAR(50),
        max_temperature  VARCHAR(50),
        day1_forecast    VARCHAR(200),
        day2_forecast    VARCHAR(200),
        day3_forecast    VARCHAR(200),
        scraped_at       TIMESTAMP,
        created_at       TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(city)
    SORTKEY(scraped_at);
    """,

    """
    CREATE TABLE IF NOT EXISTS pmd_weekly_outlook (
        id                  INTEGER IDENTITY(1,1),
        forecast_date       VARCHAR(100),
        weather_description VARCHAR(MAX),
        scraped_at          TIMESTAMP,
        created_at          TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTSTYLE ALL
    SORTKEY(scraped_at);
    """,

    # ======================================================
    # PDMA
    # ======================================================

    """
    CREATE TABLE IF NOT EXISTS pdma_daily_reports (
        id           INTEGER IDENTITY(1,1),
        source_file  VARCHAR(255),
        report_date  DATE,
        report_year  INTEGER,
        forecast     VARCHAR(MAX),
        report_time  VARCHAR(20),
        created_at   TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(report_year)
    SORTKEY(report_date);
    """,

    """
    CREATE TABLE IF NOT EXISTS pdma_rainfall_readings (
        id           INTEGER IDENTITY(1,1),
        source_file  VARCHAR(255),
        report_date  DATE,
        report_year  INTEGER,
        station      VARCHAR(200),
        rainfall_mm  FLOAT,
        created_at   TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(station)
    SORTKEY(report_date);
    """,

    """
    CREATE TABLE IF NOT EXISTS pdma_gauge_readings (
        id                INTEGER IDENTITY(1,1),
        source_file       VARCHAR(255),
        report_datetime   TIMESTAMP,
        report_year       INTEGER,
        station           VARCHAR(200),
        river             VARCHAR(200),
        current_level_ft  FLOAT,
        danger_level_ft   FLOAT,
        discharge_cusecs  FLOAT,
        flow_status       VARCHAR(50),
        created_at        TIMESTAMP DEFAULT SYSDATE,
        PRIMARY KEY (id)
    )
    DISTKEY(river)
    SORTKEY(report_datetime);
    """,
]


def get_connection():
    return redshift_connector.connect(
        host=REDSHIFT_HOST,
        port=REDSHIFT_PORT,
        database=REDSHIFT_DB,
        user=REDSHIFT_USER,
        password=REDSHIFT_PASSWORD,
    )


def create_all_tables():
    conn   = get_connection()
    cursor = conn.cursor()

    print("=" * 60)
    print("CREATING REDSHIFT TABLES")
    print("=" * 60)

    for sql in TABLES:
        table_name = [
            line.strip().split()[-1]
            for line in sql.strip().splitlines()
            if "CREATE TABLE" in line.upper()
        ][0]
        try:
            cursor.execute(sql)
            conn.commit()
            print(f"  [OK] {table_name}")
        except Exception as e:
            conn.rollback()
            print(f"  [FAIL] {table_name}: {e}")

    cursor.close()
    conn.close()

    print("=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    create_all_tables()
