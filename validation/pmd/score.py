"""
PMD Quality Score

Calculates overall quality score
for PMD datasets.
"""

from validation.pmd.completeness import calculate_completeness


# ==========================================================
# QUALITY SCORE
# ==========================================================

def calculate_score(

    daily_forecast,

    weather_alert,

    weekly_outlook,

    errors,

):

    completeness = calculate_completeness(

        daily_forecast,

        weather_alert,

        weekly_outlook,

    )

    score = completeness

    # ------------------------------------------------------
    # Validation Penalty
    # ------------------------------------------------------

    penalty = len(errors) * 5

    score -= penalty

    if score < 0:
        score = 0

    if score > 100:
        score = 100

    # ------------------------------------------------------
    # Quality Level
    # ------------------------------------------------------

    if score >= 90:
        quality = "Excellent"

    elif score >= 80:
        quality = "Good"

    elif score >= 70:
        quality = "Fair"

    else:
        quality = "Poor"

    valid = score >= 70

    return {

        "valid": valid,

        "score": score,

        "quality": quality,

        "completeness": completeness,

        "penalty": penalty,

        "error_count": len(errors),

        "errors": errors,

    }


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    daily = [

        {

            "city": "Karachi"

        }

    ]

    alert = {

        "alert_type": "Rain"

    }

    weekly = [

        {

            "weekday": "Monday"

        }

    ]

    result = calculate_score(

        daily,

        alert,

        weekly,

        [],

    )

    print(result)