import json
from pathlib import Path

from scripts.parsing.pmd.utils import (
    clean_text,
    extract_number,
    province_from_city,
)

RAW_FILE = Path("data/raw/pmd/reports/daily_forecast/all/latest.json")


def parse_daily_forecast():

    if not RAW_FILE.exists():
        raise FileNotFoundError(RAW_FILE)

    with open(RAW_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    output = []

    for table in raw.get("tables", []):

        for row in table.get("rows", []):

            if len(row) < 6:
                continue

            city = clean_text(row[5])

            humidity = extract_number(row[4])

            temperature = extract_number(row[3])

            day1 = clean_text(row[2])

            day2 = clean_text(row[1])

            day3 = clean_text(row[0])

            output.append({

                "city": city,

                "province": province_from_city(city),

                "temperature": temperature,

                "humidity": humidity,

                "forecast_day_1": day1,

                "forecast_day_2": day2,

                "forecast_day_3": day3,

                "category": raw["category"],

                "scraped_at": raw["scraped_at"]

            })

    return output


if __name__ == "__main__":

    data = parse_daily_forecast()

    print(f"Cities Parsed : {len(data)}")

    print(json.dumps(data[:5], indent=4, ensure_ascii=False))