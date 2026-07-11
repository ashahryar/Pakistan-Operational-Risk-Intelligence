import json
import re
from pathlib import Path

from scripts.parsing.pmd.utils import clean_text

RAW_FILE = Path("data/raw/pmd/reports/weekly_outlook/all/latest.json")


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

    for table in raw.get("tables", []):

        for row in table.get("rows", []):

            if len(row) < 2:
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

    return output


if __name__ == "__main__":

    parsed = parse_weekly_outlook()

    print(f"Days Parsed : {len(parsed)}")

    print(json.dumps(parsed, indent=4, ensure_ascii=False))