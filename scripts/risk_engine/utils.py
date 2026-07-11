import re


def normalize(text):

    if text is None:
        return ""

    return text.lower().strip()


def contains(text, keyword):

    return keyword.lower() in text.lower()


def score_to_level(score):

    if score >= 80:
        return "Extreme"

    elif score >= 60:
        return "High"

    elif score >= 40:
        return "Medium"

    elif score >= 20:
        return "Low"

    else:
        return "Minimal"


def recommendation(level):

    mapping = {

        "Extreme": "Suspend field operations",

        "High": "Delay deliveries and avoid unnecessary travel",

        "Medium": "Operate with caution",

        "Low": "Normal operation with monitoring",

        "Minimal": "Safe to operate"

    }

    return mapping[level]