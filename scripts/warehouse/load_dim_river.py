import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


IGNORE = {

    "",
    "NULLAHS",
    "NULLAHS DATA SOURCE: F",
    "FLOOD LIMIT IN CUSECS",
    "FLOOD LIMITS IN CUSECS",
    "DG KHAN HILL TORRENTS",
    "DG KHAN HILL TORRENT S",
    "RAJANPUR HILL TORRENTS",
    "RAJANPU R HILL TORRENT S"

}


def load_dim_river():

    with engine.begin() as conn:

        conn.execute(text("""
            TRUNCATE TABLE dim_river
            RESTART IDENTITY CASCADE;
        """))

        rows = conn.execute(text("""
            SELECT DISTINCT river
            FROM pdma_gauge_readings
            WHERE river IS NOT NULL
        """)).fetchall()

        inserted = 0

        for row in rows:

            river = str(row.river).strip()

            if not river:
                continue

            if river.upper().startswith("NOTE"):
                continue

            if river.upper() in IGNORE:
                continue

            conn.execute(

                text("""

                INSERT INTO dim_river(

                    river_name

                )

                VALUES(

                    :river

                )

                ON CONFLICT(river_name)
                DO NOTHING

                """),

                {
                    "river": river
                }

            )

            inserted += 1

    print("=" * 60)
    print("DIM RIVER LOADED")
    print("=" * 60)
    print(f"Inserted : {inserted}")
    print("=" * 60)


def main():

    load_dim_river()


if __name__ == "__main__":
    main()