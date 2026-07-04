import argparse
from common.fetcher import HTTPClient
from common.filesystem import get_report_directory
from common.logger import setup_logger
from datetime import datetime
from typing import Dict,List

from bs4 import BeautifulSoup
import json

from common.pmd_parser import (
    extract_forecast_text,
    extract_tables,
)



logger = setup_logger("pmd")
client = HTTPClient()

# ==========================================================
# CONFIGURATION
# ==========================================================
MAX_EMPTY_PAGES = 1
REPORTS = {
    "daily_forecast": {
        "url": "https://nwfc.pmd.gov.pk/new/daily-forecast.php",
        "folder": "daily_forecast",
    },
    "weekly_outlook": {
        "url": "https://nwfc.pmd.gov.pk/new/weekly-outlook.php",
        "folder": "weekly_outlook",
    },
    "weather_alerts": {
        "url": "https://www.pmd.gov.pk/en/latest-weather-alerts.php",
        "folder": "weather_alerts",
    },
}
# ==========================================================
# CORE SCRAPE LOGIC FOR ONE REPORT/YEAR
# ==========================================================

def scrape_report(report_key: str, config: Dict[str, str]) -> int:

    folder = get_report_directory(
        "pmd",
        config["folder"],
        "all"
    )

    page_url = config["url"]

    logger.info("Scraping %s", report_key)

    response = client.get(page_url)

    if response is None:
        logger.warning("Skipping %s", page_url)
        return 0

    soup = BeautifulSoup(response.text, "html.parser")

    forecast = extract_forecast_text(soup)

    tables = extract_tables(soup)
    

    output = {
        "source": "PMD",
        "category": report_key,
        "url": page_url,
        "scraped_at": datetime.now().isoformat(),
        "forecast": forecast,
        "tables": tables,
    }

    json_file = folder / "latest.json"

    with open(json_file, "w", encoding="utf8") as f:
        json.dump(
            output,
            f,
            indent=4,
            ensure_ascii=False,
        )

    logger.info("Saved %s", json_file)

    print("Forecast saved successfully.")

    return 1



# ==========================================================
# MAIN
# ==========================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="PMD Pakistan reports scraper")
    parser.add_argument(
        "report",
        choices=list(REPORTS.keys()) + ["all"],
        help="daily_forecast | weekly_forecast | weather_alerts | all",
    )
    args = parser.parse_args()

    report_list = list(REPORTS.keys()) if args.report == "all" else [args.report]

    total_downloaded = 0

    for report_key in report_list:

        print("\n" + "=" * 70)
        print(f"Starting Report : {report_key.upper()}")
        print("=" * 70)

        config = REPORTS[report_key]

        total_downloaded += scrape_report(
            report_key,
            config
        )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("Reports        :", len(report_list))
    print("PDFs Downloaded:", total_downloaded)
    print("Completed Successfully")
    print("=" * 70)


if __name__ == "__main__":
    main()