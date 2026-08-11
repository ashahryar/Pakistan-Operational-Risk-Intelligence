import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


# ==========================================================
# LOAD NDMA CASUALTIES
# ==========================================================

def load_casualties():

    with engine.begin() as conn:

        conn.execute(text("DELETE FROM fact_ndma_casualties"))

        rows = conn.execute(text("""

            SELECT
                report_number,
                report_date,
                province,
                deaths,
                injured
            FROM ndma_casualties

        """)).mappings()

        count = 0

        for row in rows:

            province_key = conn.execute(
                text("""
                    SELECT province_key
                    FROM dim_province
                    WHERE province_name=:province
                """),
                {
                    "province": row["province"]
                }
            ).scalar()

            if province_key is None:
                continue

            date_key = int(row["report_date"].strftime("%Y%m%d"))

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
                    "date_key": date_key,
                    "province_key": province_key,
                    "report_number": row["report_number"],
                    "deaths": row["deaths"],
                    "injured": row["injured"]
                }
            )

            count += 1

    print(f"Loaded {count} NDMA casualty facts")


# ==========================================================
# LOAD NDMA DAMAGE
# ==========================================================

def load_damage():

    with engine.begin() as conn:

        conn.execute(text("DELETE FROM fact_ndma_damage"))

        rows = conn.execute(text("""

            SELECT
                report_number,
                report_date,
                province,
                roads_km,
                bridges,
                houses_total,
                livestock
            FROM ndma_damage

        """)).mappings()

        count = 0

        for row in rows:

            province_key = conn.execute(
                text("""
                    SELECT province_key
                    FROM dim_province
                    WHERE province_name=:province
                """),
                {
                    "province": row["province"]
                }
            ).scalar()

            if province_key is None:
                continue

            date_key = int(row["report_date"].strftime("%Y%m%d"))

            conn.execute(
                text("""

                    INSERT INTO fact_ndma_damage(

                        date_key,
                        province_key,
                        report_number,
                        roads_km,
                        bridges,
                        houses_total,
                        livestock

                    )

                    VALUES(

                        :date_key,
                        :province_key,
                        :report_number,
                        :roads_km,
                        :bridges,
                        :houses_total,
                        :livestock

                    )

                """),
                {
                    "date_key": date_key,
                    "province_key": province_key,
                    "report_number": row["report_number"],
                    "roads_km": row["roads_km"],
                    "bridges": row["bridges"],
                    "houses_total": row["houses_total"],
                    "livestock": row["livestock"]
                }
            )

            count += 1

    print(f"Loaded {count} NDMA damage facts")


# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 60)
    print("LOADING NDMA FACT TABLES")
    print("=" * 60)

    load_casualties()
    load_damage()

    print("=" * 60)
    print("NDMA FACT TABLES LOADED")
    print("=" * 60)


if __name__ == "__main__":
    main()