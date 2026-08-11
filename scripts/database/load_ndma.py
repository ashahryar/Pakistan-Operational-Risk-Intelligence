"""
NDMA Loader

Reads parsed NDMA JSON files and loads them
directly into PostgreSQL.

Flow:

Parsed JSON
        ↓
Loader
        ↓
PostgreSQL
"""

import json
import sys
from pathlib import Path
from datetime import datetime

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from config.database import engine

# ==========================================================
# CONFIGURATION
# ==========================================================

PARSED_FOLDER = Path(
    "data/parsed/ndma/sitreps"
)
with engine.connect() as conn:
    print("Database :", conn.execute(text("SELECT current_database()")).scalar())
    print("Port     :", conn.execute(text("SELECT inet_server_port()")).scalar())

# ==========================================================
# HELPERS
# ==========================================================

def parse_date(value):

    if not value:
        return None

    formats = [

        "%d %B %Y",
        "%d %b %Y",
        "%Y-%m-%d",

    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                value.strip(),
                fmt
            ).date()

        except Exception:
            pass

    return None


def to_int(value):

    if value in (
        None,
        "",
        "-",
        "N/A",
    ):
        return None

    try:
        return int(float(value))

    except Exception:
        return None


def to_float(value):

    if value in (
        None,
        "",
        "-",
        "N/A",
    ):
        return None

    try:
        return float(value)

    except Exception:
        return None


# ==========================================================
# READ PARSED JSON FILES
# ==========================================================

def load_parsed_files():

    json_files = sorted(
        PARSED_FOLDER.glob("*.json")
    )

    print("=" * 60)
    print(f"Found {len(json_files)} parsed NDMA files")
    print("=" * 60)

    return json_files

# ==========================================================
# LOAD CASUALTIES
# ==========================================================

def load_casualties(json_file):

    with open(json_file, "r", encoding="utf-8") as f:

        report = json.load(f)
        print("Damage rows =", len(report.get("damage", [])))

    report_number = report.get("report_number")
    report_date = parse_date(report.get("report_date"))

    inserted = 0
    skipped = 0

    with engine.begin() as conn:

        for row in report.get("casualties", []):

            exists = conn.execute(
                text("""
                    SELECT 1
                    FROM ndma_casualties
                    WHERE report_number=:report_number
                    AND province=:province
                    LIMIT 1
                """),
                {
                    "report_number": report_number,
                    "province": row.get("province"),
                }
            ).fetchone()

            if exists:

                skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO ndma_casualties
                    (
                        report_number,
                        report_date,
                        province,
                        deaths,
                        injured
                    )
                    VALUES
                    (
                        :report_number,
                        :report_date,
                        :province,
                        :deaths,
                        :injured
                    )
                """),
                {
                    "report_number": report_number,
                    "report_date": report_date,
                    "province": row.get("province"),
                    "deaths": to_int(row.get("deaths")),
                    "injured": to_int(row.get("injured")),
                }
            )

            inserted += 1

    print(f"[CASUALTIES] {json_file.name} | Inserted={inserted} Skipped={skipped}")


# ==========================================================
# LOAD DAMAGE
# ==========================================================

def load_damage(json_file):

    with open(json_file, "r", encoding="utf-8") as f:

        report = json.load(f)

    report_number = report.get("report_number")
    report_date = parse_date(report.get("report_date"))

    inserted = 0
    skipped = 0

    with engine.begin() as conn:

        for row in report.get("damage", []):

            exists = conn.execute(
                text("""
                    SELECT 1
                    FROM ndma_damage
                    WHERE report_number=:report_number
                    AND province=:province
                    LIMIT 1
                """),
                {
                    "report_number": report_number,
                    "province": row.get("province"),
                }
            ).fetchone()

            if exists:

                skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO ndma_damage
                    (
                        report_number,
                        report_date,
                        province,
                        roads_km,
                        bridges,
                        houses_total,
                        livestock
                    )
                    VALUES
                    (
                        :report_number,
                        :report_date,
                        :province,
                        :roads_km,
                        :bridges,
                        :houses_total,
                        :livestock
                    )
                """),
                {
                    "report_number": report_number,
                    "report_date": report_date,
                    "province": row.get("province"),
                    "roads_km": to_float(row.get("roads_km")),
                    "bridges": to_int(row.get("bridges")),
                    "houses_total": to_int(row.get("houses_damaged")),
                    "livestock": to_int(row.get("livestock")),
                }
            )

            inserted += 1

    print(f"[DAMAGE] {json_file.name} | Inserted={inserted} Skipped={skipped}")

