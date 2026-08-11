"""
Data Quality Checks

Used after parsing and before warehouse loading.
"""

from pathlib import Path
import json


# ==========================================================
# JSON FILE CHECK
# ==========================================================

def check_json_files(folder):

    folder = Path(folder)

    files = list(folder.rglob("*.json"))

    if not files:
        raise RuntimeError(
            f"No JSON files found in {folder}"
        )

    print("=" * 60)
    print(f"JSON Files : {len(files)}")
    print("=" * 60)

    return files


# ==========================================================
# EMPTY FILE CHECK
# ==========================================================

def check_empty_json(files):

    empty = []

    for file in files:

        if file.stat().st_size == 0:
            empty.append(file.name)

    if empty:

        raise RuntimeError(
            f"Empty JSON files found:\n{empty}"
        )

    print("✓ No empty JSON files")


# ==========================================================
# PDMA REPORT DATETIME CHECK
# ==========================================================

def check_report_datetime(files):

    missing = []

    for file in files:

        with open(file, encoding="utf-8") as f:

            data = json.load(f)

        if data.get("report_type") != "gauge":
            continue

        if not data.get("report_datetime"):

            missing.append(file.name)

    if missing:

        raise RuntimeError(
            f"Missing report_datetime:\n{missing}"
        )

    print("✓ report_datetime validated")


# ==========================================================
# PDMA GAUGE CHECK
# ==========================================================

def check_gauge_count(files):

    bad = []

    for file in files:

        with open(file, encoding="utf-8") as f:

            data = json.load(f)

        if data.get("report_type") != "gauge":
            continue

        gauges = data.get("gauges", [])

        if len(gauges) == 0:

            bad.append(file.name)

    if bad:

        raise RuntimeError(
            f"Gauge reports contain zero stations:\n{bad}"
        )

    print("✓ Gauge reports validated")


# ==========================================================
# NDMA REPORT CHECK
# ==========================================================

def check_ndma_reports(files):

    bad = []

    for file in files:

        with open(file, encoding="utf-8") as f:

            data = json.load(f)

        if data.get("report_type") != "sitrep":
            continue

        if not data.get("report_number"):
            bad.append(file.name)
            continue

        if not data.get("report_date"):
            bad.append(file.name)

    if bad:

        raise RuntimeError(
            f"Invalid NDMA reports:\n{bad}"
        )

    print("✓ NDMA reports validated")


# ==========================================================
# PDMA VALIDATION
# ==========================================================

def validate_pdma(folder):

    files = check_json_files(folder)

    check_empty_json(files)

    check_report_datetime(files)

    check_gauge_count(files)

    print("=" * 60)
    print("PDMA DATA QUALITY PASSED")
    print("=" * 60)


# ==========================================================
# NDMA VALIDATION
# ==========================================================

def validate_ndma(folder):

    files = check_json_files(folder)

    check_empty_json(files)

    check_ndma_reports(files)

    print("=" * 60)
    print("NDMA DATA QUALITY PASSED")
    print("=" * 60)