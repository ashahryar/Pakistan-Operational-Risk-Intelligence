import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


TABLES = [

"""
CREATE TABLE IF NOT EXISTS dim_station(

    station_key SERIAL PRIMARY KEY,

    station_name TEXT UNIQUE NOT NULL,

    province_key INTEGER REFERENCES dim_province(province_key),

    latitude DOUBLE PRECISION,

    longitude DOUBLE PRECISION,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
""",

"""
CREATE INDEX IF NOT EXISTS idx_dim_station_name
ON dim_station(station_name);
"""

]


def create_station_dimension():

    with engine.begin() as conn:

        for sql in TABLES:
            conn.execute(text(sql))

    print("=" * 60)
    print("DIM_STATION CREATED")
    print("=" * 60)


def main():

    create_station_dimension()


if __name__ == "__main__":
    main()