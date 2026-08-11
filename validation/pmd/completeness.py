"""
PMD Completeness Score

Calculates completeness percentage
for PMD datasets.
"""

# ==========================================================
# FIELD WEIGHTS
# ==========================================================

FIELD_WEIGHTS = {

    "daily_forecast": 40,

    "weather_alert": 30,

    "weekly_outlook": 30,

}


# ==========================================================
# HELPERS
# ==========================================================

def has_value(value):

    if value is None:
        return False

    if value == "":
        return False

    if isinstance(value, list) and len(value) == 0:
        return False

    if isinstance(value, dict) and len(value) == 0:
        return False

    return True


# ==========================================================
# COMPLETENESS
# ==========================================================

def calculate_completeness(

    daily_forecast,

    weather_alert,

    weekly_outlook,

):

    score = 0

    total = sum(FIELD_WEIGHTS.values())

    if has_value(daily_forecast):
        score += FIELD_WEIGHTS["daily_forecast"]

    if has_value(weather_alert):
        score += FIELD_WEIGHTS["weather_alert"]

    if has_value(weekly_outlook):
        score += FIELD_WEIGHTS["weekly_outlook"]

    completeness = round(

        (score / total) * 100,

        2,

    )

    return completeness


# ==========================================================
# REPORT
# ==========================================================

def completeness_report(

    daily_forecast,

    weather_alert,

    weekly_outlook,

):

    report = {

        "daily_forecast": has_value(
            daily_forecast
        ),

        "weather_alert": has_value(
            weather_alert
        ),

        "weekly_outlook": has_value(
            weekly_outlook
        ),

    }

    report["completeness"] = calculate_completeness(

        daily_forecast,

        weather_alert,

        weekly_outlook,

    )

    return report


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    daily = [{"city": "Karachi"}]

    alert = {

        "alert_type": "Rain"

    }

    weekly = [

        {

            "weekday": "Monday"

        }

    ]

    print(

        completeness_report(

            daily,

            alert,

            weekly,

        )

    )