"""
PDMA Gauge Report Parser

Parses PDMA Gauge / River Situation PDF reports into structured JSON.
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

    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def detect_flow(text: str):

    text = text.lower()

    for key, value in FLOW_STATUS.items():

        if key in text:

            return value

    return None


def extract_report_datetime(pdf_path: Path, first_page: str):

    candidates = [
        pdf_path.stem,
        first_page,
    ]

    for candidate in candidates:

        match = FILENAME_PATTERN.search(candidate)

        if not match:
            continue

        date_part = match.group(1)
        time_part = match.group(2).zfill(4)

        try:

            dt = parser.parse(
                f"{date_part} {time_part[:2]}:{time_part[2:]}",
                dayfirst=True,
            )

            return dt.isoformat()

        except Exception:

            continue

    return None


# ==========================================================
# TABLE PARSER
# ==========================================================


def parse_table(table):

    if not table:

        return []

    rows = [[clean(cell) for cell in row] for row in table]

    if len(rows) < 2:

        return []

    header = [c.lower() for c in rows[0]]

    station_idx = 0
    river_idx = None
    level_idx = None
    danger_idx = None
    discharge_idx = None
    flow_idx = None

    for i, column in enumerate(header):

        if "station" in column or "gauge" in column:
            station_idx = i

        elif "river" in column:
            river_idx = i

        elif "danger" in column:
            danger_idx = i

        elif "level" in column:
            level_idx = i

        elif "discharge" in column or "cusec" in column:
            discharge_idx = i

        elif (
            "flow" in column
            or "trend" in column
            or "status" in column
        ):
            flow_idx = i

    stations = []

    for row in rows[1:]:

        if not any(row):
            continue

        if station_idx >= len(row):
            continue

        station = row[station_idx]

        if station == "":
            continue

        river = row[river_idx] if river_idx is not None and river_idx < len(row) else ""

        current = row[level_idx] if level_idx is not None and level_idx < len(row) else ""

        danger = row[danger_idx] if danger_idx is not None and danger_idx < len(row) else ""

        discharge = row[discharge_idx] if discharge_idx is not None and discharge_idx < len(row) else ""

        flow = row[flow_idx] if flow_idx is not None and flow_idx < len(row) else ""

        if not flow:
            flow = detect_flow(" ".join(row))

        stations.append(
            {
                "station": station,
                "river": river or None,
                "current_level_ft": to_float(current),
                "danger_level_ft": to_float(danger),
                "discharge_cusecs": to_float(discharge),
                "flow_status": flow,
            }
        )

    return stations


# ==========================================================
# MAIN PARSER
# ==========================================================


def parse_pdf(pdf_path: Path):

    pdf_path = Path(pdf_path)

    first_page_text = ""

    gauges = []

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