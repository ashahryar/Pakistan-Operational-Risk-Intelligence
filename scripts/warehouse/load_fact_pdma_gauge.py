import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


SQL = """

SELECT

    d.date_key,
    s.station_key,
    r.river_key,

    g.current_level_ft,
    g.danger_level_ft,
    g.discharge_cusecs,
    g.flow_status

FROM pdma_gauge_readings g

JOIN dim_date d
ON DATE(g.report_datetime)=d.full_date

JOIN dim_station s
ON UPPER(TRIM(g.station))=UPPER(TRIM(s.station_name))

JOIN dim_river r
ON UPPER(TRIM(g.river))=UPPER(TRIM(r.river_name))

WHERE g.station IS NOT NULL
AND g.river IS NOT NULL

"""


def load_fact_pdma_gauge():

    with engine.begin() as conn:

        conn.execute(text("""
            TRUNCATE TABLE fact_pdma_gauge
            RESTART IDENTITY;
        """))

        rows = conn.execute(text(SQL)).fetchall()

        inserted = 0

        for row in rows:

            conn.execute(

                text("""

                INSERT INTO fact_pdma_gauge(

                    date_key,
                    station_key,
                    river_key,
                    current_level_ft,
                    danger_level_ft,
                    discharge_cusecs,
                    flow_status

                )

                VALUES(

                    :date_key,
                    :station_key,
                    :river_key,
                    :current_level,
                    :danger_level,
                    :discharge,
                    :status

                )

                """),

                {

                    "date_key": row.date_key,
                    "station_key": row.station_key,
                    "river_key": row.river_key,
                    "current_level": row.current_level_ft,
                    "danger_level": row.danger_level_ft,
                    "discharge": row.discharge_cusecs,
                    "status": row.flow_status

                }

            )

            inserted += 1

    print("=" * 60)
    print("FACT PDMA GAUGE LOADED")
    print("=" * 60)
    print(f"Inserted : {inserted}")
    print("=" * 60)


def main():

    load_fact_pdma_gauge()


if __name__ == "__main__":
    main()