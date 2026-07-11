import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


def create_tables():

    sql = """

    CREATE TABLE IF NOT EXISTS operational_risk(

        id SERIAL PRIMARY KEY,

        district TEXT,

        province TEXT,

        latitude DOUBLE PRECISION,

        longitude DOUBLE PRECISION,

        weather_risk INTEGER,

        disaster_risk INTEGER,

        overall_risk INTEGER,

        risk_level TEXT,

        recommendation TEXT,

        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );

    """

    with engine.begin() as conn:

        conn.execute(text(sql))

    print("Operational Risk table created successfully")


if __name__ == "__main__":

    create_tables()