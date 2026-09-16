"""
validation/rules.py

Field-level validators used by validation/validator.py to check
individual PMD weather-record fields.

Task 16A (Phase 1 / ADR-0001): this file previously defined
valid_temperature/valid_humidity/valid_city/valid_forecast TWICE.
Python keeps only the second definition of a name in a module, so the
first (pandas-based, temperature range -10..60) was silently dead --
confirmed unreachable by every caller and by
tests/parsers/test_type_coercion.py, which already only exercised the
second (live) definitions. The dead first block, plus its
now-unreferenced `is_empty`/`has_duplicates` helpers (confirmed unused
anywhere else in the repo), has been removed. Behavior is unchanged --
only the second definitions were ever actually reachable.
"""


def valid_city(city):

    if city is None:
        return False

    city = str(city).strip()

    if city == "":
        return False

    if city.lower() == "unknown":
        return False

    return True


def valid_temperature(temp):

    try:

        temp = float(temp)

    except Exception:

        return False

    return -20 <= temp <= 60


def valid_humidity(humidity):

    try:

        humidity = float(humidity)

    except Exception:

        return False

    return 0 <= humidity <= 100


def valid_forecast(text):

    if text is None:
        return False

    text = str(text).strip()

    return text != ""
