"""
PMD Schema Validation

Validates:

1. Daily Forecast
2. Weather Alerts
3. Weekly Outlook
"""

# ==========================================================
# REQUIRED FIELDS
# ==========================================================

DAILY_REQUIRED = [

    "city",
    "district",
    "province",

    "temperature",
    "humidity",

    "forecast_day_1",
    "forecast_day_2",
    "forecast_day_3",

    "category",
    "scraped_at",

]

ALERT_REQUIRED = [

    "alert_type",

    "severity",

    "duration",

    "regions",

    "forecast",

    "category",

    "scraped_at",

]

WEEKLY_REQUIRED = [

    "date",

    "weekday",

    "weather_summary",

    "regions",

    "category",

    "scraped_at",

]

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
# DAILY VALIDATION
# ==========================================================

def validate_daily(data):

    errors = []

    if not isinstance(data, list):

        return False, ["Daily Forecast must be a list"]

    for index, row in enumerate(data):

        for field in DAILY_REQUIRED:

            if not has_value(row.get(field)):

                errors.append(
                    f"Daily[{index}] Missing : {field}"
                )

    return len(errors) == 0, errors


# ==========================================================
# ALERT VALIDATION
# ==========================================================

def validate_alert(data):

    errors = []

    if not isinstance(data, dict):

        return False, ["Weather Alert must be an object"]

    for field in ALERT_REQUIRED:

        if not has_value(data.get(field)):

            errors.append(
                f"Alert Missing : {field}"
            )

    return len(errors) == 0, errors


# ==========================================================
# WEEKLY VALIDATION
# ==========================================================

def validate_weekly(data):

    errors = []

    if not isinstance(data, list):

        return False, ["Weekly Outlook must be a list"]

    for index, row in enumerate(data):

        for field in WEEKLY_REQUIRED:

            if not has_value(row.get(field)):

                errors.append(
                    f"Weekly[{index}] Missing : {field}"
                )

    return len(errors) == 0, errors


# ==========================================================
# MASTER VALIDATOR
# ==========================================================

def validate_schema(

    daily_forecast,

    weather_alert,

    weekly_outlook,

):

    errors = []

    valid1, err1 = validate_daily(
        daily_forecast
    )

    valid2, err2 = validate_alert(
        weather_alert
    )

    valid3, err3 = validate_weekly(
        weekly_outlook
    )

    errors.extend(err1)
    errors.extend(err2)
    errors.extend(err3)

    return (

        len(errors) == 0,

        errors,

    )


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    print("PMD Schema Validator Ready")