"""
Load PDMA Parsed JSON into PostgreSQL
"""

import sys
import json
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from config.database import engine


# ==========================================================
# PATHS
# ==========================================================

BASE = Path("data/parsed/pdma")

DAILY_DIR = BASE / "daily"

RAINFALL_DIR = BASE / "rainfall"

GAUGE_DIR = BASE / "gauge"


# ==========================================================
# HELPER
# ==========================================================

def json_files(folder):

    if not folder.exists():
        return []

    return sorted(folder.rglob("*.json"))


# ==========================================================
# LOAD DAILY REPORTS
# ==========================================================

def load_daily():

    files = json_files(DAILY_DIR)

    inserted = 0
    skipped = 0

    with engine.begin() as conn:

        for file in files:

            report = json.loads(
                file.read_text(
                    encoding="utf-8"
                )
            )

            # --------------------------------------
            # Skip Invalid Reports
            # --------------------------------------

            validation = report.get("validation", {})

            if not validation.get("valid", True):

                skipped += 1

                continue

            # --------------------------------------
            # Duplicate Check
            # --------------------------------------

            exists = conn.execute(

                text("""

                SELECT 1

                FROM pdma_daily_reports

                WHERE source_file = :source

                LIMIT 1

                """),

                {
                    "source": report["source_file"]
                }

            ).fetchone()

            if exists:

                skipped += 1

                continue

            # --------------------------------------
            # Insert
            # --------------------------------------

            conn.execute(

                text("""

                INSERT INTO pdma_daily_reports(

                    source_file,

                    report_date,

                    report_year,

                    raw_data

                )

                VALUES(

                    :source,

                    :date,

                    :year,

                    CAST(:raw AS JSONB)

                )

                """),

                {

                    "source": report["source_file"],

                    "date": report.get("report_date"),

                    "year": int(report["report_year"]),

                    "raw": json.dumps(report)

                }

            )

            inserted += 1

    print(f"✓ Daily Reports Loaded ({inserted})")
    print(f"✓ Daily Reports Skipped ({skipped})")

# ==========================================================
# LOAD RAINFALL REPORTS
# ==========================================================

def load_rainfall():

    files = json_files(RAINFALL_DIR)

    inserted = 0
    skipped = 0

    with engine.begin() as conn:

        for file in files:

            report = json.loads(
                file.read_text(
                    encoding="utf-8"
                )
            )

            # --------------------------------------
            # Skip Invalid Reports
            # --------------------------------------

            validation = report.get("validation", {})

            if not validation.get("valid", True):

                skipped += 1

                continue

            stations = report.get("stations", [])

            for station in stations:

                # --------------------------------------
                # Ignore Empty Station
                # --------------------------------------

                if not station.get("station"):

                    continue

                # --------------------------------------
                # Duplicate Check
                # --------------------------------------

                exists = conn.execute(

                    text("""

                    SELECT 1

                    FROM pdma_rainfall_readings

                    WHERE source_file = :source
                      AND station = :station

                    LIMIT 1

                    """),

                    {

                        "source": report["source_file"],

                        "station": station["station"]

                    }

                ).fetchone()

                if exists:

                    skipped += 1

                    continue

                # --------------------------------------
                # Insert
                # --------------------------------------

                conn.execute(

                    text("""

                    INSERT INTO pdma_rainfall_readings(

                        source_file,

                        report_date,

                        report_year,

                        station,

                        rainfall_mm

                    )

                    VALUES(

                        :source,

                        :date,

                        :year,

                        :station,

                        :rainfall

                    )

                    """),

                    {

                        "source": report["source_file"],

                        "date": report.get("report_date"),

                        "year": int(report["report_year"]),

                        "station": station["station"],

                        "rainfall": station.get("rainfall_mm")

                    }

                )

                inserted += 1

    print(f"✓ Rainfall Loaded ({inserted})")
    print(f"✓ Rainfall Skipped ({skipped})")

# ==========================================================
# LOAD GAUGE REPORTS
# ==========================================================

def load_gauge():

    files = json_files(GAUGE_DIR)

    inserted = 0
    skipped = 0

    with engine.begin() as conn:

        for file in files:

            report = json.loads(
                file.read_text(
                    encoding="utf-8"
                )
            )

            # --------------------------------------
            # Skip Invalid Reports
            # --------------------------------------

            validation = report.get("validation", {})

            if not validation.get("valid", True):

                skipped += 1

                continue

            gauges = report.get("gauges", [])

            for gauge in gauges:

                # --------------------------------------
                # Ignore Empty Station
                # --------------------------------------

                if not gauge.get("station"):

                    continue

                # --------------------------------------
                # Duplicate Check
                # --------------------------------------

                exists = conn.execute(

                    text("""

                    SELECT 1

                    FROM pdma_gauge_readings

                    WHERE source_file = :source
                      AND station = :station

                    LIMIT 1

                    """),

                    {

                        "source": report["source_file"],

                        "station": gauge["station"]

                    }

                ).fetchone()

                if exists:

                    skipped += 1

                    continue

                # --------------------------------------
                # Insert
                # --------------------------------------

                conn.execute(

                    text("""

                    INSERT INTO pdma_gauge_readings(

                        source_file,

                        report_datetime,

                        report_year,

                        station,

                        river,

                        current_level_ft,

                        danger_level_ft,

                        discharge_cusecs,

                        flow_status

                    )

                    VALUES(

                        :source,

                        :datetime,

                        :year,

                        :station,

                        :river,

                        :current,

                        :danger,

                        :discharge,

                        :status

                    )

                    """),

                    {

                        "source": report["source_file"],

                        "datetime": report.get("report_datetime"),

                        "year": report.get("report_year"),

                        "station": gauge.get("station"),

                        "river": gauge.get("river"),

                        "current": gauge.get("current_level_ft"),

                        "danger": gauge.get("danger_level_ft"),

                        "discharge": gauge.get("discharge_cusecs"),

                        "status": gauge.get("flow_status")

                    }

                )

                inserted += 1

    print(f"✓ Gauge Reports Loaded ({inserted})")
    print(f"✓ Gauge Reports Skipped ({skipped})")

# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 60)
    print("Loading PDMA Parsed Data")
    print("=" * 60)

    try:

        load_daily()

        load_rainfall()

        load_gauge()

    except Exception as e:

        print("=" * 60)
        print("PDMA LOADING FAILED")
        print("=" * 60)
        print(e)
        print("=" * 60)

        raise

    print("=" * 60)
    print("PDMA DATA LOADED SUCCESSFULLY")
    print("=" * 60)


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    main()
    