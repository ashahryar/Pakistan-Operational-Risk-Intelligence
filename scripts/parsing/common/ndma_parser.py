"""
NDMA specific parser.
"""

import re


def extract_report_number(text: str):

    match = re.search(
        r"Situation Report No\.?\s*([0-9]+)",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return None


def extract_report_date(text: str):

    match = re.search(
        r"Dated:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return None


def extract_subject(text: str):

    match = re.search(
        r"Subject:\s*(.*?)\n",
        text,
        re.DOTALL,
    )

    if match:
        return match.group(1).strip()

    return None
