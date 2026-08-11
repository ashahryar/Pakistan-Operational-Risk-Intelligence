import sys
import json
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


PARSED_DIR = Path("data/parsed/pdma/gauge")


INSERT_SQL = text("""

INSERT INTO pdma_gauge_readings(

    report_datetime,
    station,
    river,
    current_level_ft,
    danger_level_ft,
    discharge_cusecs,
    flow_status

)

VALUES(

    :report_datetime,
    :station,
    :river,
    :current_level_ft,
    :danger_level_ft,
    :discharge_cusecs,
    :flow_status

)

""")


def load_json():

    inserted = 0

    with engine.begin() as conn:

        print("=" * 60)
        print("Cleaning staging table ...")
        print("=" * 60)

        conn.execute(text("""

            TRUNCATE TABLE pdma_gauge_readings
            RESTART IDENTITY;

        """))

        json_files = sorted(
            PARSED_DIR.rglob("*.json")
        )

        print(f"JSON Files : {len(json_files)}")
        print()

        for json_file in json_files:

            with open(
                json_file,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            report_datetime = data.get(
                "report_datetime"
            )

            gauges = data.get(
                "gauges",
                []
            )
            for gauge in gauges:

                station = gauge.get("station")

                river = gauge.get("river")

                if not station:
                    continue

                conn.execute(

                    INSERT_SQL,

                    {

                        "report_datetime": report_datetime,

                        "station": station.strip(),

                        "river": river.strip() if river else None,

                        "current_level_ft": gauge.get("current_level_ft"),

                        "danger_level_ft": gauge.get("danger_level_ft"),

                        "discharge_cusecs": gauge.get("discharge_cusecs"),

                        "flow_status": gauge.get("flow_status"),

                    }

                )

                inserted += 1

    print()
    print("=" * 60)
    print("PDMA GAUGE STAGING LOADED")
    print("=" * 60)
    print(f"JSON Files : {len(json_files)}")
    print(f"Rows Inserted : {inserted}")
    print("=" * 60)


def main():

    load_json()


if __name__ == "__main__":

    main()