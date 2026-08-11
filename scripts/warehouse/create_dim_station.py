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

    province TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
""",

"""
CREATE INDEX IF NOT EXISTS idx_dim_station_name
ON dim_station(station_name);
"""

]


def create_dim_station():

    with engine.begin() as conn:

        for sql in TABLES:
            conn.execute(text(sql))

    print("=" * 60)
    print("DIM STATION CREATED")
    print("=" * 60)


def main():

    create_dim_station()


if __name__ == "__main__":
    main()