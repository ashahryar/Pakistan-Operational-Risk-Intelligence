"""
Extract structured information from NDMA SitReps.
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
def extract_provinces(text: str):

    provinces = []

    names = [

        "Punjab",

        "Sindh",

        "Balochistan",

        "Khyber Pakhtunkhwa",

        "KP",

        "Gilgit Baltistan",

        "GB",

        "AJK",

        "Islamabad",

    ]

    lower = text.lower()

    for province in names:

        if province.lower() in lower:

            provinces.append(province)

    return sorted(set(provinces))
def extract_rivers(text: str):

    rivers = []

    names = [

        "Indus",

        "Jhelum",

        "Chenab",

        "Ravi",

        "Sutlej",

        "Kabul",

        "Swat",

    ]

    lower = text.lower()

    for river in names:

        if river.lower() in lower:

            rivers.append(river)

    return sorted(set(rivers))
def extract_dams(text: str):

    dams = []

    names = [

        "Tarbela",

        "Mangla",

        "Chashma",

    ]

    lower = text.lower()

    for dam in names:

        if dam.lower() in lower:

            dams.append(dam)

    return sorted(set(dams))
def extract_weather_events(text: str):

    keywords = [

        "Flood",

        "Flash Flood",

        "Rain",

        "Heavy Rain",

        "Thunderstorm",

        "Windstorm",

        "Landslide",

        "Glacial Lake",

        "Cloudburst",

        "Heatwave",

    ]

    events = []

    lower = text.lower()

    for event in keywords:

        if event.lower() in lower:

            events.append(event)

    return sorted(set(events))
