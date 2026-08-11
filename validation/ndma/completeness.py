"""
NDMA Completeness Assessment

Computes completeness percentage
and field-level report for NDMA SITREPs.
"""

from typing import Dict, Any

# ==========================================================
# FIELD WEIGHTS
# ==========================================================

FIELD_WEIGHTS = {

    "report_number": 10,
    "report_date": 10,
    "subject": 10,

    "casualties": 15,
    "damage": 15,
    "relief": 10,
    "rescue": 10,

    "provinces": 5,
    "rivers": 5,
    "dams": 5,
    "weather_events": 5,

}

TOTAL_WEIGHT = sum(FIELD_WEIGHTS.values())


# ==========================================================
# HELPERS
# ==========================================================

def has_value(value):

    if value is None:
        return False

    if isinstance(value, str):
        return value.strip() != ""

    if isinstance(value, list):
        return len(value) > 0

    if isinstance(value, dict):
        return len(value) > 0

    return True


# ==========================================================
# CALCULATE COMPLETENESS
# ==========================================================

def calculate_completeness(data: Dict[str, Any]) -> int:

    earned = 0

    for field, weight in FIELD_WEIGHTS.items():

        if has_value(data.get(field)):
            earned += weight

    percentage = round((earned / TOTAL_WEIGHT) * 100)

    return percentage


# ==========================================================
# FIELD REPORT
# ==========================================================

def completeness_report(data: Dict[str, Any]):

    report = {}

    earned = 0

    missing = []

    for field, weight in FIELD_WEIGHTS.items():

        ok = has_value(data.get(field))

        report[field] = ok

        if ok:
            earned += weight
        else:
            missing.append(field)

    percentage = round((earned / TOTAL_WEIGHT) * 100)

    report["earned_score"] = earned
    report["total_score"] = TOTAL_WEIGHT
    report["completeness"] = percentage
    report["missing_fields"] = missing

    return report


# ==========================================================
# PRINT REPORT
# ==========================================================

def print_completeness(report):

    print("=" * 60)
    print("NDMA COMPLETENESS REPORT")
    print("=" * 60)

    for field in FIELD_WEIGHTS:

        status = "PASS" if report[field] else "FAIL"
        print(f"{field:<20} : {status}")

    print("-" * 60)

    print(
        f"Completeness : {report['completeness']}%"
    )

    print(
        f"Score        : {report['earned_score']}/{report['total_score']}"
    )

    if report["missing_fields"]:

        print("\nMissing Fields:")

        for field in report["missing_fields"]:
            print(f" - {field}")

    print("=" * 60)


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    sample = {

        "report_number": "57",
        "report_date": "2026-07-17",
        "subject": "Flood SITREP",

        "casualties": [{"province": "Punjab"}],
        "damage": [{"province": "Punjab"}],
        "relief": [{"province": "Punjab"}],
        "rescue": [{"province": "Punjab"}],

        "provinces": ["Punjab"],
        "rivers": ["Indus"],
        "dams": ["Tarbela"],
        "weather_events": ["Flood"],

    }

    report = completeness_report(sample)

    print_completeness(report)