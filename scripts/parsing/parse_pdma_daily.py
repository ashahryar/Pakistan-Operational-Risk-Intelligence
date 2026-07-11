"""
PDMA Daily Report Parser

Parses PDMA Daily Situation Report PDFs
and converts them into structured JSON.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from datetime import datetime

import pdfplumber

logger = logging.getLogger(__name__)

# ==========================================================
# HELPERS
# ==========================================================

DATE_PATTERNS = [

    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,\s+\d{4})",

    r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

    r"([A-Za-z]+\s+\d{1,2},\s+\d{4})",

]


def extract_date(text):

    for pattern in DATE_PATTERNS:

        match = re.search(pattern, text)

        if match:

            return match.group(1)

    return None


def extract_time(text):

    match = re.search(

        r"TIME[:\s]+(\d{3,4})",

        text,

        re.IGNORECASE,

    )

    if match:

        return match.group(1)

    return None


def extract_forecast(text):

    start = text.upper().find("WEATHER FORECAST")

    if start == -1:

        return ""

    forecast = text[start:start + 1200]

    return " ".join(forecast.split())


def extract_temperature(text):

    results = re.findall(

        r"([A-Za-z ]+)=\s*(\d+)\s*°?C",

        text,

    )

    output = {}

    for city, value in results:

        output[city.strip()] = int(value)

    return output


def extract_rainfall(text):

    results = re.findall(

        r"([A-Za-z ()]+)=\s*(\d+(?:\.\d+)?)",

        text,

    )

    rainfall = {}

    for city, value in results:

        rainfall[city.strip()] = float(value)

    return rainfall


def extract_dams(text):

    dams = []

    pattern = re.compile(

        r"(Tarbela Dam|Mangla Dam|Bhakra Dam|Pong Dam|Thein Dam).*?(Normal|Low|Medium|High)",

        re.DOTALL,

    )

    for match in pattern.finditer(text):

        dams.append(

            {

                "dam": match.group(1),

                "status": match.group(2),

            }

        )

    return dams


# ==========================================================
# MAIN PARSER
# ==========================================================

def parse_pdf(pdf_path: Path):

    pdf_path = Path(pdf_path)

    text = ""

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

    result = {

        "source_file": pdf_path.name,

        "report_type": "daily",

        "report_year": pdf_path.parent.parent.name,

        "report_date": extract_date(text),

        "report_time": extract_time(text),

        "forecast": extract_forecast(text),

        "temperature": extract_temperature(text),

        "rainfall": extract_rainfall(text),

        "dams": extract_dams(text),

        "created_at": datetime.now().isoformat(),

    }

    logger.info("Parsed %s", pdf_path.name)

    return result


if __name__ == "__main__":

    print(

        "This parser is intended to be used from parse_pdma.py"

    )