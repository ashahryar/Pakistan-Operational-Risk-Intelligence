import sys
from pathlib import Path

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine

# ==========================================================
# DIMENSION TABLES
# ==========================================================

TABLES = [

    # ======================================================
    # DATE DIMENSION
    # ======================================================

    """
    CREATE TABLE IF NOT EXISTS dim_date (

        date_key INTEGER PRIMARY KEY,

        full_date DATE UNIQUE NOT NULL,

        day INTEGER,
        month INTEGER,
        month_name TEXT,

        quarter INTEGER,

        year INTEGER,

        week INTEGER,

        weekday INTEGER,
        weekday_name TEXT,

        is_weekend BOOLEAN

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_dim_date
    ON dim_date(full_date);
    """,

    # ======================================================
    # PROVINCE DIMENSION
    # ======================================================

    """
    CREATE TABLE IF NOT EXISTS dim_province (

        province_key SERIAL PRIMARY KEY,

        province_name TEXT UNIQUE NOT NULL,

        country TEXT,

        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_dim_province_name
    ON dim_province(province_name);
    """,

    # ======================================================
    # RIVER DIMENSION
    # ======================================================

    """
    CREATE TABLE IF NOT EXISTS dim_river (

        river_key SERIAL PRIMARY KEY,

        river_name TEXT UNIQUE NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_dim_river
    ON dim_river(river_name);
    """

]

# ==========================================================
# CREATE TABLES
# ==========================================================

def create_dimension_tables():

    with engine.begin() as conn:

        for sql in TABLES:
            conn.execute(text(sql))

    print("=" * 60)
    print("DIMENSION TABLES CREATED")
    print("=" * 60)
    print("✓ dim_date")
    print("✓ dim_province")
    print("✓ dim_river")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():

    create_dimension_tables()


if __name__ == "__main__":
    main()