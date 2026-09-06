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
# DATA QUALITY (Phase 1 / Task 6, ADR-0001)
# ==========================================================

from pipeline.utils.quarantine import write_quarantine
from config.data_quality import REJECTION_THRESHOLD

PARSER_VERSION = "1.0.0"

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

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for row in report.get("casualties", []):

        processed += 1

        try:

            with engine.begin() as conn:

                exists = conn.execute(
                    text("""
                        SELECT 1
                        FROM ndma_casualties
                        WHERE report_number=:report_number
                        AND province=:province
                        AND report_date IS NOT DISTINCT FROM :report_date
                        LIMIT 1
                    """),
                    {
                        "report_number": report_number,
                        "province": row.get("province"),
                        "report_date": report_date,
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

        except Exception as e:

            rejected += 1

            print(f"[CASUALTIES REJECTED] {json_file.name} | {row.get('province')} | {e}")

            write_quarantine(
                source="ndma",
                domain="casualties",
                source_document=json_file.name,
                reason_code="load_exception",
                message=str(e),
                parser_version=PARSER_VERSION,
                raw_payload=row,
            )

    print(f"[CASUALTIES] {json_file.name} | Inserted={inserted} Skipped={skipped} Rejected={rejected}")

    return processed, inserted, rejected


# ==========================================================
# LOAD DAMAGE
# ==========================================================

def load_damage(json_file):

    with open(json_file, "r", encoding="utf-8") as f:

        report = json.load(f)

    report_number = report.get("report_number")
    report_date = parse_date(report.get("report_date"))

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for row in report.get("damage", []):

        processed += 1

        try:

            with engine.begin() as conn:

                exists = conn.execute(
                    text("""
                        SELECT 1
                        FROM ndma_damage
                        WHERE report_number=:report_number
                        AND province=:province
                        AND report_date IS NOT DISTINCT FROM :report_date
                        LIMIT 1
                    """),
                    {
                        "report_number": report_number,
                        "province": row.get("province"),
                        "report_date": report_date,
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

        except Exception as e:

            rejected += 1

            print(f"[DAMAGE REJECTED] {json_file.name} | {row.get('province')} | {e}")

            write_quarantine(
                source="ndma",
                domain="damage",
                source_document=json_file.name,
                reason_code="load_exception",
                message=str(e),
                parser_version=PARSER_VERSION,
                raw_payload=row,
            )

    print(f"[DAMAGE] {json_file.name} | Inserted={inserted} Skipped={skipped} Rejected={rejected}")

    return processed, inserted, rejected

# ==========================================================
# LOAD RELIEF
# ==========================================================

def load_relief(json_file):

    with open(json_file, "r", encoding="utf-8") as f:

        report = json.load(f)

    report_number = report.get("report_number")
    report_date = parse_date(report.get("report_date"))

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for row in report.get("relief", []):

        processed += 1

        try:

            with engine.begin() as conn:

                exists = conn.execute(
                    text("""
                        SELECT 1
                        FROM ndma_relief
                        WHERE report_number = :report_number
                        AND province = :province
                        AND item = :item
                        AND report_date IS NOT DISTINCT FROM :report_date
                        LIMIT 1
                    """),
                    {
                        "report_number": report_number,
                        "province": row.get("province"),
                        "item": row.get("item"),
                        "report_date": report_date,
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

        except Exception as e:

            rejected += 1

            print(f"[RELIEF REJECTED] {json_file.name} | {row.get('province')} | {e}")

            write_quarantine(
                source="ndma",
                domain="relief",
                source_document=json_file.name,
                reason_code="load_exception",
                message=str(e),
                parser_version=PARSER_VERSION,
                raw_payload=row,
            )

    print(
        f"[RELIEF] {json_file.name} | Inserted={inserted} Skipped={skipped} Rejected={rejected}"
    )

    return processed, inserted, rejected


# ==========================================================
# LOAD RESCUE
# ==========================================================

def load_rescue(json_file):

    with open(json_file, "r", encoding="utf-8") as f:

        report = json.load(f)

    report_number = report.get("report_number")
    report_date = parse_date(report.get("report_date"))

    processed = 0
    inserted = 0
    skipped = 0
    rejected = 0

    for row in report.get("rescue", []):

        processed += 1

        try:

            with engine.begin() as conn:

                exists = conn.execute(
                    text("""
                        SELECT 1
                        FROM ndma_rescue
                        WHERE report_number = :report_number
                        AND province = :province
                        AND report_date IS NOT DISTINCT FROM :report_date
                        LIMIT 1
                    """),
                    {
                        "report_number": report_number,
                        "province": row.get("province"),
                        "report_date": report_date,
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

        except Exception as e:

            rejected += 1

            print(f"[RESCUE REJECTED] {json_file.name} | {row.get('province')} | {e}")

            write_quarantine(
                source="ndma",
                domain="rescue",
                source_document=json_file.name,
                reason_code="load_exception",
                message=str(e),
                parser_version=PARSER_VERSION,
                raw_payload=row,
            )

    print(
        f"[RESCUE] {json_file.name} | Inserted={inserted} Skipped={skipped} Rejected={rejected}"
    )

    return processed, inserted, rejected

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
    # NOTE (Phase 1 / Task 6, ADR-0001): the unconditional
    # TRUNCATE that previously ran here has been removed. It
    # erased all four NDMA tables on every run, so a parser
    # regression didn't just fail to add data -- it destroyed
    # previously-good data. Idempotency now comes from the
    # per-row dedup check in each load_*() function below
    # (report_number + province [+ item] + report_date), the
    # same pattern already used by load_pdma.py / load_pmd.py.
    # ------------------------------------------------------

    # ------------------------------------------------------
    # Process Files
    # ------------------------------------------------------

    file_success = 0
    file_failed = 0

    grand_processed = 0
    grand_succeeded = 0
    grand_rejected = 0

    for json_file in json_files:

        print("-" * 70)
        print(f"Processing : {json_file.name}")
        print("-" * 70)

        file_ok = True

        for loader, domain in (
            (load_casualties, "casualties"),
            (load_damage, "damage"),
            (load_relief, "relief"),
            (load_rescue, "rescue"),
        ):

            try:

                processed, succeeded, rejected = loader(json_file)

                grand_processed += processed
                grand_succeeded += succeeded
                grand_rejected += rejected

            except Exception as e:

                # An exception reaching here means the sub-loader itself
                # raised outside its own per-row try/except (e.g. the
                # JSON file could not be read) -- isolate it to this one
                # sub-table so the other three still get their chance.

                file_ok = False

                print(f"[ERROR] {json_file.name} | {domain} | {e}")

                write_quarantine(
                    source="ndma",
                    domain=domain,
                    source_document=json_file.name,
                    reason_code="load_exception",
                    message=str(e),
                    parser_version=PARSER_VERSION,
                )

        if file_ok:
            file_success += 1
        else:
            file_failed += 1

    # ------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------

    print()
    print("=" * 70)
    print("NDMA LOADER SUMMARY")
    print("=" * 70)

    print(f"Parsed JSON Files : {len(json_files)}")

    print(f"Files Fully Loaded : {file_success}")

    print(f"Files With Errors  : {file_failed}")

    print(f"Rows Processed     : {grand_processed}")

    print(f"Rows Succeeded     : {grand_succeeded}")

    print(f"Rows Rejected      : {grand_rejected}")

    print("=" * 70)

    print("NDMA DATA LOADED SUCCESSFULLY")

    print("=" * 70)

    # ------------------------------------------------------
    # DATA QUALITY GATE (Phase 1 / Task 6, ADR-0001, CLAUDE.md rule 5)
    # ------------------------------------------------------

    if grand_processed == 0:
        return

    rejection_ratio = grand_rejected / grand_processed

    print(f"Rejection Ratio      : {round(rejection_ratio * 100, 2)}%")
    print(f"Rejection Threshold  : {round(REJECTION_THRESHOLD * 100, 2)}%")

    if rejection_ratio > REJECTION_THRESHOLD:

        print("=" * 70)
        print("DATA QUALITY GATE FAILED")
        print(f"{grand_rejected}/{grand_processed} rows rejected — exceeds threshold")
        print("=" * 70)

        sys.exit(1)


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    main()