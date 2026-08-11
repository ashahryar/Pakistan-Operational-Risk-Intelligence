import sys
import json
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine

PARSED_DIR = Path("data/parsed/ndma/sitreps")

CASUALTIES_SQL = text("""
INSERT INTO ndma_casualties (
    source_file,
    report_number,
    report_date,
    province,
    district,
    deaths,
    injured
)
VALUES (
    :source_file,
    :report_number,
    :report_date,
    :province,
    :district,
    :deaths,
    :injured
)
""")

DAMAGE_SQL = text("""
INSERT INTO ndma_damage (
    source_file,
    report_number,
    report_date,
    province,
    district,
    houses_damaged,
    roads_damaged,
    bridges_damaged
)
VALUES (
    :source_file,
    :report_number,
    :report_date,
    :province,
    :district,
    :houses_damaged,
    :roads_damaged,
    :bridges_damaged
)
""")

RELIEF_SQL = text("""
INSERT INTO ndma_relief (
    source_file,
    report_number,
    report_date,
    province,
    district,
    camps,
    beneficiaries
)
VALUES (
    :source_file,
    :report_number,
    :report_date,
    :province,
    :district,
    :camps,
    :beneficiaries
)
""")

RESCUE_SQL = text("""
INSERT INTO ndma_rescue (
    source_file,
    report_number,
    report_date,
    province,
    district,
    rescued_people
)
VALUES (
    :source_file,
    :report_number,
    :report_date,
    :province,
    :district,
    :rescued_people
)
""")
def load_json():

    with engine.begin() as conn:

        print("=" * 60)
        print("Cleaning NDMA staging tables")
        print("=" * 60)

        conn.execute(text("TRUNCATE ndma_casualties RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE ndma_damage RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE ndma_relief RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE ndma_rescue RESTART IDENTITY CASCADE"))

        json_files = sorted(PARSED_DIR.glob("*.json"))

        print(f"JSON Files : {len(json_files)}")

        casualties_rows = 0
        damage_rows = 0
        relief_rows = 0
        rescue_rows = 0

        for file in json_files:

            data = json.loads(file.read_text(encoding="utf-8"))

            common = {
                "source_file": data["filename"],
                "report_number": data["report_number"],
                "report_date": data["report_date"],
            }

            for row in data.get("casualties", []):

                conn.execute(
                    CASUALTIES_SQL,
                    {
                        **common,
                        **row,
                    },
                )

                casualties_rows += 1

            for row in data.get("damage", []):

                conn.execute(
                    DAMAGE_SQL,
                    {
                        **common,
                        **row,
                    },
                )

                damage_rows += 1

            for row in data.get("relief", []):

                conn.execute(
                    RELIEF_SQL,
                    {
                        **common,
                        **row,
                    },
                )

                relief_rows += 1

            for row in data.get("rescue", []):

                conn.execute(
                    RESCUE_SQL,
                    {
                        **common,
                        **row,
                    },
                )

                rescue_rows += 1

    print()
    print("=" * 60)
    print("NDMA LOADED")
    print("=" * 60)
    print("Casualties :", casualties_rows)
    print("Damage     :", damage_rows)
    print("Relief     :", relief_rows)
    print("Rescue     :", rescue_rows)
    print("=" * 60)


def main():
    load_json()


if __name__ == "__main__":
    main()