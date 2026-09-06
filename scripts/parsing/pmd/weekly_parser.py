import json
import re
from pathlib import Path

from scripts.parsing.pmd.utils import clean_text
from pipeline.utils.quarantine import write_quarantine

RAW_FILE = Path("data/raw/pmd/reports/weekly_outlook/all/latest.json")

PARSER_VERSION = "1.0.0"


def extract_regions(text):

    region_keywords = {
        "Punjab": ["پنجاب"],
        "Sindh": ["سندھ"],
        "Khyber Pakhtunkhwa": ["خیبر", "پختونخوا"],
        "Balochistan": ["بلوچستان"],
        "Islamabad": ["اسلام آباد", "اسلام آباد"],
        "Gilgit Baltistan": ["گلگت"],
        "AJK": ["کشمیر"]
    }

    regions = []

    text = clean_text(text)

    for region, keywords in region_keywords.items():

        for keyword in keywords:

            if keyword in text:

                regions.append(region)

                break

    return regions


def extract_weekday(date_text):

    mapping = {
        "پیر": "Monday",
        "منگل": "Tuesday",
        "بدھ": "Wednesday",
        "جمعرات": "Thursday",
        "جمعہ": "Friday",
        "جمعه": "Friday",
        "ہفتہ": "Saturday",
        "اتوار": "Sunday",
    }

    for urdu, english in mapping.items():

        if urdu in date_text:

            return english

    return None


def parse_weekly_outlook():

    with open(RAW_FILE, encoding="utf-8") as f:

        raw = json.load(f)

    output = []
    processed = 0
    rejected = 0

    for table in raw.get("tables", []):

        for row in table.get("rows", []):

            processed += 1

            if len(row) < 2:

                rejected += 1

                write_quarantine(
                    source="pmd",
                    domain="weekly_outlook",
                    source_document=str(RAW_FILE),
                    reason_code="row_too_short",
                    message=f"Row has {len(row)} cells, expected >= 2",
                    parser_version=PARSER_VERSION,
                    raw_payload=row,
                )

                continue

            summary = clean_text(row[0])

            date = clean_text(row[1])

            output.append({

                "date": date,

                "weekday": extract_weekday(date),

                "weather_summary": summary,

                "regions": extract_regions(summary),

                "category": raw["category"],

                "scraped_at": raw["scraped_at"]

            })

    return output, processed, rejected


if __name__ == "__main__":

    parsed, processed, rejected = parse_weekly_outlook()

    print(f"Days Parsed : {len(parsed)} | Processed : {processed} | Rejected : {rejected}")

    print(json.dumps(parsed, indent=4, ensure_ascii=False))