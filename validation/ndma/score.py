"""
NDMA Quality Score

Combines

1. Completeness
2. Validation Errors

to generate a final quality score.
"""

from validation.ndma.completeness import (
    calculate_completeness,
)


# ==========================================================
# SETTINGS
# ==========================================================

ERROR_PENALTY = 5

PASSING_SCORE = 70


# ==========================================================
# QUALITY LEVEL
# ==========================================================

def quality_level(score):

    if score >= 90:
        return "Excellent"

    if score >= 80:
        return "Good"

    if score >= 70:
        return "Acceptable"

    if score >= 50:
        return "Poor"

    return "Invalid"


# ==========================================================
# SCORE
# ==========================================================

def calculate_score(data, errors):

    """
    Returns

    {
        valid,
        score,
        completeness,
        quality,
        error_count,
        penalty,
        errors
    }
    """

    completeness = calculate_completeness(data)

    error_count = len(errors)

    penalty = error_count * ERROR_PENALTY

    score = completeness - penalty

    score = max(0, min(score, 100))

    valid = score >= PASSING_SCORE

    return {

        "valid": valid,

        "score": score,

        "completeness": completeness,

        "quality": quality_level(score),

        "error_count": error_count,

        "penalty": penalty,

        "errors": errors,

    }


# ==========================================================
# PRINT REPORT
# ==========================================================

def print_score(result):

    print("=" * 60)
    print("NDMA QUALITY REPORT")
    print("=" * 60)

    print(f"Quality Score : {result['score']}%")
    print(f"Completeness  : {result['completeness']}%")
    print(f"Quality Level : {result['quality']}")
    print(f"Penalty       : {result['penalty']}")
    print(f"Errors        : {result['error_count']}")
    print(f"Valid         : {result['valid']}")

    if result["errors"]:

        print("\nValidation Errors")

        for err in result["errors"]:
            print(f" - {err}")

    print("=" * 60)


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    sample = {

        "report_number": "56",

        "report_date": "2026-07-15",

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

    errors = []

    result = calculate_score(
        sample,
        errors,
    )

    print_score(result)