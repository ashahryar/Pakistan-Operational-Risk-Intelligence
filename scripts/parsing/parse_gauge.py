"""
PDMA Gauge Report Parser
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber
from dateutil import parser

logger = logging.getLogger(__name__)

# ==========================================================
# REGEX
# ==========================================================

FILENAME_PATTERN = re.compile(
    r"(\d{2}\.\d{2}\.\d{4})[_ ]+(\d{3,4})",
    re.IGNORECASE,
)

FLOW_STATUS = {
    "rising": "RISING",
    "falling": "FALLING",
    "steady": "STEADY",
    "stationary": "STEADY",
    "receding": "FALLING",
}


# ==========================================================
# HELPERS
# ==========================================================

def clean(value: Any) -> str:

    if value is None:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def to_float(value: str):

    if not value:
        return None

    value = value.replace(",", "")

    m = re.search(r"-?\d+(?:\.\d+)?", value)

    if not m:
        return None

    try:
        return float(m.group())
    except Exception:
        return None


def detect_flow(text: str):

    text = text.lower()

    for k, v in FLOW_STATUS.items():

        if k in text:
            return v

    return None


def extract_report_datetime(pdf_path: Path, first_page: str):

    candidates = [
        pdf_path.stem,
        first_page,
    ]

    for candidate in candidates:

        m = FILENAME_PATTERN.search(candidate)

        if not m:
            continue

        date_part = m.group(1)
        time_part = m.group(2).zfill(4)

        try:

            dt = parser.parse(
                f"{date_part} {time_part[:2]}:{time_part[2:]}",
                dayfirst=True,
            )

            return dt.isoformat()

        except Exception:
            pass

    return None


# ==========================================================
# TABLE PARSER
# ==========================================================

def parse_table(table):

    if not table:
        return []

    rows = [
        [clean(c) for c in row]
        for row in table
    ]

    if len(rows) < 2:
        return []

    stations = []

    current_river = None

    for row in rows:

        if not any(row):
            continue

        # --------------------------------------------------
        # Skip headers
        # --------------------------------------------------

        first = row[0].upper() if len(row) > 0 else ""
        second = row[1].upper() if len(row) > 1 else ""

        if first in {
            "RIVER",
            "SITE",
            "DISCHARGE",
            "FLOOD LIMITS",
            "INFLOW",
            "OUTFLOW",
        }:
            continue

        # --------------------------------------------------
        # Main River Table
        # --------------------------------------------------

        if len(row) >= 12:

            if row[0]:
                current_river = clean(row[0]).upper()

            station = clean(row[1])

            if not station:
                continue

            river = current_river

            current_level = to_float(row[3])

            danger_level = to_float(row[6])

            discharge = to_float(row[9])

            flow = clean(row[11])

            if not flow:
                flow = detect_flow(" ".join(row))

            stations.append(
                {
                    "station": station,
                    "river": river,
                    "current_level_ft": current_level,
                    "danger_level_ft": danger_level,
                    "discharge_cusecs": discharge,
                    "flow_status": flow,
                }
            )

            continue

        # --------------------------------------------------
        # Ignore notes/footer
        # --------------------------------------------------

        text = " ".join(row).upper()

        if text.startswith("NOTE"):
            continue

        if "DATA SOURCE" in text:
            continue

        if "PEOC" in text:
            continue

        if "PROVINCIAL DISASTER" in text:
            continue

    return stations

# ==========================================================
# MAIN PARSER
# ==========================================================

def parse_pdf(pdf_path: Path):

    pdf_path = Path(pdf_path)

    gauges = []

    first_page_text = ""

    with pdfplumber.open(pdf_path) as pdf:

        if not pdf.pages:
            raise ValueError("PDF contains no pages.")

        first_page_text = pdf.pages[0].extract_text() or ""

        for page in pdf.pages:

            tables = page.extract_tables()

            if not tables:
                continue

            for table in tables:
                gauges.extend(parse_table(table))

    unique = {}

    for item in gauges:

        key = (
            item["station"],
            item["river"],
        )

        unique[key] = item

    result = {

        "source_file": pdf_path.name,

        "report_type": "gauge",

        "report_datetime": extract_report_datetime(
            pdf_path,
            first_page_text,
        ),

        "gauge_count": len(unique),

        "gauges": list(unique.values()),

        "created_at": datetime.now().isoformat(),

    }

    logger.info(
        "Parsed %s (%d stations)",
        pdf_path.name,
        len(unique),
    )

    return result


if __name__ == "__main__":

    print(
        "This file is intended to be imported by parse_pdma.py"
    )