import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


IGNORE = {

    "",
    "DISTRICT",
    "STATIONS",
    "NULLAHS",
    "CHENAB",
    "INDUS",
    "JHELUM",
    "JEHLUM",
    "RAVI",
    "SUTLEJ",
    "FLOOD LIMIT IN CUSECS",
    "FLOOD LIMITS IN CUSECS",
    "DG KHAN HILL TORRENTS",
    "DG KHAN HILL TORRENT S",
    "RAJANPUR HILL TORRENTS",
    "RAJANPU R HILL TORRENT S"

}


def clean_station(name):

    if not name:
        return []

    name = str(name).strip()

    if not name:
        return []

    upper = name.upper()

    if upper.startswith("NOTE"):
        return []

    if upper.startswith("ALL NULLAHS"):
        return []

    if upper.startswith("NULLAHS"):
        return []

    stations = []

    # Split only by comma first
    comma_parts = name.split(",")

    for part in comma_parts:

        part = part.strip()

        if not part:
            continue

        # Split on '&' only when not inside parentheses
        if "(" not in part and ")" not in part and "&" in part:

            pieces = part.split("&")

        else:

            pieces = [part]

        for piece in pieces:

            station = piece.strip()

            if not station:
                continue

            if station.upper() in IGNORE:
                continue

            stations.append(station)

    return stations


def load_dim_station():

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                TRUNCATE TABLE dim_station
                RESTART IDENTITY CASCADE;
                """
            )
        )

        rows = conn.execute(

            text("""

                SELECT station
                FROM pdma_rainfall_readings

                UNION ALL

                SELECT station
                FROM pdma_gauge_readings

            """)

        ).fetchall()

        stations = set()

        for row in rows:

            for station in clean_station(row.station):

                stations.add(station)

        for station in sorted(stations):

            conn.execute(

                text("""

                    INSERT INTO dim_station(

                        station_name,
                        province_key

                    )

                    VALUES(

                        :station,
                        1

                    )

                    ON CONFLICT(station_name)
                    DO NOTHING

                """),

                {
                    "station": station
                }

            )

    print("=" * 60)
    print("DIM STATION LOADED")
    print("=" * 60)
    print(f"Stations : {len(stations)}")
    print("=" * 60)


def main():

    load_dim_station()


if __name__ == "__main__":
    main()