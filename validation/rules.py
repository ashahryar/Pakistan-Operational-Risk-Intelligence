"""
validation/rules.py
"""

import pandas as pd


def is_empty(value):
    return pd.isna(value) or str(value).strip() == ""


def valid_temperature(value):

    try:
        value = float(value)
        return -10 <= value <= 60
    except:
        return False


def valid_humidity(value):

    try:
        value = float(value)
        return 0 <= value <= 100
    except:
        return False


def valid_city(city):

    return not is_empty(city)


def valid_forecast(text):

    return not is_empty(text)


def has_duplicates(df, subset):

    return df.duplicated(subset=subset).any()

"""
validation/rules.py
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