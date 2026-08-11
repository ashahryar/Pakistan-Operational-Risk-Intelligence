"""
scripts/parsing/pmd/daily_parser.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import json

from validation.translator import normalize_city
from validation.validator import validate_weather

from scripts.parsing.pmd.utils import (
    clean_text,
    extract_number,
    province_from_city,
    district_from_city,
)

# ==========================================================
# FILES
# ==========================================================

RAW_FILE = Path(
    "data/raw/pmd/reports/daily_forecast/all/latest.json"
)

OUTPUT_DIR = Path(
    "data/parsed/pmd/daily_forecast"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "latest.json"


# ==========================================================
# PARSER
# ==========================================================

def parse_daily_forecast():

    if not RAW_FILE.exists():
        raise FileNotFoundError(RAW_FILE)

    with open(RAW_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    parsed = []

    for table in raw.get("tables", []):

        for row in table.get("rows", []):

            if len(row) < 6:
                continue

            # ---------------------------------
            # Clean Values
            # ---------------------------------

            city = clean_text(row[5])

            city = normalize_city(clean_text(row[5]))

            province = province_from_city(city)

            district = district_from_city(city)

            temperature = extract_number(row[3])

            humidity = extract_number(row[4])

            day1 = clean_text(row[2])

            day2 = clean_text(row[1])

            day3 = clean_text(row[0])

            # ---------------------------------
            # Validation
            # ---------------------------------

            if not validate_weather(
                city=city,
                temperature=temperature,
                humidity=humidity,
                day1=day1,
            ):
                continue

            # ---------------------------------
            # Parsed Record
            # ---------------------------------

            parsed.append({

                "city": city,

                "district": district,

                "province": province,

                "temperature": temperature,

                "humidity": humidity,

                "forecast_day_1": day1,

                "forecast_day_2": day2,

                "forecast_day_3": day3,

                "category": raw["category"],

                "scraped_at": raw["scraped_at"]

            })

    return parsed


# ==========================================================
# SAVE
# ==========================================================

def save_daily_forecast():

    data = parse_daily_forecast()

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4,
        )

    print("=" * 60)
    print(f"PMD Daily Forecast Parsed : {len(data)} Records")
    print(f"Saved : {OUTPUT_FILE}")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    save_daily_forecast()