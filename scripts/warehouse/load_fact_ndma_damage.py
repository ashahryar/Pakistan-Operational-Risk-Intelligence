import sys
from pathlib import Path

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


# ==========================================================
# LOAD FACT NDMA DAMAGE
# ==========================================================

def load_fact_ndma_damage():

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                TRUNCATE TABLE fact_ndma_damage
                RESTART IDENTITY;
                """
            )
        )

        rows = conn.execute(
            text(
                """
                SELECT

                    n.report_number,
                    n.report_date,
                    n.province,

                    n.roads_km,
                    n.bridges,
                    n.houses_total,
                    n.livestock,

                    d.date_key,
                    p.province_key

                FROM ndma_damage n

                JOIN dim_date d
                    ON n.report_date = d.full_date

                JOIN dim_province p
                    ON n.province = p.province_name

                ORDER BY
                    n.report_date,
                    n.province
                """
            )
        ).fetchall()

        inserted = 0

        for row in rows:

            conn.execute(
                text(
                    """
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
                    """
                ),
                {
                    "date_key": row.date_key,
                    "province_key": row.province_key,
                    "report_number": row.report_number,
                    "roads_km": float(row.roads_km or 0),
                    "bridges": int(row.bridges or 0),
                    "houses_total": int(row.houses_total or 0),
                    "livestock": int(row.livestock or 0),
                },
            )

            inserted += 1

    print("=" * 60)
    print("FACT NDMA DAMAGE LOADED")
    print("=" * 60)
    print(f"Inserted : {inserted}")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():

    load_fact_ndma_damage()


if __name__ == "__main__":
    main()