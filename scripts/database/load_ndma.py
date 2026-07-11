import json
import sys
from pathlib import Path
from datetime import datetime

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.database import engine


def parse_date(value):

    if not value:
        return None

    return datetime.strptime(
        value,
        "%d %B %Y"
    ).date()


def to_int(value):

    if value in (None, "", "-", "N/A"):
        return None

    try:
        return int(float(value))
    except:
        return None


def to_float(value):

    if value in (None, "", "-", "N/A"):
        return None

    try:
        return float(value)
    except:
        return None


# ==========================================================
# CONFIGURATION
# ==========================================================

DATASET_FOLDER = Path("data/analytics/ndma")

FILES = {
    "casualties": "casualties.json",
    "damage": "damage.json",
    "relief": "relief.json",
    "rescue": "rescue.json",
}

# ==========================================================
# HELPERS
# ==========================================================

def load_json(file_name: str):

    file = DATASET_FOLDER / file_name

    with open(file, "r", encoding="utf8") as f:
        return json.load(f)

# ==========================================================
# LOAD CASUALTIES
# ==========================================================

def load_casualties():

    rows = load_json(FILES["casualties"])

    with engine.begin() as conn:

        for row in rows:
            row["report_date"] = parse_date(row["report_date"])
            row["deaths"] = to_int(row["deaths"])
            row["injured"] = to_int(row["injured"])
            conn.execute(

                text("""

                INSERT INTO ndma_casualties(

                    report_number,
                    report_date,
                    province,
                    deaths,
                    injured

                )

                VALUES(

                    :report_number,
                    :report_date,
                    :province,
                    :deaths,
                    :injured

                )

                """),

                row

            )

    print(f"Loaded {len(rows)} casualty records")

# ==========================================================
# LOAD DAMAGE
# ==========================================================

def load_damage():

    rows = load_json(FILES["damage"])

    with engine.begin() as conn:

        for row in rows:
            row["report_date"] = parse_date(row["report_date"])
            row["roads_km"] = to_float(row["roads_km"])
            row["bridges"] = to_int(row["bridges"])
            row["houses_total"] = to_int(row["houses_total"])
            row["livestock"] = to_int(row["livestock"])

            conn.execute(

                text("""

                INSERT INTO ndma_damage(

                    report_number,
                    report_date,
                    province,
                    roads_km,
                    bridges,
                    houses_total,
                    livestock

                )

                VALUES(

                    :report_number,
                    :report_date,
                    :province,
                    :roads_km,
                    :bridges,
                    :houses_total,
                    :livestock

                )

                """),

                row

            )

    print(f"Loaded {len(rows)} damage records")

# ==========================================================
# LOAD RELIEF
# ==========================================================

def load_relief():

    rows = load_json(FILES["relief"])

    with engine.begin() as conn:

        for row in rows:
            row["report_date"] = parse_date(row["report_date"])
            row["quantity"] = to_int(row["quantity"])
            conn.execute(

                text("""

                INSERT INTO ndma_relief(

                    report_number,
                    report_date,
                    province,
                    item,
                    quantity

                )

                VALUES(

                    :report_number,
                    :report_date,
                    :province,
                    :item,
                    :quantity

                )

                """),

                row

            )

    print(f"Loaded {len(rows)} relief records")

# ==========================================================
# LOAD RESCUE
# ==========================================================

def load_rescue():

    rows = load_json(FILES["rescue"])

    with engine.begin() as conn:

        for row in rows:
            row["report_date"] = parse_date(row["report_date"])
            row["operations"] = to_int(row["operations"])
            row["rescued"] = to_int(row["rescued"])

            conn.execute(

                text("""

                INSERT INTO ndma_rescue(

                    report_number,
                    report_date,
                    province,
                    rescue_operations,
                    persons_rescued

                )

                VALUES(

                    :report_number,
                    :report_date,
                    :province,
                    :operations,
                    :rescued

                )

                """),

                row

            )

    print(f"Loaded {len(rows)} rescue records")

# ==========================================================
# MAIN
# ==========================================================

def main():
    with engine.begin() as conn:
        conn.execute(text("""
            TRUNCATE TABLE
                ndma_casualties,
                ndma_damage,
                ndma_relief,
                ndma_rescue
            RESTART IDENTITY CASCADE;
        """))

    print("=" * 60)
    print("LOADING NDMA DATASETS")
    print("=" * 60)

    load_casualties()
    load_damage()
    load_relief()
    load_rescue()

    print()
    print("=" * 60)
    print("NDMA DATA LOADED SUCCESSFULLY")
    print("=" * 60)

if __name__ == "__main__":
    main()