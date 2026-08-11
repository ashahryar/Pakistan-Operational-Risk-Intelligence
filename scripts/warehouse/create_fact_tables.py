import sys
from pathlib import Path

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine

# ==========================================================
# FACT TABLES
# ==========================================================

TABLES = [

# ==========================================================
# FACT NDMA CASUALTIES
# ==========================================================

"""
CREATE TABLE IF NOT EXISTS fact_ndma_casualties (

    id SERIAL PRIMARY KEY,

    date_key INTEGER REFERENCES dim_date(date_key),
    province_key INTEGER REFERENCES dim_province(province_key),

    report_number TEXT,

    deaths INTEGER,
    injured INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_ndma_casualties_date
ON fact_ndma_casualties(date_key);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_ndma_casualties_province
ON fact_ndma_casualties(province_key);
""",


# ==========================================================
# FACT NDMA DAMAGE
# ==========================================================

"""
CREATE TABLE IF NOT EXISTS fact_ndma_damage (

    id SERIAL PRIMARY KEY,

    date_key INTEGER REFERENCES dim_date(date_key),
    province_key INTEGER REFERENCES dim_province(province_key),

    report_number TEXT,

    roads_km REAL,
    bridges INTEGER,
    houses_total INTEGER,
    livestock INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_ndma_damage_date
ON fact_ndma_damage(date_key);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_ndma_damage_province
ON fact_ndma_damage(province_key);
""",


# ==========================================================
# FACT PDMA RAINFALL
# ==========================================================

"""
CREATE TABLE IF NOT EXISTS fact_pdma_rainfall (

    id SERIAL PRIMARY KEY,

    date_key INTEGER REFERENCES dim_date(date_key),
    station_key INTEGER REFERENCES dim_station(station_key),

    rainfall_mm REAL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_pdma_rainfall_date
ON fact_pdma_rainfall(date_key);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_pdma_rainfall_station
ON fact_pdma_rainfall(station_key);
""",


# ==========================================================
# FACT PDMA GAUGE
# ==========================================================

"""
CREATE TABLE IF NOT EXISTS fact_pdma_gauge (

    id SERIAL PRIMARY KEY,

    date_key INTEGER REFERENCES dim_date(date_key),
    station_key INTEGER REFERENCES dim_station(station_key),
    river_key INTEGER REFERENCES dim_river(river_key),

    current_level_ft REAL,
    danger_level_ft REAL,
    discharge_cusecs REAL,

    flow_status TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_pdma_gauge_date
ON fact_pdma_gauge(date_key);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_pdma_gauge_station
ON fact_pdma_gauge(station_key);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_pdma_gauge_river
ON fact_pdma_gauge(river_key);
""",


# ==========================================================
# FACT PMD FORECAST
# ==========================================================

"""
CREATE TABLE IF NOT EXISTS fact_pmd_forecast (

    id SERIAL PRIMARY KEY,

    date_key INTEGER REFERENCES dim_date(date_key),
    province_key INTEGER REFERENCES dim_province(province_key),

    temperature REAL,
    humidity REAL,

    forecast_day_1 TEXT,
    forecast_day_2 TEXT,
    forecast_day_3 TEXT,

    category TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_pmd_forecast_date
ON fact_pmd_forecast(date_key);
""",

"""
CREATE INDEX IF NOT EXISTS idx_fact_pmd_forecast_province
ON fact_pmd_forecast(province_key);
"""

]


# ==========================================================
# CREATE TABLES
# ==========================================================

def create_fact_tables():

    with engine.begin() as conn:

        for sql in TABLES:
            conn.execute(text(sql))

    print("=" * 60)
    print("FACT TABLES CREATED")
    print("=" * 60)
    print("✓ fact_ndma_casualties")
    print("✓ fact_ndma_damage")
    print("✓ fact_pdma_rainfall")
    print("✓ fact_pdma_gauge")
    print("✓ fact_pmd_forecast")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():

    create_fact_tables()


if __name__ == "__main__":
    main()