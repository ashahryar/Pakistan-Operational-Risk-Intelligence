from sqlalchemy import text

from connection import engine

TABLES = [

    # ==========================================================
    # NDMA TABLES
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS ndma_casualties (

        id SERIAL PRIMARY KEY,

        report_number TEXT,
        report_date DATE,
        province TEXT,

        deaths INTEGER,
        injured INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province)

    );
    """,

    """
    CREATE TABLE IF NOT EXISTS ndma_damage (

        id SERIAL PRIMARY KEY,

        report_number TEXT,
        report_date DATE,
        province TEXT,

        roads_km REAL,
        bridges INTEGER,
        houses_total INTEGER,
        livestock INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province)

    );
    """,

    """
    CREATE TABLE IF NOT EXISTS ndma_relief (

        id SERIAL PRIMARY KEY,

        report_number TEXT,
        report_date DATE,
        province TEXT,

        item TEXT,
        quantity INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province, item)

    );
    """,

    """
    CREATE TABLE IF NOT EXISTS ndma_rescue (

        id SERIAL PRIMARY KEY,

        report_number TEXT,
        report_date DATE,
        province TEXT,

        rescue_operations INTEGER,
        persons_rescued INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(report_number, report_date, province)

    );
    """,

    # ==========================================================
    # PMD TABLES
    # ==========================================================

    """
    CREATE TABLE IF NOT EXISTS pmd_reports (

        id SERIAL PRIMARY KEY,

        category TEXT,
        source TEXT,
        url TEXT,

        forecast TEXT,

        scraped_at TIMESTAMP,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );
    """,

    """
    CREATE TABLE IF NOT EXISTS pmd_weather (

        id SERIAL PRIMARY KEY,

        category TEXT,

        city TEXT,

        humidity TEXT,
        max_temperature TEXT,

        day1_forecast TEXT,
        day2_forecast TEXT,
        day3_forecast TEXT,

        scraped_at TIMESTAMP,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );
    """,

    """
    CREATE TABLE IF NOT EXISTS pmd_weekly_outlook (

        id SERIAL PRIMARY KEY,

        forecast_date TEXT,

        weather_description TEXT,

        scraped_at TIMESTAMP,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );
    """,

    # ==========================================================
    # PDMA DAILY REPORTS
    # ==========================================================

    """
    CREATE TABLE pdma_daily_reports (

        id SERIAL PRIMARY KEY,

        pdf_name TEXT UNIQUE,

        report_date DATE,

        report_time TEXT,

        forecast TEXT,

        temperature JSONB,

        rainfall JSONB,

        dams JSONB,

        created_at TIMESTAMP

    );
    """,

    # ==========================================================
    # PDMA RAINFALL REPORTS
    # ==========================================================

    """
    CREATE TABLE pdma_rainfall_reports(

        id SERIAL PRIMARY KEY,

        pdf_name TEXT UNIQUE,

        report_date DATE,

        rainfall_data JSONB,

        created_at TIMESTAMP

    );
    """,

    # ==========================================================
    # PDMA GAUGE REPORTS
    # ==========================================================

    """
    CREATE TABLE pdma_gauge_reports(

        id SERIAL PRIMARY KEY,

        pdf_name TEXT UNIQUE,

        report_date DATE,

        gauge_data JSONB,

        created_at TIMESTAMP

    );
    """

]

with engine.begin() as conn:

    for sql in TABLES:
        conn.execute(text(sql))

print("=" * 60)
print("DATABASE CREATED SUCCESSFULLY")
print("=" * 60)

print("NDMA")
print("  ✓ ndma_casualties")
print("  ✓ ndma_damage")
print("  ✓ ndma_relief")
print("  ✓ ndma_rescue")
print()

print("PMD")
print("  ✓ pmd_reports")
print("  ✓ pmd_weather")
print("  ✓ pmd_weekly_outlook")
print()

print("PDMA")
print("  ✓ pdma_daily_reports")
print("  ✓ pdma_rainfall_reports")
print("  ✓ pdma_gauge_reports")

print("=" * 60)