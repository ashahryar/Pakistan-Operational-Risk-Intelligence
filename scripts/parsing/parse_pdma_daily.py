"""
PDMA Daily Situation Report Parser
Production Parser (Part 1)
"""

from __future__ import annotations

import re
import json
import logging
from pathlib import Path
from datetime import datetime

import pdfplumber

logger = logging.getLogger(__name__)

# ==========================================================
# DATE PATTERNS
# ==========================================================

DATE_PATTERNS = [

    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})",

    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,\s+\d{4})",

    r"([A-Za-z]+\s+\d{1,2},\s+\d{4})",

]

# ==========================================================
# DAMS
# ==========================================================

KNOWN_DAMS = [

    "Tarbela",
    "Mangla",
    "Chashma",
    "Taunsa",
    "Bhakra",
    "Pong",
    "Thein",

]

# ==========================================================
# HELPERS
# ==========================================================

def clean(text: str) -> str:
    """
    Normalize extracted PDF text.
    """

    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = text.replace("§", " ")
    text = text.replace("•", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ==========================================================
# READ PDF
# ==========================================================

def read_pdf(pdf_path: Path) -> str:

    pages = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            txt = page.extract_text()

            if txt:

                pages.append(txt)

    return clean("\n".join(pages))


# ==========================================================
# DATE
# ==========================================================

def extract_date(text: str):

    for pattern in DATE_PATTERNS:

        match = re.search(pattern, text, re.IGNORECASE)

        if match:

            return clean(match.group(1)).upper()

    return None


# ==========================================================
# TIME
# ==========================================================

def extract_time(text: str):

    patterns = [

        r"TIME[: ]+(\d{3,4})",

        r"(\d{3,4})\s*HRS",

        r"(\d{3,4})\s*HOURS",

    ]

    for pattern in patterns:

        m = re.search(pattern, text, re.IGNORECASE)

        if m:

            return m.group(1)

    return None


# ==========================================================
# TEMPERATURE BLOCK
# ==========================================================

def extract_temperature(text):

    """
    Implement in Part-2
    """

    return {}


# ==========================================================
# RAINFALL BLOCK
# ==========================================================

def extract_rainfall(text):

    """
    Implement in Part-2
    """

    return {}

# ==========================================================
# TEMPERATURE
# ==========================================================

def extract_temperature(text):

    temperatures = {}

    # Maximum Temperatures section only
    start = re.search(
        r"Maximum Temperatures recorded in last 24 hours",
        text,
        re.IGNORECASE,
    )

    if not start:
        return temperatures

    temp_text = text[start.end():]

    # Stop before forecast paragraph starts
    stop = re.search(
        r"Rain-wind|WEATHER ALERT|ADVISORY|DATA SOURCE",
        temp_text,
        re.IGNORECASE,
    )

    if stop:
        temp_text = temp_text[:stop.start()]

    pattern = re.compile(
        r"([A-Za-z][A-Za-z\s\-\(\)]+?)\s*=\s*(\d+(?:\.\d+)?)\s*o?°?C",
        re.IGNORECASE,
    )

    bad_words = [
        "FRIDAY",
        "SATURDAY",
        "SUNDAY",
        "MONDAY",
        "TUESDAY",
        "WEDNESDAY",
        "THURSDAY",
        "Maximum",
        "Temperatures",
        "recorded",
        "last",
        "hours",
    ]

    for city, temp in pattern.findall(temp_text):

        city = clean(city)

        for word in bad_words:
            city = re.sub(
                rf"\b{word}\b",
                "",
                city,
                flags=re.IGNORECASE,
            )

        city = clean(city)

        if len(city) < 2:
            continue

        temperatures[city] = float(temp)

    return temperatures


# ==========================================================
# RAINFALL
# ==========================================================

def extract_rainfall(text):

    rainfall = {}

    start = re.search(
        r"RAINFALL",
        text,
        re.IGNORECASE,
    )

    if not start:
        return rainfall

    rain_text = text[start.start():]

    pattern = re.compile(
        r"([A-Za-z][A-Za-z\s\-\(\)]+?)\s*=\s*(\d+(?:\.\d+)?)\s*mm",
        re.IGNORECASE,
    )

    for city, value in pattern.findall(rain_text):

        city = clean(city)

        if len(city) < 2:
            continue

        rainfall[city] = float(value)

    return rainfall


# ==========================================================
# WEATHER FORECAST
# ==========================================================

def extract_forecast(text):

    match = re.search(
        r"WEATHER FORECAST\s*\(24 HOURS\)(.*?)(?=WEATHER ALERT|ADVISORY|DATA SOURCE)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return ""

    forecast = clean(match.group(1))

    # remove temperature entries
    forecast = re.sub(
        r"[A-Za-z][A-Za-z\s\-\(\)]+=\s*\d+(?:\.\d+)?\s*o?°?C",
        "",
        forecast,
        flags=re.IGNORECASE,
    )

    forecast = clean(forecast)

    return forecast


# ==========================================================
# WEATHER ALERT
# ==========================================================

def extract_weather_alert(text):

    match = re.search(
        r"WEATHER ALERT.*?(?=DATA SOURCE|HYDROLOGICAL SITUATION|LOSS/DAMAGE|DAMS|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return ""

    return clean(match.group())

# ==========================================================
# FORECAST DISTRICTS
# ==========================================================

DISTRICTS = [

    "Rawalpindi",
    "Murree",
    "Galliyat",
    "Chakwal",
    "Attock",
    "Jhelum",
    "Gujrat",
    "Gujranwala",
    "Hafizabad",
    "Mandi Bahauddin",
    "Sialkot",
    "Sheikhupura",
    "Narowal",
    "Lahore",
    "Kasur",
    "Nankana Sahib",
    "Okara",
    "Sargodha",
    "Mianwali",
    "Faisalabad",
    "Jhang",
    "Chiniot",
    "Khushab",
    "DG Khan",
    "D.G. Khan",
    "Layyah",
    "Bhakkar",
    "Toba Tek Singh",
    "Sahiwal",
    "Kot Addu",
    "Pakpattan",
    "Vehari",
    "Multan",
    "Muzaffargarh",
    "Bahawalpur",
    "Bahawalnagar",
    "Lodhran",
    "Rahim Yar Khan",
    "Rajanpur",
    "Khanewal",
]

def extract_forecast_districts(text):

    forecast = extract_forecast(text)

    if not forecast:
        return []

    found = []

    forecast_upper = forecast.upper()

    for district in DISTRICTS:

        if district.upper() in forecast_upper:

            found.append(district)

    return sorted(list(set(found)))


# ==========================================================
# DAM STATUS
# ==========================================================

def extract_dams(text):

    dams = []

    for dam in KNOWN_DAMS:

        pattern = re.search(

            rf"{dam}.*?(LOW|MEDIUM|HIGH|NORMAL)",

            text,

            re.IGNORECASE | re.DOTALL,

        )

        status = "Unknown"

        if pattern:

            status = pattern.group(1).title()

        dams.append({

            "dam": dam,

            "status": status

        })

    return dams


# ==========================================================
# REPORT META
# ==========================================================

def extract_report_metadata(text):

    return {

        "report_date": extract_date(text),

        "report_time": extract_time(text),

        "forecast": extract_forecast(text),

        "weather_alert": extract_weather_alert(text),

        "forecast_districts": extract_forecast_districts(text),

        "temperature": extract_temperature(text),

        "rainfall": extract_rainfall(text),

        "dams": extract_dams(text),

    }

# ==========================================================
# MAIN PARSER
# ==========================================================

def parse_pdf(pdf_path: Path):

    pdf_path = Path(pdf_path)

    text = read_pdf(pdf_path)

    report = extract_report_metadata(text)

    report.update({

        "source_file": pdf_path.name,

        "report_type": "daily",

        "report_year": pdf_path.parent.parent.name,

        "created_at": datetime.now().isoformat(),

    })

    logger.info("Successfully parsed %s", pdf_path.name)

    return report


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    SAMPLE_DIR = Path(
        "data/raw/pdma/reports/daily_reports/2025/pdfs"
    )

    pdfs = sorted(SAMPLE_DIR.glob("*.pdf"))

    if not pdfs:

        print("No PDF files found.")

    else:

        report = parse_pdf(pdfs[0])

        print(

            json.dumps(

                report,

                indent=4,

                ensure_ascii=False,

            )

        )