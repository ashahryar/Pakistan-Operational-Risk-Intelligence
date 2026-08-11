import sys
from pathlib import Path

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


# ==========================================================
# LOAD FACT NDMA CASUALTIES
# ==========================================================

def load_fact_ndma_casualties():

    with engine.begin() as conn:

        # Optional: reload from scratch
        conn.execute(text("TRUNCATE TABLE fact_ndma_casualties RESTART IDENTITY;"))

        rows = conn.execute(text("""

            SELECT

                c.report_number,
                c.report_date,
                c.province,
                c.deaths,
                c.injured,

                d.date_key,
                p.province_key

            FROM ndma_casualties c

            JOIN dim_date d
                ON c.report_date = d.full_date

            JOIN dim_province p
                ON c.province = p.province_name

            ORDER BY
                c.report_date,
                c.province

        """)).fetchall()

        inserted = 0

        for row in rows:

            conn.execute(
                text("""

                    INSERT INTO fact_ndma_casualties(

                        date_key,
                        province_key,
                        report_number,
                        deaths,
                        injured

                    )

                    VALUES(

                        :date_key,
                        :province_key,
                        :report_number,
                        :deaths,
                        :injured

                    )

                """),
                {

                    "date_key": row.date_key,
                    "province_key": row.province_key,
                    "report_number": row.report_number,
                    "deaths": int(row.deaths or 0),
                    "injured": int(row.injured or 0),

                }
            )

            inserted += 1

    print("=" * 60)
    print("FACT NDMA CASUALTIES LOADED")
    print("=" * 60)
    print(f"Inserted : {inserted}")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():

    load_fact_ndma_casualties()


if __name__ == "__main__":
    main()