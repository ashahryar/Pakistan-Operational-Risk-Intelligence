"""
validation/validator.py
"""

from typing import Optional

from validation.rules import (
    valid_city,
    valid_temperature,
    valid_humidity,
    valid_forecast,
)

from validation.logger import log_validation


# ==========================================================
# LIMITS
# ==========================================================

MIN_TEMP = -20
MAX_TEMP = 60

MIN_HUMIDITY = 0
MAX_HUMIDITY = 100


# ==========================================================
# MAIN VALIDATION
# ==========================================================

def validate_weather(
    city: str,
    temperature: Optional[float],
    humidity: Optional[float],
    day1: str,
) -> bool:

    errors = []

    # -------------------------
    # City
    # -------------------------

    if not valid_city(city):
        errors.append("Invalid City")

    # -------------------------
    # Temperature
    # -------------------------

    if (
        temperature is None
        or not valid_temperature(temperature)
        or temperature < MIN_TEMP
        or temperature > MAX_TEMP
    ):
        errors.append("Invalid Temperature")

    # -------------------------
    # Humidity
    # -------------------------

    if (
        humidity is None
        or not valid_humidity(humidity)
        or humidity < MIN_HUMIDITY
        or humidity > MAX_HUMIDITY
    ):
        errors.append("Invalid Humidity")

    # -------------------------
    # Forecast
    # -------------------------

    if not valid_forecast(day1):
        errors.append("Missing Day1 Forecast")

    # -------------------------
    # Logging
    # -------------------------

    if errors:

        log_validation(
            source="PMD",
            status="FAILED",
            message=", ".join(errors),
        )

        return False

    log_validation(
        source="PMD",
        status="SUCCESS",
        message=f"{city} validated successfully",
    )

    return True