# ==========================================================
# LOAD RELIEF
# ==========================================================

def load_relief(json_file):

    with open(json_file, "r", encoding="utf-8") as f:

        report = json.load(f)

    report_number = report.get("report_number")
    report_date = parse_date(report.get("report_date"))

    inserted = 0
    skipped = 0

    with engine.begin() as conn:

        for row in report.get("relief", []):

            exists = conn.execute(
                text("""
                    SELECT 1
                    FROM ndma_relief
                    WHERE report_number = :report_number
                    AND province = :province
                    AND item = :item
                    LIMIT 1
                """),
                {
                    "report_number": report_number,
                    "province": row.get("province"),
                    "item": row.get("item"),
                },
            ).fetchone()

            if exists:

                skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO ndma_relief
                    (
                        report_number,
                        report_date,
                        province,
                        item,
                        quantity
                    )
                    VALUES
                    (
                        :report_number,
                        :report_date,
                        :province,
                        :item,
                        :quantity
                    )
                """),
                {
                    "report_number": report_number,
                    "report_date": report_date,
                    "province": row.get("province"),
                    "item": row.get("item"),
                    "quantity": to_int(row.get("quantity")),
                },
            )

            inserted += 1

    print(
        f"[RELIEF] {json_file.name} | Inserted={inserted} Skipped={skipped}"
    )


# ==========================================================
# LOAD RESCUE
# ==========================================================

def load_rescue(json_file):

    with open(json_file, "r", encoding="utf-8") as f:

        report = json.load(f)

    report_number = report.get("report_number")
    report_date = parse_date(report.get("report_date"))

    inserted = 0
    skipped = 0

    with engine.begin() as conn:

        for row in report.get("rescue", []):

            exists = conn.execute(
                text("""
                    SELECT 1
                    FROM ndma_rescue
                    WHERE report_number = :report_number
                    AND province = :province
                    LIMIT 1
                """),
                {
                    "report_number": report_number,
                    "province": row.get("province"),
                },
            ).fetchone()

            if exists:

                skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO ndma_rescue
                    (
                        report_number,
                        report_date,
                        province,
                        rescue_operations,
                        persons_rescued
                    )
                    VALUES
                    (
                        :report_number,
                        :report_date,
                        :province,
                        :operations,
                        :rescued
                    )
                """),
                {
                    "report_number": report_number,
                    "report_date": report_date,
                    "province": row.get("province"),
                    "operations": to_int(row.get("operations")),
                    "rescued": to_int(row.get("rescued")),
                },
            )

            inserted += 1

    print(
        f"[RESCUE] {json_file.name} | Inserted={inserted} Skipped={skipped}"
    )

# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 70)
    print("LOADING NDMA PARSED DATA")
    print("=" * 70)

    if not PARSED_FOLDER.exists():

        print("Parsed folder not found.")
        return

    # ------------------------------------------------------
    # Find Parsed JSON Files
    # ------------------------------------------------------

    json_files = load_parsed_files()

    if not json_files:

        print("No parsed JSON files found.")
        return

    # ------------------------------------------------------
    # Clear Tables
    # ------------------------------------------------------

    with engine.begin() as conn:

        conn.execute(
            text("""
                TRUNCATE TABLE

                    ndma_casualties,

                    ndma_damage,

                    ndma_relief,

                    ndma_rescue

                RESTART IDENTITY CASCADE;
            """)
        )

    print("Database tables cleared.")
    print()

    # ------------------------------------------------------
    # Process Files
    # ------------------------------------------------------

    success = 0
    failed = 0

    for json_file in json_files:

        print("-" * 70)
        print(f"Processing : {json_file.name}")
        print("-" * 70)

        try:

            load_casualties(json_file)

            load_damage(json_file)

            load_relief(json_file)

            load_rescue(json_file)

            success += 1

        except Exception as e:

            failed += 1

            print(f"[ERROR] {json_file.name}")

            print(e)

    # ------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------

    print()
    print("=" * 70)
    print("NDMA LOADER SUMMARY")
    print("=" * 70)

    print(f"Parsed JSON Files : {len(json_files)}")

    print(f"Loaded Successfully : {success}")

    print(f"Failed : {failed}")

    print("=" * 70)

    print("NDMA DATA LOADED SUCCESSFULLY")

    print("=" * 70)


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    main()