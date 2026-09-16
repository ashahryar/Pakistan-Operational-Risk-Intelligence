import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

from bs4 import BeautifulSoup

from common.fetcher import HTTPClient
from common.filesystem import get_report_directory
from common.logger import setup_logger
from common.pmd_parser import (
    extract_forecast_text,
    extract_tables,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.acquisition.raw_store import write_verified_bytes  # noqa: E402

logger = setup_logger("pmd")
client = HTTPClient()

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


def scrape_report(report_key: str, config: Dict[str, str]) -> int:

    logger.info("=" * 60)
    logger.info("Scraping %s", report_key)

    try:

        response = client.get(config["url"])

        if response is None:
            logger.error("No response received.")
            return 0

        if response.status_code != 200:
            logger.error(
                "HTTP %s returned from %s",
                response.status_code,
                config["url"],
            )
            return 0

        soup = BeautifulSoup(response.text, "html.parser")

        forecast = extract_forecast_text(soup)

        tables = extract_tables(soup)

        if not forecast:
            logger.warning("Forecast text is empty.")

        if not tables:
            logger.warning("No tables extracted.")

        folder = get_report_directory(
            "pmd",
            config["folder"],
            "all",
        )

        output = {
            "source": "PMD",
            "category": report_key,
            "url": config["url"],
            "scraped_at": datetime.utcnow().isoformat(),
            "forecast": forecast,
            "tables": tables,
        }

        json_file = folder / "latest.json"

        # Task 16A (Phase 1 / ADR-0001), Part A item 6: reuses Task 15's
        # atomic, checksum-verified write (scripts/acquisition/raw_store.py)
        # instead of a direct open(...,"w") -- a crash or the same
        # Windows read-back timing issue Task 15 diagnosed could
        # otherwise leave a truncated/corrupt latest.json silently
        # treated as a successful scrape.
        content = json.dumps(output, indent=4, ensure_ascii=False).encode("utf-8")
        write_verified_bytes(json_file, content)

        logger.info("Saved %s", json_file)

        return 1

    except Exception as e:

        logger.exception(
            "Failed while scraping %s : %s",
            report_key,
            e,
        )

        return 0


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "report",
        choices=list(REPORTS.keys()) + ["all"],
    )

    args = parser.parse_args()

    reports = (
        list(REPORTS.keys())
        if args.report == "all"
        else [args.report]
    )

    total = 0

    for report in reports:

        total += scrape_report(
            report,
            REPORTS[report],
        )

    print("=" * 60)
    print("Completed")
    print("Reports :", len(reports))
    print("Success :", total)
    print("=" * 60)


if __name__ == "__main__":
    main()