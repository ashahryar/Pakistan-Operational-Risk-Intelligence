import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


SQL = """
SELECT

    d.date_key,
    s.station_key,
    r.rainfall_mm

FROM pdma_rainfall_readings r

JOIN dim_date d
ON r.report_date = d.full_date

JOIN dim_station s
ON TRIM(r.station)=TRIM(s.station_name)

WHERE r.rainfall_mm IS NOT NULL
"""


def load_fact_pdma_rainfall():

    with engine.begin() as conn:

        conn.execute(text("""
            TRUNCATE TABLE fact_pdma_rainfall
            RESTART IDENTITY;
        """))

        rows = conn.execute(text(SQL)).fetchall()

        inserted = 0

        for row in rows:

            conn.execute(text("""

                INSERT INTO fact_pdma_rainfall(

                    date_key,
                    station_key,
                    rainfall_mm

                )

                VALUES(

                    :date_key,
                    :station_key,
                    :rainfall_mm

                )

            """),

            {

                "date_key": row.date_key,
                "station_key": row.station_key,
                "rainfall_mm": row.rainfall_mm

            })

            inserted += 1

    print("=" * 60)
    print("FACT PDMA RAINFALL LOADED")
    print("=" * 60)
    print(f"Inserted : {inserted}")
    print("=" * 60)


if __name__ == "__main__":
    load_fact_pdma_rainfall()