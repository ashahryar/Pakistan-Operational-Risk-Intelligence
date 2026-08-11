"""
PDMA Rainfall Report Parser

Parses PDMA rainfall report PDFs and converts them
into structured JSON.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pdfplumber

logger = logging.getLogger(__name__)


# ==========================================================
# HELPERS
# ==========================================================

DATE_PATTERNS = [
    r"(\d{1,2}\.\d{1,2}\.\d{4})",
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,\s+\d{4})",
    r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    r"([A-Za-z]+\s+\d{1,2},\s+\d{4})",
]


def extract_report_date(text: str):
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_numeric(value):
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group())


# ==========================================================
# TABLE PARSER
# ==========================================================

def parse_table(table) -> List[Dict]:

    stations = []

    if not table:
        return stations

    for row in table:

        row = [clean_text(cell) for cell in row]

        if len(row) < 2:
            continue

        station = row[0]
        rainfall = parse_numeric(row[1])

        if not station:
            continue

        if rainfall is None:
            continue

        stations.append(
            {
                "station": station,
                "rainfall_mm": rainfall,
            }
        )

    return stations


# ==========================================================
# MAIN PARSER
# ==========================================================

def parse_rainfall_report(pdf_path: Path):

    pdf_path = Path(pdf_path)

    all_text = ""
    stations = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:
                all_text += page_text + "\n"

            tables = page.extract_tables()

            # =====================================================
            # DEBUG INFORMATION
            # =====================================================
            print("\n" + "=" * 70)
            print("PDF :", pdf_path.name)
            print("PAGE:", page.page_number)
            print("TABLES FOUND:", len(tables))

            if page_text:
                print("\nFIRST 1500 CHARACTERS\n")
                print(page_text[:1500])
            else:
                print("\nNO TEXT EXTRACTED\n")

            # =====================================================

            if not tables:
                continue

            for i, table in enumerate(tables):

                print(f"\nTABLE {i+1}")

                if table:
                    for row in table[:5]:
                        print(row)

                stations.extend(parse_table(table))

    unique = {}

    for station in stations:
        unique[station["station"]] = station

    result = {
        "source_file": pdf_path.name,
        "report_type": "rainfall",
        "report_year": pdf_path.parent.parent.name,
        "report_date": extract_report_date(all_text),
        "station_count": len(unique),
        "stations": list(unique.values()),
        "created_at": datetime.now().isoformat(),
    }

    logger.info(
        "%s parsed (%d stations)",
        pdf_path.name,
        len(unique),
    )

    return result


if __name__ == "__main__":

    print(
        "Use this parser through scripts/parsing/parse_pdma.py"
    )